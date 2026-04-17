# modules/flask_server.py
import os
import sys
import json
import re
import base64
import mimetypes
import traceback
import secrets
import sqlite3
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Union
from urllib.parse import urlencode, quote

DATA_DIR = Path(__file__).parent.parent / "exported_docs"
SHARE_DIR = DATA_DIR / "_shares"
ASSETS_DIR = DATA_DIR / "assets"  # optional: holds *.b64 files
TOKEN_FILE = Path(__file__).parent.parent / "storage" / "pikit_api_token.txt"
DEFAULT_CERT = Path(__file__).parent.parent / "storage" / "pikit.crt"
DEFAULT_KEY = Path(__file__).parent.parent / "storage" / "pikit.key"
DB_PATH = Path(os.getenv("PIKIT_DB_PATH", str(Path(__file__).parent.parent / "storage" / "documents.db"))).expanduser().resolve()

# -------------------- utils --------------------

def _s(val: Any, fallback: str = "") -> str:
    if val is None:
        return fallback
    try:
        if isinstance(val, (str, int, float, bool)):
            return str(val)
        if isinstance(val, (dict, list, tuple, set)):
            return json.dumps(val, ensure_ascii=False)
        if isinstance(val, bytes):
            return f"<{len(val)} bytes>"
        return str(val)
    except Exception:
        return fallback


