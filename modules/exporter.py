# modules/exporter.py

import os
import json

def export_documents(doc_store, output_dir="exported_docs"):
    os.makedirs(output_dir, exist_ok=True)
    index = doc_store.get_document_index()

    for rec in index:
        doc_id = rec["id"]
        row = doc_store.get_document(doc_id)
        doc = dict(row)  # convert sqlite3.Row to a plain dict
        with open(os.path.join(output_dir, f"{doc_id}.json"), "w", encoding="utf-8") as f:
            json.dump(doc, f, ensure_ascii=False, indent=2)

    print(f"Exported {len(index)} documents to '{output_dir}'")

