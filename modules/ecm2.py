#!/usr/bin/env python3
"""
ecm.py — Emotional Context Module (ECM) reference implementation
Implements the frozen API v1.0:

Base URL: http://localhost:7321/ecm

GET  /v1/now
PUT  /v1/override
POST /v1/label
GET  /v1/health

Design goals:
- Small, legible, local-first.
- Streaming keystroke features + 90s EWMA window.
- “Kick pedal” tempo override with gentle decay.
- Classifier is real-but-swappable (drop-in weights file).

Dependencies:
- Required: fastapi, uvicorn, pydantic, numpy
- Optional (for real key capture): pynput

Run:
  pip install fastapi uvicorn numpy pydantic
  # Optional keystrokes:
  pip install pynput
  python ecm.py

Then:
  curl http://localhost:7321/ecm/v1/health
  curl http://localhost:7321/ecm/v1/now
"""

from __future__ import annotations

import os
import time
import math
import json
import sqlite3
import threading
from dataclasses import dataclass
from typing import Deque, Dict, List, Optional, Tuple
from collections import deque, Counter

import numpy as np
from fastapi import FastAPI, Response
from pydantic import BaseModel, Field


# ----------------------------
# Frozen contract constants
# ----------------------------

BASE_PATH = "/ecm"
API_PREFIX = f"{BASE_PATH}/v1"

WINDOW_SECONDS_DEFAULT = 90.0
EWMA_HALFLIFE_SECONDS = 30.0  # as discussed (phrase-level sensitivity)
POLL_MAX_LATENCY_MS_TARGET = 8.0

BPM_MIN = 60
BPM_MAX = 180

OVERRIDE_DURATION_SECONDS = 120.0
OVERRIDE_SOURCE_SECONDS = 5.0  # first few seconds read "override" then "decay"

DEFAULT_DB_PATH = os.environ.get("ECM_DB_PATH", "ecm_labels.db")
DEFAULT_WEIGHTS_PATH = os.environ.get("ECM_WEIGHTS", "ecm_weights.npz")

# CORS: open for localhost only (per contract). We do minimal headers in responses.
LOCALHOST_ORIGINS = {
    "http://localhost",
    "http://localhost:3000",
    "http://localhost:5173",
    "http://127.0.0.1",
    "http://127.0.0.1:3000",
    "http://127.0.0.1:5173",
}

# ----------------------------
# Models (API)
# ----------------------------


class OverrideIn(BaseModel):
    factor: float = Field(
        ..., description="0.5=half-time, 2.0=double-time, 1.0=release"
    )


class LabelIn(BaseModel):
    start_ts: float
    end_ts: float
    label: str


class NowOut(BaseModel):
    ts: float
    bpm: int
    valence: float
    confidence: float
    tokens_per_minute: int
    window_seconds: int
    source: str  # "live" | "override" | "decay"
    tempo_mode: str = "normal"  # "normal" | "slow" | "rest"


class HealthOut(BaseModel):
    status: str
    model_crc: str


# ----------------------------
# Keystroke event store
# ----------------------------


@dataclass(frozen=True)
class KeyEvent:
    ts: float
    key_id: str  # a coarse ID, not raw text
    is_backspace: bool


class RingBuffer:
    """
    Lock-protected ring buffer of KeyEvent.
    Keeps only the last WINDOW_SECONDS_DEFAULT + some slack.
    """

    def __init__(self, max_seconds: float):
        self.max_seconds = float(max_seconds)
        self._events: Deque[KeyEvent] = deque()
        self._lock = threading.Lock()

    def add(self, ev: KeyEvent) -> None:
        with self._lock:
            self._events.append(ev)
            self._trim_locked(now=ev.ts)

    def snapshot(self, now: float) -> List[KeyEvent]:
        with self._lock:
            self._trim_locked(now=now)
            return list(self._events)

    def _trim_locked(self, now: float) -> None:
        cutoff = now - self.max_seconds
        while self._events and self._events[0].ts < cutoff:
            self._events.popleft()


# ----------------------------
# Feature extraction (12 floats)
# ----------------------------


def _safe_div(a: float, b: float) -> float:
    return a / b if b != 0 else 0.0


