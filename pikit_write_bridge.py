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
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    return conn


def _get_doc(conn: sqlite3.Connection, doc_id: int) -> sqlite3.Row | None:
    return conn.execute(
        "SELECT id, title, body, created_at FROM documents WHERE id = ?",
        (doc_id,),
    ).fetchone()


def create_document(title: str, body: str, db_path: str | Path | None = None) -> dict[str, Any]:
    with _connect(db_path) as conn:
        cur = conn.execute(
            "INSERT INTO documents (title, body) VALUES (?, ?)",
            (title, body),
        )
        conn.commit()
        new_id = int(cur.lastrowid)
        row = _get_doc(conn, new_id)
        return {
            "status": "ok",
            "action": "create",
            "db_path": str(Path(db_path or DEFAULT_DB_PATH).expanduser().resolve()),
            "new_doc_id": new_id,
            "doc": dict(row) if row else None,
        }


def ask_insert(
    *,
    source_doc_id: int,
    selected_text: str,
    response_body: str,
    response_title: str = "AI Response",
    db_path: str | Path | None = None,
    sel_start: int | None = None,
    sel_end: int | None = None,
) -> dict[str, Any]:
    if not selected_text:
        raise ValueError("selected_text is required")

    with _connect(db_path) as conn:
        source = _get_doc(conn, source_doc_id)
        if not source:
            raise ValueError(f"Source doc not found: {source_doc_id}")

        source_body = source["body"]
        if source_body is None:
            source_body = ""
        if not isinstance(source_body, str):
            raise TypeError("Source document body is not plain text; ASK-style link insertion only supports text docs")

        cur = conn.execute(
            "INSERT INTO documents (title, body) VALUES (?, ?)",
            (response_title, response_body),
        )
        new_doc_id = int(cur.lastrowid)
        link_md = f"[{selected_text}](doc:{new_doc_id})"

        updated_body: str | None = None
        replacement_mode = "none"
        if (
            isinstance(sel_start, int)
            and isinstance(sel_end, int)
            and 0 <= sel_start < sel_end <= len(source_body)
        ):
            updated_body = source_body[:sel_start] + link_md + source_body[sel_end:]
            replacement_mode = "offsets"
        elif selected_text in source_body:
            updated_body = source_body.replace(selected_text, link_md, 1)
            replacement_mode = "substring"
        else:
            updated_body = source_body
            replacement_mode = "not_found"

        if updated_body != source_body:
            conn.execute(
                "UPDATE documents SET body = ? WHERE id = ?",
                (updated_body, source_doc_id),
            )

        conn.commit()

        created = _get_doc(conn, new_doc_id)
        updated_source = _get_doc(conn, source_doc_id)
        return {
            "status": "ok",
            "action": "ask",
            "db_path": str(Path(db_path or DEFAULT_DB_PATH).expanduser().resolve()),
            "source_doc_id": source_doc_id,
            "new_doc_id": new_doc_id,
            "replacement_mode": replacement_mode,
            "created_doc": dict(created) if created else None,
            "updated_source_doc": dict(updated_source) if updated_source else None,
        }


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description="Write-capable PiKit bridge for explicit document mutations")
    parser.add_argument("--db", default=str(DEFAULT_DB_PATH), help="Path to PiKit SQLite DB")
    parser.add_argument("--json", action="store_true", help="Output JSON")

    subparsers = parser.add_subparsers(dest="command", required=True)

    create_parser = subparsers.add_parser("create", help="Create a new document")
    create_parser.add_argument("--title", required=True)
    create_parser.add_argument("--body", help="Body text to store")
    create_parser.add_argument("--body-file", help="Read body text from file")

    ask_parser = subparsers.add_parser("ask", help="Create an AI Response doc and insert a green link into a source doc")
    ask_parser.add_argument("--source-doc", type=int, required=True, help="Source document ID to patch")
    ask_parser.add_argument("--selected-text", required=True, help="Selected text to replace with a doc link")
    ask_parser.add_argument("--response-title", default="AI Response")
    ask_parser.add_argument("--response-body", help="Response text to store in the new document")
    ask_parser.add_argument("--response-file", help="Read response text from file")
    ask_parser.add_argument("--sel-start", type=int)
    ask_parser.add_argument("--sel-end", type=int)

    args = parser.parse_args(argv)

    try:
        if args.command == "create":
            body = args.body
            if args.body_file:
                body = Path(args.body_file).read_text(encoding="utf-8")
            if body is None:
                raise ValueError("Provide --body or --body-file")
            result = create_document(args.title, body, args.db)
        elif args.command == "ask":
            response_body = args.response_body
            if args.response_file:
                response_body = Path(args.response_file).read_text(encoding="utf-8")
            if response_body is None:
                raise ValueError("Provide --response-body or --response-file")
            result = ask_insert(
                source_doc_id=args.source_doc,
                selected_text=args.selected_text,
                response_body=response_body,
                response_title=args.response_title,
                db_path=args.db,
                sel_start=args.sel_start,
                sel_end=args.sel_end,
            )
        else:
            raise ValueError(f"Unknown command: {args.command}")

        if args.json:
            print(json.dumps(result, indent=2, ensure_ascii=False))
        else:
            print(f"Action: {result['action']}")
            print(f"DB: {result['db_path']}")
            if result["action"] == "create":
                print(f"Created doc: {result['new_doc_id']}")
                print(f"Title: {result['doc']['title'] if result.get('doc') else ''}")
            else:
                print(f"Source doc: {result['source_doc_id']}")
                print(f"Created doc: {result['new_doc_id']}")
                print(f"Replacement mode: {result['replacement_mode']}")
                created = result.get("created_doc") or {}
                print(f"New title: {created.get('title', '')}")
        return 0
    except Exception as e:
        if getattr(args, "json", False):
            print(json.dumps({"status": "error", "error": str(e)}, indent=2, ensure_ascii=False), file=sys.stderr)
        else:
            print(f"Error: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
