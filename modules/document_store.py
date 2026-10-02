import sqlite3
from modules.db_migrations import ensure_ai_memory_table

class DocumentStore:
    def __init__(self, db_path):
        self.conn = sqlite3.connect(db_path)
        self.conn.row_factory = sqlite3.Row
        self.create_table()
        ensure_ai_memory_table(self.conn)  
        self.ensure_content_type_column()   # ensure type column exists
    def get_connection(self):
        return self.conn    # Return the actual connection object

    # modules/document_store.py  (add near your other helpers)
    def ensure_content_type_column(self):
        cur = self.conn.cursor()
        cur.execute("PRAGMA table_info(documents)")
        cols = {row[1] for row in cur.fetchall()}
        if "content_type" not in cols:
            # Back-compat: default existing docs to text/plain
            self.conn.execute("ALTER TABLE documents ADD COLUMN content_type TEXT DEFAULT 'text/plain'")
            self.conn.commit()

    def create_table(self):
        self.conn.execute(
            "CREATE TABLE IF NOT EXISTS documents (id INTEGER PRIMARY KEY, title TEXT, body TEXT, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)"
        )
        self.conn.commit()

    # Add this method here clearly:
    def add_document(self, title, body):
        cur = self.conn.execute(
            "INSERT INTO documents (title, body) VALUES (?, ?)", 
            (title, body)
        )
        self.conn.commit()
        return cur.lastrowid

    def update_document(self, doc_id: int, new_body: str):
        """
        Replace the body of an existing document.
        """
        self.conn.execute(
        "UPDATE documents SET body = ? WHERE id = ?",
        (new_body, doc_id)
    )
        self.conn.commit()

    def append_to_document(self, doc_id: int, extra_text: str):
        """
        # Append text to the end of a document body.
        """
        row = self.get_document(doc_id)
        if not row:
            raise ValueError(f"No document with id {doc_id}")

        current_body = row["body"] if isinstance(row, dict) else row[2]
        if current_body is None:
            current_body = ""

        new_body = current_body + "\n" + extra_text
        self.update_document(doc_id, new_body)

    def get_document_index(self):
        """
        Return[{'id': .., 'title': .., 'description': .., 'size': ..}, ...] -
        'description' is a 60-char preview for text docs,
        or "[12345 bytes]" for binary (images, PDFs, ...).
        """
        cur = self.conn.execute(
            "SELECT id, title, body FROM documents ORDER BY id DESC"
        )
        result = []
        for row in cur.fetchall():
            body = row["body"]
            if body is None:
                body = ""
            if isinstance(body, bytes):
                # binary file - show size placeholder
                desc = f"[{len(body)} bytes]"
                size = len(body)
            else:
                # text - first 60 chars, single-line
                desc = body[:60].replace("\n", " ").replace("\r", " ")
                size = len(body.encode("utf-8", errors="ignore"))
            result.append({"id": row["id"], "title": row["title"], "description": desc, "size": size})
        return result

    def get_document(self, doc_id):
        cur = self.conn.execute("SELECT id, title, body FROM documents WHERE id=?", (doc_id,))
        return cur.fetchone()

    # ... (add your other methods as needed)
    def delete_document(self, doc_id: int):
        """Permanently delete a document and commit changes."""
        self.conn.execute(
            "DELETE FROM documents WHERE id = ?",
            (doc_id,)
        )
        self.conn.commit()