def _shannon_entropy(counter: Counter) -> float:
    total = sum(counter.values())
    if total <= 0:
        return 0.0
    ent = 0.0
    for c in counter.values():
        p = c / total
        if p > 0:
            ent -= p * math.log(p + 1e-12, 2)
    return float(ent)


@dataclass
class FeatureVector:
    x: np.ndarray  # shape (12,)


class FeatureExtractor:
    """
    Computes a compact vector from keystroke events over a rolling window.

    Notes:
    - We purposely avoid storing actual typed text.
    - “edit_distance_rate” is approximated from backspace behavior + burstiness,
      unless you later integrate a real edit-distance stream from your editor.
    """

    def __init__(self, window_seconds: float):
        self.window_seconds = float(window_seconds)

    def compute(self, events: List[KeyEvent], now: float) -> FeatureVector:
        start = now - self.window_seconds
        evs = [e for e in events if e.ts >= start]
        n = len(evs)

        if n < 2:
            return FeatureVector(x=np.zeros((12,), dtype=np.float32))

        times = np.array([e.ts for e in evs], dtype=np.float64)
        dt = np.diff(times)
        dt = np.clip(dt, 1e-4, None)  # avoid zeros

        # Keystrokes per second
        span = max(times[-1] - times[0], 1e-3)
        kps_mean = n / span
        kps_var = float(np.var(1.0 / dt))  # rough "instantaneous rate" variance
        inter_key_cv = float(np.std(dt) / (np.mean(dt) + 1e-9))

        # Backspace rate + pause-after-backspace
        backspaces = [e for e in evs if e.is_backspace]
        backspace_rate = _safe_div(len(backspaces), span)

        pause_after_bs_ms = 0.0
        if backspaces:
            pauses = []
            for i in range(1, n):
                if evs[i - 1].is_backspace:
                    pauses.append((evs[i].ts - evs[i - 1].ts) * 1000.0)
            pause_after_bs_ms = float(np.mean(pauses)) if pauses else 0.0

        # Pause density and long pause ratio
        pause_threshold = 0.300  # 300 ms
        long_pause_threshold = 1.000  # 1 s
        pauses = dt[dt > pause_threshold]
        pause_density = float(len(pauses) / span)
        long_pause_ratio = float(
            _safe_div(float(np.sum(dt > long_pause_threshold)), len(dt))
        )

        # Burst ratio: keystrokes in bursts (>3 keys within 200 ms between presses)
        burst_dt = 0.200
        burst_mask = (dt <= burst_dt).astype(np.int32)
        # A "burst key" is any key that is close to previous key.
        burst_ratio = float(np.sum(burst_mask) / max(len(dt), 1))

        # Tempo slope: compare first half vs second half kps
        mid = start + self.window_seconds / 2.0
        first = [e for e in evs if e.ts < mid]
        second = [e for e in evs if e.ts >= mid]

        def _kps(segment: List[KeyEvent]) -> float:
            if len(segment) < 2:
                return 0.0
            s = segment[-1].ts - segment[0].ts
            return _safe_div(len(segment), max(s, 1e-3))

        tempo_slope = float(_kps(second) - _kps(first))

        # Key entropy (coarse IDs, not content)
        key_counts = Counter(e.key_id for e in evs)
        entropy_keys = _shannon_entropy(key_counts)

        # “Edit distance rate” proxy:
        # We approximate “editing friction” as backspace_rate * pause_after_bs_ms (scaled)
        # plus a small term for burstiness (stress can look like frantic bursts).
        edit_distance_rate = float(
            backspace_rate * (pause_after_bs_ms / 250.0) + 0.25 * burst_ratio
        )

        x = np.array(
            [
                kps_mean,
                kps_var,
                inter_key_cv,
                backspace_rate,
                edit_distance_rate,
                pause_after_bs_ms,
                pause_density,
                long_pause_ratio,
                burst_ratio,
                tempo_slope,
                entropy_keys,
                float(n),  # event count helps confidence calibration a bit
            ],
            dtype=np.float32,
        )

        return FeatureVector(x=x)


# ----------------------------
# Tiny classifier (swappable)
# ----------------------------


