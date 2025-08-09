# modules/flask_server.py
import os
import json
import re
import sys
import base64
import mimetypes
from pathlib import Path

# Directory where JSON files are exported
DATA_DIR = Path(__file__).parent.parent / "exported_docs"
DATA_DIR.mkdir(exist_ok=True)

def create_app():
    try:
        from flask import Flask, render_template_string, abort, send_from_directory
    except ImportError:
        print("Error: Flask is not installed. Run 'pip install flask'.")
        sys.exit(1)

    app = Flask(__name__)

    # -------- helpers --------
    def _is_image_path(p: Path) -> bool:
        mime, _ = mimetypes.guess_type(p.name)
        return bool(mime and mime.startswith("image/"))

    def _is_image_name(name: str) -> bool:
        mime, _ = mimetypes.guess_type(name)
        return bool(mime and mime.startswith("image/"))

    # Serve exported files (images, etc.)
    @app.get("/files/<path:relpath>")
    def files(relpath):
        safe = (DATA_DIR / relpath).resolve()
        if not str(safe).startswith(str(DATA_DIR)) or not safe.exists():
            abort(404)
        return send_from_directory(DATA_DIR, relpath)

    # -------- index --------
    @app.route("/")
    def index():
        """Index page: list all documents with title/desc, plus any standalone images as thumbnails."""
        docs_file = DATA_DIR / "docs.json"
        items = []

        if docs_file.exists():
            with docs_file.open(encoding="utf-8") as f:
                docs = json.load(f)
            if isinstance(docs, dict):
                docs = [docs]
            for doc in docs:
                doc_id = doc.get("id")
                title = doc.get("title", f"Document {doc_id}")
                desc = (doc.get("description") or doc.get("body") or "")[:80].replace("\n", " ")
                items.append({'id': doc_id, 'title': title, 'desc': desc})
        else:
            for file_path in sorted(DATA_DIR.glob("*.json")):
                if file_path.name == "docs.json":
                    continue
                doc_id = file_path.stem
                with file_path.open(encoding="utf-8") as f:
                    doc = json.load(f)
                if isinstance(doc, list):
                    doc = next((d for d in doc if str(d.get("id")) == doc_id), {})
                title = doc.get("title", f"Document {doc_id}")
                desc = (doc.get("description") or doc.get("body") or "")[:80].replace("\n", " ")
                items.append({'id': doc_id, 'title': title, 'desc': desc})

        # Also show standalone images in exported_docs (handy visual check)
        image_items = []
        for p in sorted(DATA_DIR.iterdir(), key=lambda x: x.name.lower()):
            if p.is_file() and _is_image_path(p):
                image_items.append(p.name)

        template = """
        <!doctype html><meta charset="utf-8"/>
        <h1>DemoKit Documents</h1>
        <ul>
        {% for item in items %}
          <li><a href="/doc/{{ item.id }}">{{ item.title }}</a> – {{ item.desc }}...</li>
        {% endfor %}
        </ul>

        {% if images %}
        <h2>Images</h2>
        <ul>
        {% for name in images %}
          <li>
            <a href="/files/{{ name }}" target="_blank">
              <img src="/files/{{ name }}" alt="{{ name }}" style="max-width:320px;height:auto;border:1px solid #ddd;padding:2px"/>
            </a><br/>{{ name }}
          </li>
        {% endfor %}
        </ul>
        {% endif %}
        """
        return render_template_string(template, items=items, images=image_items)

    # -------- document view --------
    @app.route("/doc/<doc_id>")
    def show_doc(doc_id):
        """Document page: render a single document."""
        file_path = DATA_DIR / f"{doc_id}.json"
        if not file_path.exists():
            abort(404)
        with file_path.open(encoding="utf-8") as f:
            doc = json.load(f)
        if isinstance(doc, list):
            doc = next((d for d in doc if str(d.get("id")) == doc_id), {})

        title = doc.get("title", f"Document {doc_id}")
        body = doc.get("body", "") or ""

        # --- Transformations ---

        # 1) PiKit doc links: [label](doc:123) -> <a href="/doc/123">label</a>
        body_html = re.sub(r'\[(.+?)\]\(doc:(\d+)\)', r'<a href="/doc/\2">\1</a>', body)

        # 2) Markdown images with local filenames: ![alt](image.png) -> serve from /files/image.png
        def _md_img_local(m):
            alt = m.group(1) or ""
            url = m.group(2).strip()
            # If it's a pure filename (or path under exported_docs), rewrite to /files/...
            if url.startswith("data:image/"):
                # already a data URI; keep as-is
                return m.group(0)
            if url.startswith("file:"):
                url = url[5:]
            # If it looks like an image filename, serve it
            if _is_image_name(url):
                return f'<img src="/files/{url}" alt="{alt}" style="max-width:100%;height:auto"/>'
            # otherwise leave it alone
            return m.group(0)

        body_html = re.sub(r'!\[([^\]]*)\]\(([^)]+)\)', _md_img_local, body_html)

        # 3) Simple file links: [image](file:photo.png) or [image](photo.png) -> show image inline if supported
        def _md_link_to_img(m):
            text = m.group(1) or ""
            url = m.group(2).strip()
            if url.startswith("file:"):
                url = url[5:]
            if _is_image_name(url):
                return f'<img src="/files/{url}" alt="{text}" style="max-width:100%;height:auto"/>'
            return f'<a href="/files/{url}" target="_blank">{text or url}</a>'

        body_html = re.sub(r'\[([^\]]*)\]\(([^)]+)\)', _md_link_to_img, body_html)

        # 4) Raw base64 helper: [base64:AAA...] -> <img src="data:image/*;base64,..." />
        def _b64_to_img(m):
            b64 = m.group(1)
            mime = "image/png"
            try:
                head = base64.b64decode(b64[:16], validate=False)
                if head.startswith(b"\xff\xd8"):
                    mime = "image/jpeg"
                elif head.startswith(b"GIF"):
                    mime = "image/gif"
                elif head.startswith(b"\x89PNG"):
                    mime = "image/png"
            except Exception:
                pass
            return f'<img src="data:{mime};base64,{b64}" alt="Embedded Image" style="max-width:100%;height:auto"/>'

        body_html = re.sub(r'\[base64:([A-Za-z0-9+/=]+)\]', _b64_to_img, body_html)

        # 5) Keep any existing data: URIs as-is (markdown image syntax already covers it)

        template = """
        <!doctype html><meta charset="utf-8"/>
        <h2>{{ title }}</h2>
        <div style="line-height:1.45">{{ body_html|safe }}</div>
        <p><a href="/">← Back to index</a></p>
        """
        return render_template_string(template, title=title, body_html=body_html)

    return app

if __name__ == "__main__":
    app = create_app()
    app.run(host="127.0.0.1", port=5050)

