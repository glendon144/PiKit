import sqlite3

class DocumentStore:
    def __init__(self, db_path):
        self.conn = sqlite3.connect(db_path)
        self.conn.row_factory = sqlite3.Row
        self.create_table()

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

    def get_document_index(self):
        cur = self.conn.execute("SELECT id, title, body FROM documents ORDER BY id DESC")
        result = []
        for row in cur.fetchall():
            description = (row['body'] or "")[:60].replace("\n", " ").replace("\r", " ")
            result.append({'id': row['id'], 'title': row['title'], 'description': description})
            print("DEBUG: get_document_index returns:", result)
        return result

    def get_document(self, doc_id):
        cur = self.conn.execute("SELECT id, title, body FROM documents WHERE id=?", (doc_id,))
        return cur.fetchone()

    # ... (add your other methods as needed)
