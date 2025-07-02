from modules.document_store import DocumentStore

store = DocumentStore("storage/documents.db")
store.add_document("Welcome", "This is a test document to verify the GUI works.")
store.close()

