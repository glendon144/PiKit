import sqlite3
import csv

class DocumentStore:
    def __init__(self, db):
        self.conn = sqlite3.connect(db)
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

    def list_documents(self):
        cursor = self.conn.execute("SELECT id, title FROM documents")
        return cursor.fetchall()

    def import_csv(self):
        with open("import.csv", "r", newline='') as csvfile:
            reader = csv.reader(csvfile)
            for row in reader:
                if len(row) >= 2:
                    self.add_document(row[0], row[1])

    def export_csv(self):
        cursor = self.conn.execute("SELECT title, body FROM documents")
        with open("export.csv", "w", newline='') as csvfile:
            writer = csv.writer(csvfile)
            writer.writerows(cursor.fetchall())
