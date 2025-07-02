import pandas as pd
import datetime
import os

def migrate_document_store(file_path="storage/documents.csv"):
    if not os.path.exists(file_path):
        print("No existing document store found to migrate.")
        return

    df = pd.read_csv(file_path)
    updated = False

    if 'created_at' not in df.columns:
        df['created_at'] = datetime.datetime.now().isoformat()
        updated = True

    if 'updated_at' not in df.columns:
        df['updated_at'] = datetime.datetime.now().isoformat()
        updated = True

    if updated:
        df.to_csv(file_path, index=False)
        print("Migration successful. Document store updated to 5E schema.")
    else:
        print("Document store already up-to-date. No changes made.")

if __name__ == "__main__":
    migrate_document_store()
