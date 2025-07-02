
import sqlite3
import os
import csv

class DocumentStore:
    def __init__(self, db_path="storage/documents.db"):
        os.makedirs(os.path.dirname(db_path), exist_ok=True)
        self.conn = sqlite3.connect(db_path)
        self.create_table()

    def create_table(self):
        with self.conn:
            self.conn.execute('''
                CREATE TABLE IF NOT EXISTS documents (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    title TEXT NOT NULL,
                    body TEXT NOT NULL
                )
            ''')

    def add_document(self, title, body):
        with self.conn:
            cursor = self.conn.execute(
                "INSERT INTO documents (title, body) VALUES (?, ?)", (title, body)
            )
            return cursor.lastrowid

    def get_document(self, doc_id):
        cursor = self.conn.execute("SELECT * FROM documents WHERE id = ?", (doc_id,))
        return cursor.fetchone()

    def update_document(self, doc_id, new_body):
        with self.conn:
            self.conn.execute(
                "UPDATE documents SET body = ? WHERE id = ?", (new_body, doc_id)
            )

    def list_documents(self):
        cursor = self.conn.execute("SELECT id, title FROM documents")
        return cursor.fetchall()

    def import_csv(self, filename="import.csv"):
        if not os.path.exists(filename):
            raise FileNotFoundError(f"{filename} not found.")
        with open(filename, "r", newline='', encoding='utf-8') as csvfile:
            sniffer = csv.Sniffer()
            has_header = sniffer.has_header(csvfile.read(1024))
            csvfile.seek(0)
            reader = csv.reader(csvfile)

            if has_header:
                next(reader, None)  # skip header

            for row in reader:
                if len(row) >= 2 and row[0].strip() and row[1].strip():
                    self.add_document(row[0].strip(), row[1].strip())

    def export_csv(self, filename="export.csv"):
        cursor = self.conn.execute("SELECT title, body FROM documents")
        with open(filename, "w", newline='', encoding='utf-8') as csvfile:
            writer = csv.writer(csvfile)
            writer.writerow(["title", "body"])
            writer.writerows(cursor.fetchall())

    def close(self):
        self.conn.close()
