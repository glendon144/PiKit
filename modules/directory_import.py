
import os, mimetypes

def import_text_files_from_directory(dir_path, doc_store):
    """Import all files; text decoded as UTF‑8, others stored raw bytes."""
    imported = skipped = 0

    for filename in os.listdir(dir_path):
        full = os.path.join(dir_path, filename)
        if not os.path.isfile(full):
            continue

        mime, _ = mimetypes.guess_type(full)
        is_text = (mime and mime.startswith("text")) or filename.lower().endswith(
            (".txt", ".md", ".py", ".c", ".json", ".csv", ".html", ".css")
        )

        try:
            if is_text:
                with open(full, "r", encoding="utf-8", errors="ignore") as f:
                    body = f.read()
            else:
                with open(full, "rb") as f:
                    body = f.read()

            doc_store.add_document(title=filename, body=body)
            imported += 1
            print(f"[INFO] Imported {filename} → doc", imported)
        except Exception as e:
            skipped += 1
            print(f"[WARNING] Skipped {filename}: {e}")

    return imported, skipped
