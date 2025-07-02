# File: modules/document_store.py
import sqlite3
import os
import csv
from datetime import datetime

class DocumentStore:
    def __init__(self, db_path="storage/documents.db"):
        os.makedirs(os.path.dirname(db_path), exist_ok=True)
        self.conn = sqlite3.connect(db_path)
        self.conn.row_factory = sqlite3.Row
        # Check if 'created_at' column exists for migration compatibility
        pragma_info = self.conn.execute("PRAGMA table_info(documents)").fetchall()
        self._has_created_at = any(row[1] == 'created_at' for row in pragma_info)
        self._initialize()

    def _initialize(self):
        # Ensure the documents table exists; if adding 'created_at' later, this won't alter existing table
        if not self._has_created_at:
            # Original schema without created_at
            self.conn.execute(
                '''
                CREATE TABLE IF NOT EXISTS documents (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    title TEXT NOT NULL,
                    body TEXT NOT NULL
                )
                '''
            )
        else:
            # Schema with created_at
            self.conn.execute(
                '''
                CREATE TABLE IF NOT EXISTS documents (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    title TEXT NOT NULL,
                    body TEXT NOT NULL,
                    created_at TIMESTAMP NOT NULL
                )
                '''
            )
        self.conn.commit()

    def add_document(self, title, body):
        now = datetime.utcnow()
        if self._has_created_at:
            cur = self.conn.execute(
                "INSERT INTO documents (title, body, created_at) VALUES (?, ?, ?)",
                (title, body, now)
            )
        else:
            cur = self.conn.execute(
                "INSERT INTO documents (title, body) VALUES (?, ?)",
                (title, body)
            )
        self.conn.commit()
        return cur.lastrowid

    def get_document(self, doc_id):
        if self._has_created_at:
            row = self.conn.execute(
                "SELECT id, title, body, created_at FROM documents WHERE id = ?", (doc_id,)
            ).fetchone()
        else:
            row = self.conn.execute(
                "SELECT id, title, body FROM documents WHERE id = ?", (doc_id,)
            ).fetchone()
        return dict(row) if row else None

    def update_document(self, doc_id, new_body):
        self.conn.execute(
            "UPDATE documents SET body = ? WHERE id = ?", (new_body, doc_id)
        )
        self.conn.commit()

    def list_documents(self):
        # Order by created_at if available, else by id
        order_col = 'created_at' if self._has_created_at else 'id'
        rows = self.conn.execute(
            f"SELECT id, body FROM documents ORDER BY {order_col}"
        ).fetchall()
        docs = []
        for row in rows:
            # Derive a short summary from the first line
            summary = row["body"].strip().split("\n", 1)[0]
            if len(summary) > 60:
                summary = summary[:60] + "…"
            docs.append((row["id"], summary))
        return docs

    def import_csv(self, filename="import.csv"):
        if not os.path.exists(filename):
            raise FileNotFoundError(f"{filename} not found.")
        with open(filename, "r", newline='', encoding='utf-8') as csvfile:
            reader = csv.reader(csvfile)
            for row in reader:
                if len(row) >= 2:
                    self.add_document(row[0].strip(), row[1].strip())

    def export_csv(self, filename="export.csv"):
        # Export title and body regardless of created_at
        cursor = self.conn.execute("SELECT title, body FROM documents")
        with open(filename, "w", newline='', encoding='utf-8') as csvfile:
            writer = csv.writer(csvfile)
            writer.writerow(["title", "body"])
            writer.writerows(cursor.fetchall())

    def close(self):
        self.conn.close()
