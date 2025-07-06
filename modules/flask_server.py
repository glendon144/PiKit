import os
import json
import re
import sys
from pathlib import Path

# Directory where JSON files are exported
DATA_DIR = Path(__file__).parent.parent / "exported_docs"

def create_app():
    try:
        from flask import Flask, render_template_string, abort
    except ImportError:
        print("Error: Flask is not installed. Run 'pip install flask'.")
        sys.exit(1)
    app = Flask(__name__)

    @app.route("/")
    def index():
        """Index page: list all documents with title and description."""
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
                desc = doc.get("description", "")[:80].replace("\n", " ")
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
                desc = doc.get("body", "")[:80].replace("\n", " ")
                items.append({'id': doc_id, 'title': title, 'desc': desc})

        template = """
        <h1>DemoKit Documents</h1>
        <ul>
        {% for item in items %}
          <li><a href="/doc/{{ item.id }}">{{ item.title }} - {{ item.desc }}...</a></li>
        {% endfor %}
        </ul>
        """
        return render_template_string(template, items=items)

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
        body = doc.get("body", "")
        # Convert markdown doc: links to HTML
        body_html = re.sub(r'\[(.+?)\]\(doc:(\d+)\)', r'<a href="/doc/\2">\1</a>', body)
        template = """
        <h2>{{ title }}</h2>
        <div>{{ body_html|safe }}</div>
        <p><a href="/">← Back to index</a></p>
        """
        return render_template_string(template, title=title, body_html=body_html)

    return app

if __name__ == "__main__":
    app = create_app()
    app.run(debug=True)
