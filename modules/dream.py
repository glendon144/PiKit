# dream.py
#
# PiKit Dream Processing Layer
#
# Purpose:
# - Maintain a separate SQLite database for provisional semantic processing
# - Observe session activity without blocking the main document database
# - Perform lightweight local extraction and consolidation
# - Produce a "session capsule" that can later be used by ASK or Memory Weave
#
# Notes:
# - This module does NOT call external LLM APIs
# - It is designed to be conservative and inexpensive
# - It is intended to be started/stopped by the UI Dream button

from __future__ import annotations

import os
import re
import json
import time
import queue
import sqlite3
import threading
import hashlib
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple


ISO_FMT = "%Y-%m-%d %H:%M:%S"


def now_str() -> str:
    return datetime.now().strftime(ISO_FMT)


def sha1_text(text: str) -> str:
    return hashlib.sha1(text.encode("utf-8", errors="ignore")).hexdigest()


@dataclass
class DreamEvent:
    event_type: str
    source_doc_id: Optional[int]
    content_snippet: str
    metadata: Optional[Dict[str, Any]] = None


class DreamDatabase:
    def __init__(self, db_path: str):
        self.db_path = db_path
        self._init_db()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self) -> None:
        conn = self._connect()
        cur = conn.cursor()

        cur.execute(
            """
        CREATE TABLE IF NOT EXISTS session_events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TEXT NOT NULL,
            event_type TEXT NOT NULL,
            source_doc_id INTEGER,
            content_snippet TEXT NOT NULL,
            content_hash TEXT NOT NULL,
            metadata_json TEXT,
            processed_flag INTEGER NOT NULL DEFAULT 0
        )
        """
        )

        cur.execute(
            """
        CREATE TABLE IF NOT EXISTS candidate_memories (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            memory_type TEXT NOT NULL,
            subject TEXT,
            predicate TEXT,
            object_text TEXT,
            confidence REAL NOT NULL DEFAULT 0.0,
            salience REAL NOT NULL DEFAULT 0.0,
            source_event_ids TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'candidate'
        )
        """
        )

        cur.execute(
            """
        CREATE TABLE IF NOT EXISTS topic_clusters (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            label TEXT NOT NULL UNIQUE,
            keywords_json TEXT NOT NULL,
            occurrence_count INTEGER NOT NULL DEFAULT 1,
            first_seen TEXT NOT NULL,
            last_seen TEXT NOT NULL,
            salience REAL NOT NULL DEFAULT 0.0
        )
        """
        )

        cur.execute(
            """
        CREATE TABLE IF NOT EXISTS open_loops (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            description TEXT NOT NULL,
            related_doc_ids TEXT NOT NULL,
            priority REAL NOT NULL DEFAULT 0.0,
            confidence REAL NOT NULL DEFAULT 0.0,
            resolved_flag INTEGER NOT NULL DEFAULT 0
        )
        """
        )

        cur.execute(
            """
        CREATE TABLE IF NOT EXISTS session_capsules (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            created_at TEXT NOT NULL,
            scope TEXT NOT NULL,
            capsule_text TEXT NOT NULL,
            source_event_ids TEXT NOT NULL,
            expiry_time TEXT
        )
        """
        )

        cur.execute(
            """
        CREATE TABLE IF NOT EXISTS promotion_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TEXT NOT NULL,
            candidate_memory_id INTEGER NOT NULL,
            action TEXT NOT NULL,
            target_doc_id INTEGER,
            notes TEXT
        )
        """
        )

        cur.execute(
            """
        CREATE INDEX IF NOT EXISTS idx_session_events_processed
        ON session_events(processed_flag, timestamp)
        """
        )

        cur.execute(
            """
        CREATE INDEX IF NOT EXISTS idx_candidate_memories_status
        ON candidate_memories(status, updated_at)
        """
        )

        cur.execute(
            """
        CREATE INDEX IF NOT EXISTS idx_open_loops_resolved
        ON open_loops(resolved_flag, updated_at)
        """
        )

        conn.commit()
        conn.close()

    def add_event(self, event: DreamEvent) -> None:
        conn = self._connect()
        cur = conn.cursor()
        cur.execute(
            """
        INSERT INTO session_events (
            timestamp, event_type, source_doc_id, content_snippet,
            content_hash, metadata_json, processed_flag
        ) VALUES (?, ?, ?, ?, ?, ?, 0)
        """,
            (
                now_str(),
                event.event_type,
                event.source_doc_id,
                event.content_snippet,
                sha1_text(event.content_snippet),
                json.dumps(event.metadata or {}),
            ),
        )
        conn.commit()
        conn.close()

    def fetch_unprocessed_events(self, limit: int = 50) -> List[sqlite3.Row]:
        conn = self._connect()
        cur = conn.cursor()
        cur.execute(
            """
        SELECT * FROM session_events
        WHERE processed_flag = 0
        ORDER BY id ASC
        LIMIT ?
        """,
            (limit,),
        )
        rows = cur.fetchall()
        conn.close()
        return rows

    def mark_events_processed(self, event_ids: List[int]) -> None:
        if not event_ids:
            return
        conn = self._connect()
        cur = conn.cursor()
        placeholders = ",".join("?" for _ in event_ids)
        cur.execute(
            f"""
        UPDATE session_events
        SET processed_flag = 1
        WHERE id IN ({placeholders})
        """,
            event_ids,
        )
        conn.commit()
        conn.close()

    def upsert_topic_cluster(
        self, label: str, keywords: List[str], salience_delta: float
    ) -> None:
        conn = self._connect()
        cur = conn.cursor()

        cur.execute("SELECT * FROM topic_clusters WHERE label = ?", (label,))
        row = cur.fetchone()

        if row:
            merged_keywords = sorted(
                set(json.loads(row["keywords_json"])) | set(keywords)
            )
            new_count = row["occurrence_count"] + 1
            new_salience = float(row["salience"]) + salience_delta
            cur.execute(
                """
            UPDATE topic_clusters
            SET keywords_json = ?, occurrence_count = ?, last_seen = ?, salience = ?
            WHERE id = ?
            """,
                (
                    json.dumps(merged_keywords),
                    new_count,
                    now_str(),
                    new_salience,
                    row["id"],
                ),
            )
        else:
            cur.execute(
                """
            INSERT INTO topic_clusters (
                label, keywords_json, occurrence_count, first_seen, last_seen, salience
            ) VALUES (?, ?, 1, ?, ?, ?)
            """,
                (
                    label,
                    json.dumps(sorted(set(keywords))),
                    now_str(),
                    now_str(),
                    salience_delta,
                ),
            )

        conn.commit()
        conn.close()

    def add_candidate_memory(
        self,
        memory_type: str,
        subject: str,
        predicate: str,
        object_text: str,
        confidence: float,
        salience: float,
        source_event_ids: List[int],
    ) -> None:
        conn = self._connect()
        cur = conn.cursor()
        cur.execute(
            """
        INSERT INTO candidate_memories (
            created_at, updated_at, memory_type, subject, predicate, object_text,
            confidence, salience, source_event_ids, status
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'candidate')
        """,
            (
                now_str(),
                now_str(),
                memory_type,
                subject,
                predicate,
                object_text,
                confidence,
                salience,
                json.dumps(source_event_ids),
            ),
        )
        conn.commit()
        conn.close()

    def add_or_update_open_loop(
        self,
        description: str,
        related_doc_ids: List[int],
        priority: float,
        confidence: float,
    ) -> None:
        conn = self._connect()
        cur = conn.cursor()

        cur.execute(
            """
        SELECT * FROM open_loops
        WHERE resolved_flag = 0 AND description = ?
        """,
            (description,),
        )
        row = cur.fetchone()

        if row:
            old_docs = set(json.loads(row["related_doc_ids"]))
            new_docs = sorted(old_docs | set(related_doc_ids))
            cur.execute(
                """
            UPDATE open_loops
            SET updated_at = ?, related_doc_ids = ?, priority = ?, confidence = ?
            WHERE id = ?
            """,
                (
                    now_str(),
                    json.dumps(new_docs),
                    max(priority, row["priority"]),
                    max(confidence, row["confidence"]),
                    row["id"],
                ),
            )
        else:
            cur.execute(
                """
            INSERT INTO open_loops (
                created_at, updated_at, description, related_doc_ids,
                priority, confidence, resolved_flag
            ) VALUES (?, ?, ?, ?, ?, ?, 0)
            """,
                (
                    now_str(),
                    now_str(),
                    description,
                    json.dumps(sorted(set(related_doc_ids))),
                    priority,
                    confidence,
                ),
            )

        conn.commit()
        conn.close()

    def store_session_capsule(
        self,
        scope: str,
        capsule_text: str,
        source_event_ids: List[int],
        expiry_hours: int = 72,
    ) -> None:
        expiry_time = (datetime.now() + timedelta(hours=expiry_hours)).strftime(ISO_FMT)
        conn = self._connect()
        cur = conn.cursor()
        cur.execute(
            """
        INSERT INTO session_capsules (
            created_at, scope, capsule_text, source_event_ids, expiry_time
        ) VALUES (?, ?, ?, ?, ?)
        """,
            (now_str(), scope, capsule_text, json.dumps(source_event_ids), expiry_time),
        )
        conn.commit()
        conn.close()

    def get_top_topics(self, limit: int = 10) -> List[sqlite3.Row]:
        conn = self._connect()
        cur = conn.cursor()
        cur.execute(
            """
        SELECT * FROM topic_clusters
        ORDER BY salience DESC, occurrence_count DESC, last_seen DESC
        LIMIT ?
        """,
            (limit,),
        )
        rows = cur.fetchall()
        conn.close()
        return rows

    def get_open_loops(self, limit: int = 10) -> List[sqlite3.Row]:
        conn = self._connect()
        cur = conn.cursor()
        cur.execute(
            """
        SELECT * FROM open_loops
        WHERE resolved_flag = 0
        ORDER BY priority DESC, updated_at DESC
        LIMIT ?
        """,
            (limit,),
        )
        rows = cur.fetchall()
        conn.close()
        return rows

    def get_recent_candidate_memories(self, limit: int = 15) -> List[sqlite3.Row]:
        conn = self._connect()
        cur = conn.cursor()
        cur.execute(
            """
        SELECT * FROM candidate_memories
        WHERE status = 'candidate'
        ORDER BY salience DESC, confidence DESC, updated_at DESC
        LIMIT ?
        """,
            (limit,),
        )
        rows = cur.fetchall()
        conn.close()
        return rows

    def get_latest_capsule(self) -> Optional[str]:
        conn = self._connect()
        cur = conn.cursor()
        cur.execute(
            """
        SELECT capsule_text FROM session_capsules
        ORDER BY created_at DESC
        LIMIT 1
        """
        )
        row = cur.fetchone()
        conn.close()
        return row["capsule_text"] if row else None