class TinyMLP3:
    """
    2-layer MLP: input -> hidden -> 3 classes
    Classes: [calm, animated, stressed]
    Weights can be loaded from .npz with keys: W1, b1, W2, b2
    """

    def __init__(
        self,
        input_dim: int = 12,
        hidden_dim: int = 8,
        weights_path: str = DEFAULT_WEIGHTS_PATH,
    ):
        self.input_dim = input_dim
        self.hidden_dim = hidden_dim
        self.weights_path = weights_path

        # Default: gentle, slightly conservative weights.
        rng = np.random.default_rng(7)
        self.W1 = (rng.standard_normal((hidden_dim, input_dim)) * 0.05).astype(
            np.float32
        )
        self.b1 = np.zeros((hidden_dim,), dtype=np.float32)
        self.W2 = (rng.standard_normal((3, hidden_dim)) * 0.05).astype(np.float32)
        self.b2 = np.zeros((3,), dtype=np.float32)

        self._loaded = False
        self._crc = "dev-default"

        self.try_load()

    def try_load(self) -> None:
        if not os.path.exists(self.weights_path):
            return
        try:
            data = np.load(self.weights_path)
            self.W1 = data["W1"].astype(np.float32)
            self.b1 = data["b1"].astype(np.float32)
            self.W2 = data["W2"].astype(np.float32)
            self.b2 = data["b2"].astype(np.float32)

            # Cheap CRC-ish fingerprint (stable enough for health checks)
            blob = np.concatenate([self.W1.ravel()[:128], self.W2.ravel()[:128]])
            crc = int(np.sum(np.abs(blob) * 1e6)) % 0xFFFFFF
            self._crc = f"{crc:06x}"
            self._loaded = True
        except Exception:
            # If weights are broken, stay alive with defaults.
            self._loaded = False
            self._crc = "weights-error"

    @property
    def model_crc(self) -> str:
        return self._crc

    def predict_proba(self, x: np.ndarray) -> np.ndarray:
        """
        x: shape (12,)
        returns: shape (3,) softmax probabilities
        """
        x = x.astype(np.float32)
        h = self.W1 @ x + self.b1
        h = np.maximum(h, 0.0)  # ReLU
        logits = self.W2 @ h + self.b2
        # softmax
        logits = logits - float(np.max(logits))
        exps = np.exp(logits)
        probs = exps / float(np.sum(exps) + 1e-9)
        return probs.astype(np.float32)


# ----------------------------
# Override (kick pedal) with decay
# ----------------------------


@dataclass
class OverrideState:
    factor0: float = 1.0
    start_ts: float = 0.0

    def active(self, now: float) -> bool:
        return (now - self.start_ts) < OVERRIDE_DURATION_SECONDS and self.factor0 != 1.0

    def factor(self, now: float) -> float:
        """
        Smoothly decays from factor0 to 1.0 over OVERRIDE_DURATION_SECONDS.
        Uses exponential-like curve that approaches 1 by end of duration.
        """
        if self.factor0 == 1.0:
            return 1.0
        t = max(0.0, now - self.start_ts)
        if t >= OVERRIDE_DURATION_SECONDS:
            return 1.0
        # Choose tau so exp(-duration/tau) ≈ 0.05
        tau = OVERRIDE_DURATION_SECONDS / 3.0
        decay = math.exp(-t / max(tau, 1e-6))
        return 1.0 + (self.factor0 - 1.0) * decay

    def source(self, now: float) -> str:
        if self.factor0 == 1.0:
            return "live"
        t = max(0.0, now - self.start_ts)
        if t >= OVERRIDE_DURATION_SECONDS:
            return "live"
        return "override" if t <= OVERRIDE_SOURCE_SECONDS else "decay"


# ----------------------------
# State engine (EWMA + caching)
# ----------------------------


