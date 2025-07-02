# Temporary block to add a test doc if store is empty
if not store.list_documents():
    store.new_document("Welcome", "This is a sample document to get started.")

