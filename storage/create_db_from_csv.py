import csv
from document_store import DocumentStore

def import_loose_csv(csv_file, db_file="storage/documents.db", skipped_file="skipped_rows.csv"):
    store = DocumentStore(db_file)
    added = 0
    skipped = 0
    skipped_rows = []

    with open(csv_file, "r", newline='', encoding='utf-8') as f:
        reader = csv.reader(f)
        store.conn.execute("DELETE FROM documents")
        for i, row in enumerate(reader):
            if len(row) >= 3 and row[1].strip() and row[2].strip():
                store.add_document(row[1].strip(), row[2].strip())
                added += 1
            else:
                print(f"⚠️ Skipping row {i + 1}: {row}")
                skipped_rows.append(row)
                skipped += 1

    store.close()

    if skipped_rows:
        with open(skipped_file, "w", newline='', encoding='utf-8') as f:
            writer = csv.writer(f)
            writer.writerows(skipped_rows)
        print(f"⚠️ {skipped} rows skipped and saved to '{skipped_file}'")

    print(f"✅ Import complete: {added} rows added, {skipped} rows skipped.")

if __name__ == "__main__":
    import_loose_csv("documents.csv")

