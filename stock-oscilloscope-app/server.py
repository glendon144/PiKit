"""Serve the stock oscilloscope and proxy Finnhub quotes.

Set FINNHUB_API_KEY before starting this process. The key remains on the
server and is never sent to the browser.
"""

from __future__ import annotations

import json
import os
import re
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from flask import Flask, jsonify, send_from_directory

APP_DIR = Path(__file__).resolve().parent
FINNHUB_URL = "https://finnhub.io/api/v1/quote"
CACHE_SECONDS = 30
SYMBOL_RE = re.compile(r"^[A-Z0-9.-]{1,8}$")

app = Flask(__name__, static_folder=str(APP_DIR), static_url_path="")
_quote_cache: dict[str, tuple[float, dict]] = {}
_cache_lock = threading.Lock()


def _fetch_finnhub_quote(symbol: str) -> dict:
    api_key = os.environ.get("FINNHUB_API_KEY", "").strip()
    if not api_key:
        raise RuntimeError("FINNHUB_API_KEY is not configured")

    url = f"{FINNHUB_URL}?{urlencode({'symbol': symbol, 'token': api_key})}"
    request = Request(url, headers={"Accept": "application/json", "User-Agent": "PiKit-Market-Scope/1.0"})

    with urlopen(request, timeout=8) as response:
        payload = json.load(response)

    price = float(payload.get("c") or 0)
    if price <= 0:
        raise ValueError(f"No quote is available for {symbol}")

    market_timestamp = int(payload.get("t") or 0)
    market_time = (
        datetime.fromtimestamp(market_timestamp, tz=timezone.utc).isoformat()
        if market_timestamp
        else None
    )

    return {
        "symbol": symbol,
        "price": price,
        "change": float(payload.get("d") or 0),
        "percentChange": float(payload.get("dp") or 0),
        "previousClose": float(payload.get("pc") or 0),
        "marketTime": market_time,
        "receivedAt": datetime.now(timezone.utc).isoformat(),
        "stale": False,
    }


def _cached_quote(symbol: str) -> tuple[dict | None, bool]:
    with _cache_lock:
        entry = _quote_cache.get(symbol)

    if not entry:
        return None, False

    stored_at, quote = entry
    return dict(quote), time.monotonic() - stored_at < CACHE_SECONDS


@app.get("/")
def index():
    return send_from_directory(APP_DIR, "index.html")


@app.get("/api/health")
def health():
    return jsonify(
        {
            "ok": True,
            "provider": "Finnhub",
            "apiKeyConfigured": bool(os.environ.get("FINNHUB_API_KEY", "").strip()),
            "cacheSeconds": CACHE_SECONDS,
        }
    )


@app.get("/api/quote/<raw_symbol>")
def quote(raw_symbol: str):
    symbol = raw_symbol.strip().upper()
    if not SYMBOL_RE.fullmatch(symbol):
        return jsonify(error="Ticker must contain 1–8 letters, numbers, dots, or hyphens."), 400

    cached, fresh = _cached_quote(symbol)
    if fresh:
        return jsonify(cached)

    try:
        current = _fetch_finnhub_quote(symbol)
    except (RuntimeError, ValueError, HTTPError, URLError, TimeoutError) as error:
        if cached:
            cached["stale"] = True
            cached["warning"] = str(error)
            return jsonify(cached)
        return jsonify(error=str(error)), 503

    with _cache_lock:
        _quote_cache[symbol] = (time.monotonic(), current)

    return jsonify(current)


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=int(os.environ.get("PORT", "4173")), debug=False)