def _load_json(path: Path) -> Optional[Union[dict, list]]:
    try:
        with path.open(encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        print(f"[flask_server] Skipping bad JSON: {path} ({e})", file=sys.stderr)
        return None


def _iter_docs() -> Iterable[Dict[str, Any]]:
    if not DATA_DIR.exists():
        return []
    items: List[Dict[str, Any]] = []

    docs_file = DATA_DIR / "docs.json"
    if docs_file.exists():
        root = _load_json(docs_file)
        if isinstance(root, dict):
            items.append(root)
        elif isinstance(root, list):
            items.extend([d for d in root if isinstance(d, dict)])

    for file_path in sorted(DATA_DIR.glob("*.json")):
        if file_path.name == "docs.json":
            continue
        obj = _load_json(file_path)
        if obj is None:
            continue
        doc_id = file_path.stem
        if isinstance(obj, list):
            doc = next((d for d in obj if _s(d.get("id")) == doc_id), None)
        elif isinstance(obj, dict):
            doc = obj
            doc.setdefault("id", doc_id)
        else:
            doc = None
        if isinstance(doc, dict):
            items.append(doc)

    return items


def _find_doc(doc_id: str) -> Optional[Dict[str, Any]]:
    if not DATA_DIR.exists():
        return None
    fp = DATA_DIR / f"{doc_id}.json"
    if fp.exists():
        obj = _load_json(fp)
        if isinstance(obj, dict):
            obj.setdefault("id", doc_id)
            return obj
        if isinstance(obj, list):
            return next((d for d in obj if _s(d.get("id")) == doc_id), None)
    root = _load_json(DATA_DIR / "docs.json")
    if isinstance(root, dict):
        return root if _s(root.get("id")) == doc_id else None
    if isinstance(root, list):
        return next((d for d in root if _s(d.get("id")) == doc_id), None)
    return None


def _load_share(share_id: str) -> Optional[Dict[str, Any]]:
    fp = SHARE_DIR / f"{share_id}.json"
    obj = _load_json(fp)
    return obj if isinstance(obj, dict) else None


def _is_image_dict(d: Dict[str, Any]) -> bool:
    mime = _s(d.get("mime"))
    data_b64 = d.get("data_base64")
    file_ref = _s(d.get("file"))
    return mime.startswith("image/") and (isinstance(data_b64, str) or file_ref.endswith(".b64"))


def _collect_images(doc: Dict[str, Any]) -> List[Dict[str, Any]]:
    imgs: List[Dict[str, Any]] = []

    def add_img(d: Dict[str, Any]):
        if not isinstance(d, dict):
            return
        if _is_image_dict(d):
            imgs.append(
                {
                    "mime": _s(d.get("mime"), "image/png"),
                    "data_base64": d.get("data_base64"),
                    "file": _s(d.get("file")),
                    "alt": _s(d.get("alt")),
                    "caption": _s(d.get("caption")),
                }
            )

    if isinstance(doc.get("images"), list):
        for it in doc["images"]:
            add_img(it)
    if isinstance(doc.get("attachments"), list):
        for it in doc["attachments"]:
            if isinstance(it, dict) and _s(it.get("kind")) == "image":
                add_img(it)
    return imgs


def _data_uri_or_asset(img: Dict[str, Any]) -> Optional[str]:
    mime = _s(img.get("mime"), "image/png")
    b64 = img.get("data_base64")
    file_ref = _s(img.get("file"))
    if isinstance(b64, str) and b64.strip():
        return f"data:{mime};base64,{b64}"
    if file_ref:
        return f"/asset/{file_ref}"
    return None


def _guess_mime_from_filename(name: str) -> str:
    if name.lower().endswith(".b64"):
        name = name[:-4]
    mt, _ = mimetypes.guess_type(name)
    return mt or "application/octet-stream"


def _smiley_data_uri() -> str:
    svg = (
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 64 64">'
        '<circle cx="32" cy="32" r="30" fill="#f4f4f4" stroke="#ddd"/>'
        '<circle cx="22" cy="26" r="4" fill="#666"/><circle cx="42" cy="26" r="4" fill="#666"/>'
        '<path d="M20 40 q12 10 24 0" stroke="#666" stroke-width="3" fill="none" stroke-linecap="round"/>'
        '</svg>'
    )
    b64 = base64.b64encode(svg.encode("utf-8")).decode("ascii")
    return f"data:image/svg+xml;base64,{b64}"


def _looks_like_html(text: str) -> bool:
    return bool(re.search(r"<(html|head|body|div|p|h\d|ul|ol|li|span|article|section|img|a|table|pre)\b", text, re.I))


def _load_api_token() -> Optional[str]:
    token = os.environ.get("PIKIT_API_TOKEN")
    if token:
        token = token.strip()
        if token:
            return token
    if TOKEN_FILE.exists():
        try:
            token = TOKEN_FILE.read_text(encoding="utf-8").strip()
            return token or None
        except Exception as e:
            print(f"[flask_server] Could not read token file {TOKEN_FILE}: {e}", file=sys.stderr)
    return None


def _preview_text(doc: Dict[str, Any], limit: int = 200) -> str:
    raw = doc.get("description")
    if raw is None:
        raw = doc.get("body", "")
    return _s(raw).replace("\n", " ").replace("\r", " ")[:limit]


def _doc_summary(doc: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "id": _s(doc.get("id")),
        "title": _s(doc.get("title")),
        "description": _preview_text(doc),
        "has_image": bool(_collect_images(doc)),
    }


def _db_connect() -> sqlite3.Connection:
    if not DB_PATH.exists():
        raise FileNotFoundError(f"PiKit database not found: {DB_PATH}")
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def _db_get_doc(conn: sqlite3.Connection, doc_id: int) -> sqlite3.Row | None:
    return conn.execute(
        "SELECT id, title, body, created_at FROM documents WHERE id = ?",
        (doc_id,),
    ).fetchone()


def _coerce_int(value: Any, name: str) -> int:
    try:
        return int(value)
    except Exception as e:
        raise ValueError(f"Invalid {name}: {value!r}") from e


def _ask_insert_db(
    *,
    source_doc_id: int,
    selected_text: str,
    response_body: str,
    response_title: str = "AI Response",
    sel_start: int | None = None,
    sel_end: int | None = None,
) -> Dict[str, Any]:
    if not selected_text:
        raise ValueError("selected_text is required")

    with _db_connect() as conn:
        source = _db_get_doc(conn, source_doc_id)
        if not source:
            raise ValueError(f"Source doc not found: {source_doc_id}")

        source_body = source["body"]
        if source_body is None:
            source_body = ""
        if not isinstance(source_body, str):
            raise TypeError("Source document body is not plain text; ASK insertion only supports text docs")

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
        created = _db_get_doc(conn, new_doc_id)
        updated_source = _db_get_doc(conn, source_doc_id)
        return {
            "status": "ok",
            "engine": "agent_supplied",
            "db_path": str(DB_PATH),
            "source_doc_id": source_doc_id,
            "new_doc_id": new_doc_id,
            "replacement_mode": replacement_mode,
            "created_doc": dict(created) if created else None,
            "updated_source_doc": dict(updated_source) if updated_source else None,
        }


def _ask_native_ai(
    *,
    source_doc_id: int,
    selected_text: str,
    prefix: str | None = None,
    sel_start: int | None = None,
    sel_end: int | None = None,
) -> Dict[str, Any]:
    repo_root = Path(__file__).resolve().parent.parent
    if str(repo_root) not in sys.path:
        sys.path.insert(0, str(repo_root))

    from modules.document_store import DocumentStore
    from modules.ai_interface import AIInterface
    from modules.command_processor import CommandProcessor

    store = DocumentStore(str(DB_PATH))
    ai = AIInterface()
    processor = CommandProcessor(store, ai)

    before_max = store.conn.execute("SELECT COALESCE(MAX(id), 0) FROM documents").fetchone()[0]
    result: Dict[str, Any] = {"new_doc_id": None}

    def _on_success(new_id):
        try:
            result["new_doc_id"] = int(new_id)
        except Exception:
            result["new_doc_id"] = new_id

    def _on_link_created(_value):
        return None

    processor.query_ai(
        selected_text=selected_text,
        current_doc_id=source_doc_id,
        on_success=_on_success,
        on_link_created=_on_link_created,
        prefix=prefix,
        sel_start=sel_start,
        sel_end=sel_end,
    )

    after_max = store.conn.execute("SELECT COALESCE(MAX(id), 0) FROM documents").fetchone()[0]
    new_doc_id = result.get("new_doc_id")
    if new_doc_id is None and after_max > before_max:
        new_doc_id = int(after_max)
    if new_doc_id is None:
        raise RuntimeError("PiKit native ASK did not create a new document. Check AI runtime/config.")

    created = _db_get_doc(store.conn, int(new_doc_id))
    updated_source = _db_get_doc(store.conn, source_doc_id)
    return {
        "status": "ok",
        "engine": "pikit_native_ai",
        "db_path": str(DB_PATH),
        "source_doc_id": source_doc_id,
        "new_doc_id": int(new_doc_id),
        "created_doc": dict(created) if created else None,
        "updated_source_doc": dict(updated_source) if updated_source else None,
    }


def _resolve_distill_source(
    *,
    source_doc_id: int | None,
    source_text: str | None,
    source_title: str | None,
) -> tuple[int | None, str, str]:
    if source_doc_id is not None:
        with _db_connect() as conn:
            row = _db_get_doc(conn, source_doc_id)
            if not row:
                raise ValueError(f"Source doc not found: {source_doc_id}")
            resolved_title = source_title or _s(row["title"], "Untitled")
            body = row["body"]
            if body is None:
                body = ""
            if not isinstance(body, str):
                raise TypeError("DISTILL currently only supports text source docs")
            resolved_text = source_text if source_text is not None else body
            return source_doc_id, resolved_text, resolved_title

    if source_text is None:
        raise ValueError("Provide source_doc_id or source_text")
    return None, source_text, (source_title or "Untitled")


def _distill_insert_db(
    *,
    source_doc_id: int | None,
    source_text: str,
    source_title: str,
    distilled_body: str,
    selected_text: str | None = None,
    sel_start: int | None = None,
    sel_end: int | None = None,
) -> Dict[str, Any]:
    with _db_connect() as conn:
        new_title = f"Distilled Brief: {source_title}"
        new_body = f"Distilled from: {source_title}\nPurpose: execution bridge\n\n{distilled_body}"
        cur = conn.execute(
            "INSERT INTO documents (title, body) VALUES (?, ?)",
            (new_title, new_body),
        )
        new_doc_id = int(cur.lastrowid)
        replacement_mode = "none"

        if source_doc_id is not None:
            source = _db_get_doc(conn, source_doc_id)
            if source is None:
                raise ValueError(f"Source doc not found: {source_doc_id}")
            body = source["body"]
            if body is None:
                body = ""
            if not isinstance(body, str):
                raise TypeError("DISTILL currently only supports text source docs")

            selection_label = (selected_text or "").strip()
            anchor = selection_label or f"Distilled Brief ({new_doc_id})"
            link_md = f"[{anchor}](doc:{new_doc_id})"
            updated = None

            if (
                selection_label
                and isinstance(sel_start, int)
                and isinstance(sel_end, int)
                and 0 <= sel_start < sel_end <= len(body)
            ):
                updated = body[:sel_start] + link_md + body[sel_end:]
                replacement_mode = "offsets"
            elif selection_label and selection_label in body:
                updated = body.replace(selection_label, link_md, 1)
                replacement_mode = "substring"
            elif not selection_label:
                suffix = "\n\n" if body and not body.endswith("\n") else "\n"
                updated = body + suffix + link_md + "\n"
                replacement_mode = "append"

            if updated is not None and updated != body:
                conn.execute(
                    "UPDATE documents SET body = ? WHERE id = ?",
                    (updated, source_doc_id),
                )

        conn.commit()
        created = _db_get_doc(conn, new_doc_id)
        updated_source = _db_get_doc(conn, source_doc_id) if source_doc_id is not None else None
        return {
            "status": "ok",
            "engine": "agent_supplied",
            "db_path": str(DB_PATH),
            "source_doc_id": source_doc_id,
            "new_doc_id": new_doc_id,
            "replacement_mode": replacement_mode,
            "created_doc": dict(created) if created else None,
            "updated_source_doc": dict(updated_source) if updated_source else None,
        }


def _distill_native_ai(
    *,
    source_doc_id: int | None,
    source_text: str,
    source_title: str,
    selected_text: str | None = None,
    sel_start: int | None = None,
    sel_end: int | None = None,
) -> Dict[str, Any]:
    repo_root = Path(__file__).resolve().parent.parent
    if str(repo_root) not in sys.path:
        sys.path.insert(0, str(repo_root))

    from modules.document_store import DocumentStore
    from modules.ai_interface import AIInterface
    from modules.command_processor import CommandProcessor

    store = DocumentStore(str(DB_PATH))
    ai = AIInterface()
    processor = CommandProcessor(store, ai)

    before_max = store.conn.execute("SELECT COALESCE(MAX(id), 0) FROM documents").fetchone()[0]
    result: Dict[str, Any] = {"new_doc_id": None}

    def _on_success(new_id):
        try:
            result["new_doc_id"] = int(new_id)
        except Exception:
            result["new_doc_id"] = new_id

    def _on_link_created(_value):
        return None

    processor.distill_text(
        source_text=source_text,
        current_doc_id=source_doc_id,
        on_success=_on_success,
        on_link_created=_on_link_created,
        source_title=source_title,
        selected_text=selected_text,
        sel_start=sel_start,
        sel_end=sel_end,
    )

    after_max = store.conn.execute("SELECT COALESCE(MAX(id), 0) FROM documents").fetchone()[0]
    new_doc_id = result.get("new_doc_id")
    if new_doc_id is None and after_max > before_max:
        new_doc_id = int(after_max)
    if new_doc_id is None:
        raise RuntimeError("PiKit native DISTILL did not create a new document. Check AI runtime/config.")

    created = _db_get_doc(store.conn, int(new_doc_id))
    updated_source = _db_get_doc(store.conn, source_doc_id) if source_doc_id is not None else None
    return {
        "status": "ok",
        "engine": "pikit_native_ai",
        "db_path": str(DB_PATH),
        "source_doc_id": source_doc_id,
        "new_doc_id": int(new_doc_id),
        "created_doc": dict(created) if created else None,
        "updated_source_doc": dict(updated_source) if updated_source else None,
    }


def _convert_payload_to_opml_api(title: str, payload: Any) -> str:
    repo_root = Path(__file__).resolve().parent.parent
    if str(repo_root) not in sys.path:
        sys.path.insert(0, str(repo_root))

    try:
        import importlib
        eng = importlib.import_module("modules.aopmlengine")
        if hasattr(eng, "convert_payload_to_opml"):
            return eng.convert_payload_to_opml(title, payload)
        text = payload.decode("utf-8", "replace") if isinstance(payload, (bytes, bytearray)) else str(payload or "")
        low = text.lower()
        if ("<html" in low or "<body" in low or "<div" in low or "<p" in low) and hasattr(eng, "build_opml_from_html"):
            return eng.build_opml_from_html(title, text)
        if hasattr(eng, "build_opml_from_text"):
            return eng.build_opml_from_text(title, text)
    except Exception:
        pass

    text = payload.decode("utf-8", "replace") if isinstance(payload, (bytes, bytearray)) else str(payload or "")
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    body = "\n".join(f'    <outline text="{ln}"/>' for ln in lines) or '    <outline text="[empty]"/>'
    return (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<opml version="2.0">\n'
        f'  <head><title>{title}</title></head>\n'
        '  <body>\n'
        f'{body}\n'
        '  </body>\n'
        '</opml>\n'
    )


# -------------------- app --------------------

def create_app():
    try:
        from flask import Flask, render_template_string, abort, Response, request, jsonify
    except ImportError:
        print("Error: Flask is not installed. Run 'pip install flask'.", file=sys.stderr)
        sys.exit(1)

    app = Flask(__name__)
    app.config["TEMPLATES_AUTO_RELOAD"] = True
    api_token = _load_api_token()

    def _require_auth() -> None:
        if not api_token:
            abort(503, description="API token is not configured")
        auth = request.headers.get("Authorization", "")
        if not auth.startswith("Bearer "):
            abort(401)
        supplied = auth.split(" ", 1)[1].strip()
        if not supplied or not secrets.compare_digest(supplied, api_token):
            abort(401)

    @app.after_request
    def _add_security_headers(resp):
        resp.headers["X-Content-Type-Options"] = "nosniff"
        resp.headers["X-Frame-Options"] = "DENY"
        resp.headers["Referrer-Policy"] = "no-referrer"
        if request.is_secure:
            resp.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
        return resp

    @app.errorhandler(404)
    def _e404(_e):
        return (
            """<!doctype html><meta charset=\"utf-8\">
            <title>Not found</title>
            <h3>Not found</h3><p>The requested item was not found.</p>
            <p><a href=\"/\">← Back to index</a></p>""",
            404,
            {"Content-Type": "text/html; charset=utf-8"},
        )

    @app.errorhandler(500)
    def _e500(e):
        print("[flask_server] 500:", e, file=sys.stderr)
        traceback.print_exc()
        return (
            """<!doctype html><meta charset=\"utf-8\">
            <title>Server error</title>
            <h3>Internal Server Error</h3>
            <p>Something went wrong rendering this page.</p>
            <p><a href=\"/\">← Back to index</a></p>""",
            500,
            {"Content-Type": "text/html; charset=utf-8"},
        )

    @app.route("/health")
    def health():
        exists = DATA_DIR.exists()
        count = len(list(_iter_docs())) if exists else 0
        assets = ASSETS_DIR.exists()
        return {
            "status": "ok",
            "exported_docs_exists": exists,
            "doc_count": count,
            "assets_exists": assets,
            "api_token_configured": bool(api_token),
            "https_available": DEFAULT_CERT.exists() and DEFAULT_KEY.exists(),
        }

    @app.route("/api/health")
    def api_health():
        _require_auth()
        exists = DATA_DIR.exists()
        count = len(list(_iter_docs())) if exists else 0
        return jsonify({"status": "ok", "doc_count": count})

    @app.route("/api/doc/<doc_id>")
    def api_get_doc(doc_id: str):
        _require_auth()
        doc = _find_doc(_s(doc_id))
        if not doc:
            abort(404)
        return jsonify(doc)

    @app.route("/api/search", methods=["POST"])
    def api_search():
        _require_auth()
        if not request.is_json:
            abort(400, description="Expected application/json")
        payload = request.get_json(silent=True) or {}
        query = _s(payload.get("query")).strip()
        if not query:
            abort(400, description="Missing 'query'")
        try:
            limit = int(payload.get("limit", 25))
        except Exception:
            limit = 25
        limit = max(1, min(limit, 200))
        ql = query.lower()
        results: List[Dict[str, Any]] = []
        for doc in _iter_docs():
            title = _s(doc.get("title"))
            body = _s(doc.get("body"))
            description = _s(doc.get("description"))
            if ql in title.lower() or ql in body.lower() or ql in description.lower():
                results.append(_doc_summary(doc))
            if len(results) >= limit:
                break
        return jsonify({"query": query, "limit": limit, "results": results})

    @app.route("/share/<share_id>")
    def shared_doc(share_id: str):
        shared = _load_share(_s(share_id))
        if not shared:
            abort(404)
        return jsonify(shared)

    @app.route("/api/stats")
    def api_stats():
        _require_auth()
        docs = list(_iter_docs())
        return jsonify({
            "status": "ok",
            "exported_docs_exists": DATA_DIR.exists(),
            "doc_count": len(docs),
            "sample": [_doc_summary(doc) for doc in docs[:10]],
        })

    @app.route("/api/ask", methods=["POST"])
    def api_ask():
        _require_auth()
        if not request.is_json:
            abort(400, description="Expected application/json")
        payload = request.get_json(silent=True) or {}
        try:
            source_doc_id = _coerce_int(
                payload.get("source_doc_id", payload.get("source_doc", payload.get("doc_id"))),
                "source_doc_id",
            )
            selected_text = _s(payload.get("selected_text")).strip()
            if not selected_text:
                raise ValueError("selected_text is required")

            response_title = _s(payload.get("response_title") or "AI Response")
            response_body = payload.get("response_body")
            prefix = _s(payload.get("prefix")).strip() or None

            sel_start = payload.get("sel_start")
            sel_end = payload.get("sel_end")
            sel_start = _coerce_int(sel_start, "sel_start") if sel_start is not None else None
            sel_end = _coerce_int(sel_end, "sel_end") if sel_end is not None else None

            if response_body is not None:
                result = _ask_insert_db(
                    source_doc_id=source_doc_id,
                    selected_text=selected_text,
                    response_body=_s(response_body),
                    response_title=response_title,
                    sel_start=sel_start,
                    sel_end=sel_end,
                )
            else:
                result = _ask_native_ai(
                    source_doc_id=source_doc_id,
                    selected_text=selected_text,
                    prefix=prefix,
                    sel_start=sel_start,
                    sel_end=sel_end,
                )
            return jsonify(result)
        except ValueError as e:
            return jsonify({"status": "error", "error": str(e)}), 400
        except Exception as e:
            print("[flask_server] /api/ask failed:", e, file=sys.stderr)
            traceback.print_exc()
            return jsonify({"status": "error", "error": str(e)}), 500

    @app.route("/api/distill", methods=["POST"])
    def api_distill():
        _require_auth()
        if not request.is_json:
            abort(400, description="Expected application/json")
        payload = request.get_json(silent=True) or {}
        try:
            raw_source_doc_id = payload.get("source_doc_id", payload.get("source_doc", payload.get("doc_id")))
            source_doc_id = _coerce_int(raw_source_doc_id, "source_doc_id") if raw_source_doc_id is not None else None
            source_text = payload.get("source_text")
            source_text = _s(source_text) if source_text is not None else None
            source_title = _s(payload.get("source_title")).strip() or None
            selected_text = _s(payload.get("selected_text")).strip() or None
            distilled_body = payload.get("distilled_body")
            distilled_body = _s(distilled_body) if distilled_body is not None else None

            sel_start = payload.get("sel_start")
            sel_end = payload.get("sel_end")
            sel_start = _coerce_int(sel_start, "sel_start") if sel_start is not None else None
            sel_end = _coerce_int(sel_end, "sel_end") if sel_end is not None else None

            source_doc_id, source_text, source_title = _resolve_distill_source(
                source_doc_id=source_doc_id,
                source_text=source_text,
                source_title=source_title,
            )

            if distilled_body is not None:
                result = _distill_insert_db(
                    source_doc_id=source_doc_id,
                    source_text=source_text,
                    source_title=source_title,
                    distilled_body=distilled_body,
                    selected_text=selected_text,
                    sel_start=sel_start,
                    sel_end=sel_end,
                )
            else:
                result = _distill_native_ai(
                    source_doc_id=source_doc_id,
                    source_text=source_text,
                    source_title=source_title,
                    selected_text=selected_text,
                    sel_start=sel_start,
                    sel_end=sel_end,
                )
            return jsonify(result)
        except ValueError as e:
            return jsonify({"status": "error", "error": str(e)}), 400
        except Exception as e:
            print("[flask_server] /api/distill failed:", e, file=sys.stderr)
            traceback.print_exc()
            return jsonify({"status": "error", "error": str(e)}), 500

    @app.route("/api/convert_to_opml", methods=["POST"])
    def api_convert_to_opml():
        _require_auth()
        if not request.is_json:
            abort(400, description="Expected application/json")
        payload = request.get_json(silent=True) or {}
        try:
            raw_source_doc_id = payload.get("source_doc_id", payload.get("source_doc", payload.get("doc_id")))
            source_doc_id = _coerce_int(raw_source_doc_id, "source_doc_id") if raw_source_doc_id is not None else None
            if source_doc_id is None:
                raise ValueError("source_doc_id is required for Convert to OPML")

            with _db_connect() as conn:
                row = _db_get_doc(conn, source_doc_id)
                if not row:
                    raise ValueError(f"Source doc not found: {source_doc_id}")
                source_title = _s(row["title"], "Document")
                source_body = row["body"]
                if source_body is None:
                    source_body = ""

                opml = _convert_payload_to_opml_api(source_title, source_body)
                new_title = f"{source_title} (OPML)"
                cur = conn.execute(
                    "INSERT INTO documents (title, body) VALUES (?, ?)",
                    (new_title, opml),
                )
                conn.commit()
                new_doc_id = int(cur.lastrowid)
                created = _db_get_doc(conn, new_doc_id)

            return jsonify({
                "status": "ok",
                "source_doc_id": source_doc_id,
                "new_doc_id": new_doc_id,
                "created_doc": dict(created) if created else None,
            })
        except ValueError as e:
            return jsonify({"status": "error", "error": str(e)}), 400
        except Exception as e:
            print("[flask_server] /api/convert_to_opml failed:", e, file=sys.stderr)
            traceback.print_exc()
            return jsonify({"status": "error", "error": str(e)}), 500

    @app.route("/")
    def index():
        """
        Index with view modes:
          ?view=auto   (default) — show thumbs only if doc has one (no placeholders; compact rows otherwise)
          ?view=list              — never show thumbs (tight list)
          ?view=gallery           — show thumbs; can enable placeholders via ?ph=smile
        """
        view = (request.args.get("view") or "auto").lower()
        ph = (request.args.get("ph") or "").lower()  # "smile" to show placeholder
        show_placeholders = (view in ("gallery", "auto")) and (ph == "smile")

        items = []
        note = "" if DATA_DIR.exists() else f"(Directory not found: {DATA_DIR})"

        for doc in _iter_docs():
            try:
                doc_id = _s(doc.get("id")) or _s(abs(hash(_s(doc.get("title")))) % (10**9))
                title = _s(doc.get("title", f"Document {doc_id}"))
                raw_desc = doc.get("description")
                if raw_desc is None:
                    raw_desc = doc.get("body", "")
                desc = _s(raw_desc).replace("\n", " ")[:80]

                thumb_src = None
                has_image = False
                imgs = _collect_images(doc)
                if imgs:
                    src = _data_uri_or_asset(imgs[0])
                    if src:
                        thumb_src = src
                        has_image = True
                if not has_image and view == "gallery" and show_placeholders:
                    thumb_src = _smiley_data_uri()

                items.append({"id": doc_id, "title": title, "desc": desc, "thumb": thumb_src, "has_image": has_image})
            except Exception as e:
                print(f"[flask_server] Skipping bad doc on index: {e}", file=sys.stderr)

        def link_for(v):
            q = {"view": v}
            if ph:
                q["ph"] = ph
            return "/?" + urlencode(q)

        template = """
        <!doctype html>
        <meta charset="utf-8" />
        <title>PiKit Documents</title>
        <style>
          body { font-family: ui-sans-serif, system-ui, -apple-system, Segoe UI, Roboto, Arial, sans-serif; margin: 24px; }
          .toolbar { margin-bottom: 12px; font-size: 0.95rem; }
          .toolbar a { margin-right: 12px; }
          ul.docs { list-style: none; padding: 0; margin: 0; }
          li.doc { display: flex; align-items: center; gap: 12px; padding: 8px 0; border-bottom: 1px solid #eee; }
          li.doc.compact { gap: 8px; padding: 4px 0; }
          img.thumb { display: block; width: 64px; height: 64px; object-fit: cover; border-radius: 6px; background: #f2f2f2; }
          .meta { line-height: 1.35; }
          .title { font-weight: 600; }
          .desc { color: #555; font-size: 0.92rem; }
          code { background: #f5f5f5; padding: 2px 4px; border-radius: 4px; }
          a { color: #198754; text-decoration: none; }
          a:hover { text-decoration: underline; }
        </style>

        <h1>PiKit Documents</h1>
        <div class="toolbar">
          View:
          <a href="{{ link_auto }}">Auto</a>
          <a href="{{ link_list }}">List</a>
          <a href="{{ link_gallery }}">Gallery</a>
          {% if ph %}
            | Placeholder: <strong>on</strong>
          {% else %}
            | <a href="/?{{ 'view=' + view + '&ph=smile' }}">Enable placeholder</a>
          {% endif %}
        </div>
        {% if note %}<p style="color:#a00;">{{ note }}</p>{% endif %}

        {% if items %}
          <ul class="docs">
          {% for item in items %}
            {% set use_thumb = (view == 'gallery') or (view == 'auto' and item.has_image) %}
            <li class="doc {% if not use_thumb %}compact{% endif %}">
              {% if use_thumb and item.thumb %}
                <a href="/doc/{{ item.id }}"><img class="thumb" src="{{ item.thumb }}" alt=""></a>
              {% endif %}
              <div class="meta">
                <div class="title"><a href="/doc/{{ item.id }}">{{ item.title }}</a></div>
                <div class="desc">{{ item.desc }}{% if item.desc %}…{% endif %}</div>
              </div>
            </li>
          {% endfor %}
          </ul>
        {% else %}
          <p>No documents found in <code>{{ data_dir }}</code>.</p>
        {% endif %}
        """
        return render_template_string(
            template,
            items=items,
            data_dir=str(DATA_DIR),
            note=note,
            view=view,
            ph=ph,
            link_auto=link_for("auto"),
            link_list=link_for("list"),
            link_gallery=link_for("gallery"),
        )

    @app.route("/doc/<doc_id>")
    def show_doc(doc_id):
        from flask import abort, render_template_string, request
        doc = _find_doc(_s(doc_id))
        if not doc:
            abort(404)

        title = _s(doc.get("title", f"Document {doc_id}"))
        body = _s(doc.get("body", ""))

        mode = (request.args.get("mode") or "auto").lower()
        if mode == "auto":
            mode = "reader" if _looks_like_html(body) else "code"
        elif mode not in ("reader", "code"):
            mode = "code"

        if mode == "reader":
            try:
                body_render = re.sub(r"\[(.+?)\]\(doc:(\d+)\)", r'<a href="/doc/\2">\1</a>', body)
            except Exception:
                body_render = _s(body)
        else:
            body_render = body

        images = _collect_images(doc)
        image_html_snippets: List[str] = []
        for img in images:
            try:
                src = _data_uri_or_asset(img)
                if not src:
                    continue
                alt = _s(img.get("alt"))
                caption = _s(img.get("caption"))
                snippet = f'''
                  <figure class="img-figure">
                    <img src="{src}" alt="{alt}">
                    {f"<figcaption>{caption}</figcaption>" if caption else ""}
                  </figure>
                '''
                image_html_snippets.append(snippet)
            except Exception as e:
                print(f"[flask_server] Bad image skipped: {e}", file=sys.stderr)

        host = request.host_url.rstrip("/")
        share_url = f"{host}/doc/{quote(str(doc_id))}"

        def mode_link(m: str) -> str:
            return f"/doc/{quote(str(doc_id))}?mode={m}"

        template = """
        <!doctype html>
        <meta charset="utf-8" />
        <title>{{ title }} — PiKit Documents</title>
        <style>
          body { font-family: ui-sans-serif, system-ui, -apple-system, Segoe UI, Roboto, Arial, sans-serif; margin: 24px; }
          .content { max-width: 900px; }
          .img-figure { margin: 16px 0; }
          .img-figure img { max-width: 100%; height: auto; display: block; border-radius: 8px; }
          .img-figure figcaption { color: #555; font-size: 0.9rem; margin-top: 6px; }
          pre, code { background: #f7f7f7; padding: 10px 12px; border-radius: 6px; overflow-x: auto; font-family: monospace; font-size: 0.9rem; white-space: pre-wrap; }
          a { color: #198754; text-decoration: none; }
          a:hover { text-decoration: underline; }
          .share { margin: 12px 0 20px; }
          .share input { width: 100%; padding: 8px; border: 1px solid #ddd; border-radius: 6px; }
          .share button { margin-top: 8px; padding: 6px 10px; border: 1px solid #198754; border-radius: 6px; background: #e9f7ef; color: #198754; cursor: pointer; }
          .share button:hover { background: #d9f1e3; }
          .viewtoggle { margin: 6px 0 14px; font-size: 0.95rem; }
        </style>
        <div class="content">
          <h2>{{ title }}</h2>

          <div class="share">
            <label for="shareurl"><strong>Share link</strong></label>
            <input id="shareurl" type="text" readonly value="{{ share_url }}">
            <button onclick="copyShare()">Copy link</button>
            <span id="copied" style="margin-left:8px;color:#198754;display:none;">Copied!</span>
          </div>

          <div class="viewtoggle">
            View:
            <a href="{{ link_code }}">Code</a> |
            <a href="{{ link_reader }}">Reader</a> |
            <a href="{{ link_auto }}">Auto</a>
            <small style="color:#777;">(current: {{ mode }})</small>
          </div>

          {% if mode == 'reader' %}
            <div>{{ body_render|safe }}</div>
          {% else %}
            <pre>{{ body_render }}</pre>
          {% endif %}

          {% if image_html_snippets %}
            <hr>
            <h3>Images</h3>
            {% for snip in image_html_snippets %}
              {{ snip|safe }}
            {% endfor %}
          {% endif %}
          <p><a href="/">← Back to index</a></p>
        </div>
        <script>
          function copyShare() {
            const inp = document.getElementById('shareurl');
            inp.select(); inp.setSelectionRange(0, 99999);
            try { document.execCommand('copy'); } catch(e) {}
            if (navigator.clipboard) { navigator.clipboard.writeText(inp.value); }
            const ok = document.getElementById('copied');
            ok.style.display = 'inline';
            setTimeout(() => ok.style.display = 'none', 1200);
          }
        </script>
        """
        return render_template_string(
            template,
            title=title,
            body_render=body_render,
            image_html_snippets=image_html_snippets,
            share_url=share_url,
            mode=mode,
            link_code=mode_link("code"),
            link_reader=mode_link("reader"),
            link_auto=mode_link("auto"),
        )

    @app.route("/asset/<path:filename>")
    def serve_asset(filename: str):
        from flask import abort, Response
        if not ASSETS_DIR.exists():
            abort(404)
        file_path = (ASSETS_DIR / filename).resolve()
        try:
            file_path.relative_to(ASSETS_DIR)
        except Exception:
            abort(404)
        if not file_path.exists() or not file_path.is_file():
            abort(404)

        try:
            b64_data = file_path.read_text(encoding="utf-8")
            raw = base64.b64decode(b64_data, validate=True)
        except Exception as e:
            print(f"[flask_server] Failed to decode asset {file_path}: {e}", file=sys.stderr)
            abort(404)

        mime = _guess_mime_from_filename(file_path.name)
        return Response(raw, mimetype=mime)

    return app


# -------------------- main --------------------

if __name__ == "__main__":
    debug = os.environ.get("FLASK_DEBUG") == "1"
    port = int(os.environ.get("PORT", "5050"))
    host = os.environ.get("PIKIT_FLASK_HOST", "127.0.0.1")
    cert = Path(os.environ.get("PIKIT_CERT", str(DEFAULT_CERT)))
    key = Path(os.environ.get("PIKIT_KEY", str(DEFAULT_KEY)))

    ssl_context = None
    if cert.exists() and key.exists():
        ssl_context = (str(cert), str(key))
        print(f"[flask_server] HTTPS enabled with cert={cert} key={key}", file=sys.stderr)
    else:
        print("[flask_server] TLS cert/key not found; starting HTTP on localhost only", file=sys.stderr)

    app = create_app()
    app.run(host=host, port=port, debug=debug, ssl_context=ssl_context)