class ECMEngine:
    def __init__(
        self,
        window_seconds: float = WINDOW_SECONDS_DEFAULT,
        db_path: str = DEFAULT_DB_PATH,
    ):
        self.window_seconds = float(window_seconds)
        self.ring = RingBuffer(max_seconds=self.window_seconds + 10.0)
        self.extractor = FeatureExtractor(window_seconds=self.window_seconds)
        self.classifier = TinyMLP3(
            input_dim=12, hidden_dim=8, weights_path=DEFAULT_WEIGHTS_PATH
        )

        self.override = OverrideState()

        # EWMA state
        self._ewma_x = np.zeros((12,), dtype=np.float32)
        self._ewma_initialized = False
        self._ewma_lock = threading.Lock()

        # last computed outputs (fast path for /now)
        self._last_now: Optional[NowOut] = None
        self._last_lock = threading.Lock()

        # labels DB
        self.db_path = db_path
        self._db_init()

        # background loop
        self._stop = threading.Event()
        self._thread = threading.Thread(
            target=self._run, name="ecm-engine", daemon=True
        )

    def start(self) -> None:
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        self._thread.join(timeout=1.0)

    def add_key_event(self, ts: float, key_id: str, is_backspace: bool) -> None:
        self.ring.add(KeyEvent(ts=ts, key_id=key_id, is_backspace=is_backspace))

    def set_override(self, factor: float) -> None:
        now = time.time()
        # Clamp factor to sane range to prevent nonsense
        factor = float(max(0.25, min(4.0, factor)))
        if abs(factor - 1.0) < 1e-9:
            # release
            self.override = OverrideState(factor0=1.0, start_ts=now)
        else:
            self.override = OverrideState(factor0=factor, start_ts=now)

    def label_slice(self, start_ts: float, end_ts: float, label: str) -> None:
        start_ts = float(start_ts)
        end_ts = float(end_ts)
        if end_ts <= start_ts:
            raise ValueError("end_ts must be > start_ts")

        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                "INSERT INTO labels(start_ts, end_ts, label, created_ts) VALUES (?, ?, ?, ?)",
                (start_ts, end_ts, label, time.time()),
            )
            conn.commit()

    def now(self) -> NowOut:
        # Fast path: serve cached result (updated in background loop)
        with self._last_lock:
            if self._last_now is not None:
                return self._last_now
        # If background hasn't run yet, compute once on-demand
        self._compute_once()
        with self._last_lock:
            return self._last_now  # type: ignore

    def health(self) -> HealthOut:
        return HealthOut(status="ok", model_crc=self.classifier.model_crc)

    # ---------- internals ----------

    def _db_init(self) -> None:
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS labels (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    start_ts REAL NOT NULL,
                    end_ts REAL NOT NULL,
                    label TEXT NOT NULL,
                    created_ts REAL NOT NULL
                )
                """
            )
            conn.commit()

    def _run(self) -> None:
        # Update loop ~10 Hz (cheap)
        while not self._stop.is_set():
            t0 = time.time()
            try:
                self._compute_once(now=t0)
            except Exception:
                # Keep running; ECM should fail soft.
                pass
            # 100ms cadence
            dt = time.time() - t0
            sleep_for = max(0.05, 0.10 - dt)
            time.sleep(sleep_for)

    def _compute_once(self, now: Optional[float] = None) -> None:
        now = time.time() if now is None else float(now)

        events = self.ring.snapshot(now=now)
        fv = self.extractor.compute(events=events, now=now)

        # EWMA update
        alpha = self._ewma_alpha(dt=0.10)  # loop cadence ~0.1s
        with self._ewma_lock:
            if not self._ewma_initialized:
                self._ewma_x = fv.x.copy()
                self._ewma_initialized = True
            else:
                self._ewma_x = (1.0 - alpha) * self._ewma_x + alpha * fv.x
            x_smooth = self._ewma_x.copy()

        # Classify
        probs = self.classifier.predict_proba(x_smooth)
        confidence = float(np.max(probs))

        # Map to valence (simple, interpretable projection)
        # calm -> slightly positive, animated -> positive, stressed -> negative
        calm, animated, stressed = float(probs[0]), float(probs[1]), float(probs[2])
        valence = calm * 0.25 + animated * 0.75 + stressed * (-0.85)
        valence = float(max(-1.0, min(1.0, valence)))

        # BPM mapping from kps_mean
        kps_mean = float(max(0.0, x_smooth[0]))
        bpm_live = int(round(self._kps_to_bpm(kps_mean)))
        # Temporal load estimation (segment 1)
        load = self._temporal_load(x_smooth, bpm_live)
        # Apply override factor (with decay)
        factor = self.override.factor(now)
        bpm_adj = int(round(max(BPM_MIN, min(BPM_MAX, bpm_live * factor))))

        inv = self._temporal_involution(load)
        bpm_adj = int(round(max(BPM_MIN, min(BPM_MAX, bpm_adj * float(inv["bpm_bias"])))))

        # tokens_per_minute mapping (advisory ceiling)
        # Keep it simple + bounded; downstream can interpret.
        tpm = int(round(self._bpm_to_tokens_per_minute(bpm_adj)))
        if inv.get("tpm_cap") is not None:
            tpm = min(tpm, int(inv["tpm_cap"]))

        source = self.override.source(now)

        out = NowOut(
            ts=now,
            bpm=bpm_adj,
            valence=valence,
            confidence=float(max(0.0, min(1.0, confidence))),
            tokens_per_minute=tpm,
            window_seconds=int(round(self.window_seconds)),
            source=source,
            tempo_mode=str(inv["mode"]),
        )
        with self._last_lock:
            self._last_now = out

    def _ewma_alpha(self, dt: float) -> float:
        # alpha for EWMA given half-life: alpha = 1 - exp(-ln(2) * dt / half_life)
        hl = EWMA_HALFLIFE_SECONDS
        return float(1.0 - math.exp(-math.log(2.0) * dt / max(hl, 1e-6)))

    @staticmethod
    def _kps_to_bpm(kps: float) -> float:
        # Map: 0 kps -> 60 bpm, 6 kps -> ~180 bpm
        bpm = 60.0 + 20.0 * min(max(kps, 0.0), 6.0)
        return max(BPM_MIN, min(BPM_MAX, bpm))

    @staticmethod
    def _bpm_to_tokens_per_minute(bpm: int) -> int:
        # Advisory: modest scaling, bounded.
        # 60 bpm -> 80 tpm, 180 bpm -> 200 tpm
        tpm = 80.0 + (bpm - 60) * (120.0 / 120.0)
        return int(max(60, min(240, round(tpm))))
    def _temporal_load(self, x_smooth: np.ndarray, bpm: int) -> float:
        """Estimate temporal pressure / overload risk (0.0–1.0)."""
        kps_mean = float(max(0.0, x_smooth[0]))
        burst_ratio = float(x_smooth[8])
        tempo_slope = float(x_smooth[9])

        bpm_norm = min(
            max((bpm - BPM_MIN) / (BPM_MAX - BPM_MIN), 0.0),
            1.0,
        )

        load = (
            0.45 * bpm_norm +
            0.30 * min(kps_mean / 6.0, 1.0) +
            0.15 * max(tempo_slope, 0.0) +
            0.10 * burst_ratio
        )

        return float(min(max(load, 0.0), 1.0))

    def _temporal_involution(self, load: float) -> dict:
        """Return regulation constraints based on temporal load."""
        if load >= 0.85:
            return {"mode": "rest", "tpm_cap": 60, "bpm_bias": 0.75}
        if load >= 0.60:
            return {"mode": "slow", "tpm_cap": 120, "bpm_bias": 0.90}
        return {"mode": "normal", "tpm_cap": None, "bpm_bias": 1.0}



# ----------------------------
# Optional key capture (pynput)
# ----------------------------


def start_keylogger(engine: ECMEngine) -> Optional[object]:
    """
    Starts a best-effort keylogger using pynput (if installed).
    Stores only coarse key IDs (NOT text), sufficient for entropy and backspace detection.
    """
    try:
        from pynput import keyboard  # type: ignore
    except Exception:
        return None

    def key_to_id(key) -> Tuple[str, bool]:
        # Backspace detection
        try:
            if key == keyboard.Key.backspace:
                return ("<BS>", True)
            if key == keyboard.Key.space:
                return ("<SP>", False)
            if key == keyboard.Key.enter:
                return ("<ENT>", False)
            if key == keyboard.Key.tab:
                return ("<TAB>", False)
            if key == keyboard.Key.esc:
                return ("<ESC>", False)
            # Coarse bucket for modifier keys
            if key in (keyboard.Key.shift, keyboard.Key.shift_l, keyboard.Key.shift_r):
                return ("<SHIFT>", False)
            if key in (keyboard.Key.ctrl, keyboard.Key.ctrl_l, keyboard.Key.ctrl_r):
                return ("<CTRL>", False)
            if key in (keyboard.Key.alt, keyboard.Key.alt_l, keyboard.Key.alt_r):
                return ("<ALT>", False)
        except Exception:
            pass

        # Printable character: do NOT store raw character; store a category
        try:
            ch = key.char  # type: ignore
            if ch is None:
                return ("<UNK>", False)
            if ch.isalpha():
                return ("<A>", False)
            if ch.isdigit():
                return ("<D>", False)
            # punctuation bucket
            return ("<P>", False)
        except Exception:
            return ("<UNK>", False)

    def on_press(key):
        ts = time.time()
        key_id, is_bs = key_to_id(key)
        engine.add_key_event(ts=ts, key_id=key_id, is_backspace=is_bs)

    listener = keyboard.Listener(on_press=on_press)
    listener.daemon = True
    listener.start()
    return listener


# ----------------------------
# FastAPI app
# ----------------------------

app = FastAPI(title="ECM", version="1.0", root_path="")

_engine: Optional[ECMEngine] = None
_keylog_listener: Optional[object] = None


def _ensure_api_engine() -> ECMEngine:
    global _engine, _keylog_listener
    if _engine is None:
        _engine = ECMEngine(
            window_seconds=WINDOW_SECONDS_DEFAULT,
            db_path=DEFAULT_DB_PATH,
        )
        _engine.start()
        _keylog_listener = start_keylogger(_engine)  # may be None
    return _engine


@app.on_event("startup")
def _startup_event():
    _ensure_api_engine()


@app.on_event("shutdown")
def _shutdown_event():
    global _engine, _keylog_listener
    if _keylog_listener is not None:
        try:
            _keylog_listener.stop()
        except Exception:
            pass
        _keylog_listener = None
    if _engine is not None:
        try:
            _engine.stop()
        except Exception:
            pass
        _engine = None


def _cors_headers(origin: Optional[str]) -> Dict[str, str]:
    if origin and any(origin.startswith(o) for o in LOCALHOST_ORIGINS):
        return {
            "Access-Control-Allow-Origin": origin,
            "Access-Control-Allow-Methods": "GET,PUT,POST,OPTIONS",
            "Access-Control-Allow-Headers": "Content-Type",
        }
    return {}


@app.options(f"{API_PREFIX}/now")
@app.options(f"{API_PREFIX}/override")
@app.options(f"{API_PREFIX}/label")
@app.options(f"{API_PREFIX}/health")
def cors_preflight(response: Response):
    # Minimal CORS preflight support
    return Response(status_code=204)


@app.get(f"{API_PREFIX}/now", response_model=NowOut)
def get_now(response: Response):
    engine = _ensure_api_engine()
    origin = response.headers.get(
        "origin"
    )  # FastAPI/Starlette doesn't expose request here; keep simple.
    # We can’t reliably read Origin without Request, but we can at least set permissive localhost CORS in dev.
    # If you care, switch to injecting `Request` and reading request.headers.get("origin").
    for k, v in _cors_headers("http://localhost").items():
        response.headers[k] = v
    return engine.now()


@app.put(f"{API_PREFIX}/override", response_model=NowOut)
def put_override(body: OverrideIn, response: Response):
    engine = _ensure_api_engine()
    for k, v in _cors_headers("http://localhost").items():
        response.headers[k] = v
    engine.set_override(body.factor)
    return engine.now()


@app.post(f"{API_PREFIX}/label", status_code=201)
def post_label(body: LabelIn, response: Response):
    engine = _ensure_api_engine()
    for k, v in _cors_headers("http://localhost").items():
        response.headers[k] = v
    engine.label_slice(body.start_ts, body.end_ts, body.label)
    return Response(status_code=201)


@app.get(f"{API_PREFIX}/health", response_model=HealthOut)
def get_health(response: Response):
    engine = _ensure_api_engine()
    for k, v in _cors_headers("http://localhost").items():
        response.headers[k] = v
    return engine.health()


# ----------------------------
# Main
# ----------------------------


def main() -> None:
    import uvicorn

    uvicorn.run(
        "ecm2:app",
        host="127.0.0.1",
        port=7321,
        log_level="warning",
        reload=False,
    )


if __name__ == "__main__":
    main()
