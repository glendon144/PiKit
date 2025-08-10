import sqlite3


class DocumentStore:
    def __init__(self, db_path: str):
        # Row factory gives us dict-like rows: row["id"], row["title"], row["body"]
        self.conn = sqlite3.connect(db_path)
        self.conn.row_factory = sqlite3.Row
        self.create_table()

    def create_table(self) -> None:
        self.conn.execute(
            """
            CREATE TABLE IF NOT EXISTS documents (
                id INTEGER PRIMARY KEY,
                title TEXT,
                body  BLOB,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        self.conn.commit()

    # --- CRUD ---

    def add_document(self, title: str, body) -> int:
        """
        Accepts either str or bytes for body.
        """
        cur = self.conn.execute(
            "INSERT INTO documents (title, body) VALUES (?, ?)",
            (title, body),
        )
        self.conn.commit()
        return cur.lastrowid

    def update_document(self, doc_id: int, new_body) -> None:
        """Replace the body of an existing document (str or bytes)."""
        self.conn.execute(
            "UPDATE documents SET body = ? WHERE id = ?",
            (new_body, doc_id),
        )
        self.conn.commit()

    def delete_document(self, doc_id: int) -> None:
        """Permanently delete a document."""
        self.conn.execute("DELETE FROM documents WHERE id = ?", (doc_id,))
        self.conn.commit()

    # --- Queries used by the GUI ---

    def get_document_index(self):
        """
        Returns: [{'id': .., 'title': .., 'description': ..}, ...]
        Description is synthesized from the first 60 chars of text bodies.
        If the body is bytes that do not decode as UTF-8, we show "[N bytes]".
        """
        cur = self.conn.execute(
            "SELECT id, title, body FROM documents ORDER BY id DESC"
        )
        out = []
        for row in cur.fetchall():
            body = row["body"]

            # Decide description
            if isinstance(body, bytes):
                try:
                    text = body.decode("utf-8")  # will raise if truly binary
                    desc = text[:60].replace("\n", " ").replace("\r", " ")
                except UnicodeDecodeError:
                    desc = f"[{len(body)} bytes]"
            elif isinstance(body, str) and body:
                desc = body[:60].replace("\n", " ").replace("\r", " ")
            else:
                desc = ""  # empty or None

            out.append(
                {"id": row["id"], "title": row["title"], "description": desc}
            )
        return out

    def get_document(self, doc_id: int):
        """
        Returns a dict: {'id', 'title', 'body}
        - 'body' will be a str when possible (UTF-8 decoded)
        - otherwise it remains bytes (for true binary content)
        """
        cur = self.conn.execute(
            "SELECT id, title, body FROM documents WHERE id = ?",
            (doc_id,),
        )
        row = cur.fetchone()
        if not row:
            return None

        body = row["body"]
        if isinstance(body, bytes):
            try:
                body = body.decode("utf-8")  # decode text blobs
            except UnicodeDecodeError:
                # keep bytes for real binary; the GUI shows a placeholder
                pass

        return {"id": row["id"], "title": row["title"], "body": body}

