import os
from pathlib import Path

def import_text_files_from_directory(directory: str, doc_store, skip_existing=True):
    """
    Imports all .txt files from a directory into the document store.

    Args:
        directory (str): Path to the directory.
        doc_store (DocumentStore): The document store instance.
        skip_existing (bool): If True, skips files whose titles already exist in the store.

    Returns:
        (int, int): A tuple (imported_count, skipped_count)
    """
    imported = 0
    skipped = 0

    for root, _, files in os.walk(directory):
        for file in files:
            if not file.lower().endswith(".txt"):
                continue
            path = Path(root) / file
            title = path.stem

            if skip_existing and doc_store.has_title(title):
                skipped += 1
                continue

            try:
                body = path.read_text(encoding="utf-8")
                doc_store.add_document(title, body)
                imported += 1
            except Exception as e:
                print(f"[WARN] Skipped {file}: {e}")
                skipped += 1

    return imported, skipped