class LocalExtractor:
    """
    A deliberately simple local extractor.
    Version 1 is based on recurrence, phrase detection, and lightweight heuristics.
    """

    PREFERENCE_PATTERNS = [
        r"\bI prefer\b(.+)",
        r"\bI like\b(.+)",
        r"\bI want\b(.+)",
        r"\bI need\b(.+)",
        r"\bremember\b(.+)",
    ]

    OPEN_LOOP_PATTERNS = [
        r"\bTODO\b[:\- ](.+)",
        r"\bneed to\b(.+)",
        r"\bshould\b(.+)",
        r"\bnext task\b[:\- ](.+)",
        r"\bcome back to\b(.+)",
    ]

    ENTITY_PATTERN = re.compile(r"\b[A-Z][A-Za-z0-9_\-]{2,}\b")

    def extract(self, text: str) -> Dict[str, Any]:
        text_clean = " ".join(text.split())
        lower = text_clean.lower()

        topics = self._extract_topics(text_clean)
        memories = self._extract_candidate_memories(text_clean)
        open_loops = self._extract_open_loops(text_clean)

        salience = self._compute_salience(text_clean, topics, memories, open_loops)

        return {
            "topics": topics,
            "memories": memories,
            "open_loops": open_loops,
            "salience": salience,
            "text_clean": text_clean,
            "lower": lower,
        }

    def _extract_topics(self, text: str) -> List[str]:
        entities = self.ENTITY_PATTERN.findall(text)
        topics = [e for e in entities if len(e) > 2]

        # Also add a few repeated lower-case words if they look strong
        words = re.findall(r"\b[a-zA-Z][a-zA-Z0-9_\-]{3,}\b", text.lower())
        counts: Dict[str, int] = {}
        stop = {
            "this",
            "that",
            "with",
            "from",
            "have",
            "will",
            "would",
            "there",
            "their",
            "about",
            "which",
            "into",
            "should",
            "could",
            "while",
            "where",
            "being",
        }
        for w in words:
            if w in stop:
                continue
            counts[w] = counts.get(w, 0) + 1

        repeated = [w for w, c in counts.items() if c >= 2]
        combined = sorted(set(topics + repeated))
        return combined[:12]

    def _extract_candidate_memories(
        self, text: str
    ) -> List[Tuple[str, str, str, str, float]]:
        memories = []

        for pat in self.PREFERENCE_PATTERNS:
            for match in re.finditer(pat, text, re.IGNORECASE):
                fragment = match.group(0).strip()
                memories.append(("preference", "user", "expressed", fragment, 0.75))

        if "project" in text.lower():
            memories.append(("project", "session", "mentions", text[:180], 0.60))

        if "sqlite" in text.lower():
            memories.append(
                (
                    "technical_fact",
                    "session",
                    "mentions",
                    "SQLite is relevant in current work.",
                    0.65,
                )
            )

        return memories[:8]

    def _extract_open_loops(self, text: str) -> List[Tuple[str, float]]:
        loops = []
        for pat in self.OPEN_LOOP_PATTERNS:
            for match in re.finditer(pat, text, re.IGNORECASE):
                desc = match.group(0).strip()
                loops.append((desc[:220], 0.72))

        if "let's write" in text.lower():
            loops.append(("Implementation work has been requested.", 0.80))

        return loops[:6]

    def _compute_salience(
        self, text: str, topics: List[str], memories: List[Any], open_loops: List[Any]
    ) -> float:
        base = min(len(text) / 300.0, 1.0) * 0.25
        base += min(len(topics) * 0.05, 0.30)
        base += min(len(memories) * 0.10, 0.25)
        base += min(len(open_loops) * 0.10, 0.20)
        return round(min(base, 1.0), 3)


