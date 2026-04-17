#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from pathlib import Path
from typing import Any

DEFAULT_DB_PATH = Path(__file__).resolve().parent / "storage" / "documents.db"


def _connect(db_path: str | Path | None = None) -> sqlite3.Connection:
    path = Path(db_path or DEFAULT_DB_PATH).expanduser().resolve()
    if not path.exists():
        raise FileNotFoundError(f"PiKit database not found: {path}")
    conn = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    return conn


def _preview(text: Any, limit: int = 180) -> str:
    if text is None:
        return ""
    if isinstance(text, bytes):
        return f"[{len(text)} bytes binary]"
    cleaned = str(text).replace("\r", " ").replace("\n", " ").strip()
    return cleaned[:limit] + ("…" if len(cleaned) > limit else "")


def pikit_stats(db_path: str | Path | None = None) -> dict[str, Any]:
    with _connect(db_path) as conn:
        total = conn.execute("SELECT COUNT(*) FROM documents").fetchone()[0]
        latest = conn.execute(
            "SELECT id, title, created_at FROM documents ORDER BY id DESC LIMIT 5"
        ).fetchall()
        return {
            "db_path": str(Path(db_path or DEFAULT_DB_PATH).expanduser().resolve()),
            "total_documents": total,
            "latest": [dict(row) for row in latest],
        }


def pikit_list(limit: int = 10, db_path: str | Path | None = None) -> list[dict[str, Any]]:
    with _connect(db_path) as conn:
        rows = conn.execute(
            "SELECT id, title, body, created_at FROM documents ORDER BY id DESC LIMIT ?",
            (limit,),
        ).fetchall()
        return [
            {
                "id": row["id"],
                "title": row["title"],
                "created_at": row["created_at"],
                "preview": _preview(row["body"]),
            }
            for row in rows
        ]


def pikit_view(doc_id: int, db_path: str | Path | None = None) -> dict[str, Any] | None:
    with _connect(db_path) as conn:
        row = conn.execute(
            "SELECT id, title, body, created_at FROM documents WHERE id = ?",
            (doc_id,),
        ).fetchone()
        if not row:
            return None
        return dict(row)


def pikit_search(query: str, limit: int = 5, db_path: str | Path | None = None) -> list[dict[str, Any]]:
    q = f"%{query}%"
    with _connect(db_path) as conn:
        rows = conn.execute(
            """
            SELECT id, title, body, created_at,
                   CASE
                     WHEN lower(title) LIKE lower(?) THEN 2
                     ELSE 1
                   END AS rank
            FROM documents
            WHERE lower(title) LIKE lower(?) OR lower(body) LIKE lower(?)
            ORDER BY rank DESC, id DESC
            LIMIT ?
            """,
            (q, q, q, limit),
        ).fetchall()
        return [
            {
                "id": row["id"],
                "title": row["title"],
                "created_at": row["created_at"],
                "preview": _preview(row["body"]),
            }
            for row in rows
        ]


def _print(value: Any, as_json: bool = False) -> None:
    if as_json:
        print(json.dumps(value, indent=2, ensure_ascii=False))
        return

    if isinstance(value, dict) and {"db_path", "total_documents", "latest"}.issubset(value.keys()):
        print(f"DB: {value['db_path']}")
        print(f"Total documents: {value['total_documents']}")
        print("Latest:")
        for row in value["latest"]:
            print(f"  {row['id']}: {row['title']} ({row['created_at']})")
        return

    if isinstance(value, list):
        if not value:
            print("No results.")
            return
        for row in value:
            print(f"--- {row['id']}: {row['title']} ({row['created_at']}) ---")
            print(row.get("preview", ""))
            print()
        return

    if isinstance(value, dict):
        print(f"ID: {value['id']}")
        print(f"Title: {value['title']}")
        print(f"Created: {value['created_at']}")
        print()
        print(value.get("body", ""))
        return

    print(value)


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Read-only PiKit query bridge.")
    parser.add_argument("--db", default=str(DEFAULT_DB_PATH), help="Path to PiKit SQLite DB")
    parser.add_argument("--json", action="store_true", help="Print JSON output")
    subs = parser.add_subparsers(dest="command", required=True)

    subs.add_parser("stats")

    list_cmd = subs.add_parser("list")
    list_cmd.add_argument("--limit", type=int, default=10)

    view_cmd = subs.add_parser("view")
    view_cmd.add_argument("doc_id", type=int)

    search_cmd = subs.add_parser("search")
    search_cmd.add_argument("query")
    search_cmd.add_argument("--limit", type=int, default=5)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)

    if args.command == "stats":
        result = pikit_stats(args.db)
    elif args.command == "list":
        result = pikit_list(limit=args.limit, db_path=args.db)
    elif args.command == "view":
        result = pikit_view(args.doc_id, db_path=args.db)
        if result is None:
            print(f"Document {args.doc_id} not found.")
            return 1
    elif args.command == "search":
        result = pikit_search(args.query, limit=args.limit, db_path=args.db)
    else:  # pragma: no cover
        parser.error(f"Unknown command: {args.command}")
        return 2

    _print(result, as_json=args.json)
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"Error: {exc}", file=sys.stderr)
        raise SystemExit(1)
