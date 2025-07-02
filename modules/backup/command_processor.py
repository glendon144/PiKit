
import openai
from modules.logger import Logger
from modules.document_store import DocumentStore

class CommandProcessor:
    def __init__(self, store: DocumentStore, ai_interface, logger=None):
        self.doc_store = store
        self.ai = ai_interface
        self.logger = logger if logger else Logger()

    def ask_question(self, prompt):
        try:
            self.logger.info(f"Sending prompt to AI: {prompt}")
            response = self.ai.query(prompt)
            self.logger.info("AI response received successfully")
            return response
        except Exception as e:
            self.logger.error(f"Error querying AI: {str(e)}")
            return None

    def query_ai(self, selected_text, current_doc_id, on_success, on_link_created):
        prompt = f"Please expand on this: {selected_text}"
        self.logger.info(f"Sending prompt: {prompt}")
        try:
            ai_reply = self.ai.query(prompt)
            self.logger.debug("AI Query successful")
            self.logger.info("AI response received successfully")

            # Add AI reply as a new document
            new_doc_id = self.doc_store.add_document("AI Response", ai_reply)

            # Create a link to the new document
            link_text = f"[{selected_text}](doc:{new_doc_id})"
            old_doc = self.doc_store.get_document(current_doc_id)
            updated_body = old_doc[2].replace(selected_text, link_text)
            self.doc_store.update_document(current_doc_id, updated_body)

            self.logger.debug(f"Updated original document {current_doc_id} with embedded link.")
            on_link_created(current_doc_id, updated_body)

            on_success(new_doc_id)

        except Exception as e:
            self.logger.error(f"AI query failed: {e}")

    def get_document(self, doc_id):
        try:
            doc = self.doc_store.get_document(doc_id)
            self.logger.info(f"Retrieved document {doc_id}")
            return doc
        except Exception as e:
            self.logger.error(f"Failed to get document {doc_id}: {str(e)}")
            return None

    def set_api_key(self, api_key):
        try:
            self.ai.set_api_key(api_key)
            self.logger.info("API key successfully set")
        except Exception as e:
            self.logger.error(f"Failed to set API key: {str(e)}")

    def get_context_menu_actions(self):
        return {
            "Import CSV": self.doc_store.import_csv,
            "Export CSV": self.doc_store.export_csv,
            "Import API Key": lambda: None  # Hooked by GUI
        }