class DreamProcessor:
    def __init__(
        self,
        dreams_db_path: str,
        main_db_reader=None,
        idle_seconds: int = 300,
        loop_sleep_seconds: int = 3,
    ):
        self.db = DreamDatabase(dreams_db_path)
        self.extractor = LocalExtractor()
        self.main_db_reader = main_db_reader  # optional callback or helper object
        self.idle_seconds = idle_seconds
        self.loop_sleep_seconds = loop_sleep_seconds

        self._event_queue: "queue.Queue[DreamEvent]" = queue.Queue()
        self._running = False
        self._authorized = False
        self._worker_thread: Optional[threading.Thread] = None
        self._last_activity_ts = time.time()
        self._lock = threading.Lock()

    def authorize(self, enabled: bool) -> None:
        with self._lock:
            self._authorized = enabled
            self._last_activity_ts = time.time()

    def is_authorized(self) -> bool:
        with self._lock:
            return self._authorized

    def start(self) -> None:
        if self._running:
            return
        self._running = True
        self._worker_thread = threading.Thread(target=self._run_loop, daemon=True)
        self._worker_thread.start()

    def stop(self) -> None:
        self._running = False
        if self._worker_thread and self._worker_thread.is_alive():
            self._worker_thread.join(timeout=2.0)

    def note_user_activity(self) -> None:
        with self._lock:
            self._last_activity_ts = time.time()

    def add_event(
        self,
        event_type: str,
        content_snippet: str,
        source_doc_id: Optional[int] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> None:
        self.note_user_activity()
        self._event_queue.put(
            DreamEvent(
                event_type=event_type,
                source_doc_id=source_doc_id,
                content_snippet=content_snippet[:4000],
                metadata=metadata or {},
            )
        )

    def force_dream_pass(self) -> str:
        self._flush_event_queue_to_db()
        self._process_unprocessed_events()
        capsule = self._build_session_capsule()
        return capsule

    def get_latest_capsule(self) -> Optional[str]:
        return self.db.get_latest_capsule()

    def _run_loop(self) -> None:
        while self._running:
            try:
                self._flush_event_queue_to_db()
                self._process_unprocessed_events()

                if self.is_authorized() and self._user_idle_long_enough():
                    self._build_session_capsule()
                    self._promote_strong_candidates_stub()
                    # Once a dream pass runs, require renewed inactivity
                    self.note_user_activity()

            except Exception as exc:
                print(f"[DreamProcessor] Error: {exc}")

            time.sleep(self.loop_sleep_seconds)

    def _flush_event_queue_to_db(self) -> None:
        flushed = 0
        while not self._event_queue.empty():
            try:
                event = self._event_queue.get_nowait()
            except queue.Empty:
                break
            self.db.add_event(event)
            flushed += 1

    def _process_unprocessed_events(self) -> None:
        rows = self.db.fetch_unprocessed_events(limit=50)
        if not rows:
            return

        processed_ids: List[int] = []

        for row in rows:
            event_id = int(row["id"])
            doc_id = row["source_doc_id"]
            text = row["content_snippet"]

            extracted = self.extractor.extract(text)
            salience = extracted["salience"]

            for topic in extracted["topics"]:
                self.db.upsert_topic_cluster(
                    topic, [topic], salience_delta=0.05 + salience
                )

            for mem_type, subject, predicate, obj_text, confidence in extracted[
                "memories"
            ]:
                self.db.add_candidate_memory(
                    memory_type=mem_type,
                    subject=subject,
                    predicate=predicate,
                    object_text=obj_text,
                    confidence=confidence,
                    salience=salience,
                    source_event_ids=[event_id],
                )

            for loop_desc, confidence in extracted["open_loops"]:
                related_docs = [doc_id] if doc_id is not None else []
                self.db.add_or_update_open_loop(
                    description=loop_desc,
                    related_doc_ids=related_docs,
                    priority=salience,
                    confidence=confidence,
                )

            processed_ids.append(event_id)

        self.db.mark_events_processed(processed_ids)

    def _user_idle_long_enough(self) -> bool:
        with self._lock:
            elapsed = time.time() - self._last_activity_ts
        return elapsed >= self.idle_seconds

    def _build_session_capsule(self) -> str:
        topics = self.db.get_top_topics(limit=8)
        loops = self.db.get_open_loops(limit=6)
        memories = self.db.get_recent_candidate_memories(limit=8)

        lines = []
        lines.append("Dream Capsule")
        lines.append(f"Generated: {now_str()}")
        lines.append("")

        if topics:
            lines.append("Top topics:")
            for row in topics:
                lines.append(
                    f"- {row['label']} (count={row['occurrence_count']}, salience={row['salience']:.2f})"
                )
            lines.append("")

        if memories:
            lines.append("Candidate memories:")
            for row in memories:
                lines.append(
                    f"- [{row['memory_type']}] {row['object_text']} "
                    f"(confidence={row['confidence']:.2f}, salience={row['salience']:.2f})"
                )
            lines.append("")

        if loops:
            lines.append("Open loops:")
            for row in loops:
                lines.append(
                    f"- {row['description']} "
                    f"(priority={row['priority']:.2f}, confidence={row['confidence']:.2f})"
                )
            lines.append("")

        if self.main_db_reader is not None:
            try:
                main_context = self.main_db_reader()
                if main_context:
                    lines.append("Main DB context hint:")
                    lines.append(main_context[:400])
                    lines.append("")
            except Exception as exc:
                lines.append(f"Main DB context hint unavailable: {exc}")
                lines.append("")

        capsule_text = "\n".join(lines).strip()
        self.db.store_session_capsule(
            scope="current_session", capsule_text=capsule_text, source_event_ids=[]
        )
        return capsule_text

    def _promote_strong_candidates_stub(self) -> None:
        """
        Placeholder for version 2.
        In a future step, this can write durable memories into the main DB.
        For now, the Dreams DB is intentionally provisional.
        """
        return
