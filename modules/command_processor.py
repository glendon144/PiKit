import openai
from modules.logger import Logger
from modules.document_store import DocumentStore

class CommandProcessor:
    def __init__(self, store: DocumentStore, ai_interface, logger=None):
        self.doc_store = store
        self.ai = ai_interface
        self.logger = logger if logger else Logger()

    def ask_question(self, prompt: str) -> str:
        """
        Send a standalone prompt to the AI and return its response.
        """
        try:
            self.logger.info(f"Sending standalone prompt to AI: {prompt}")
            response = self.ai.query(prompt)
            self.logger.info("AI response received successfully")
            return response
        except Exception as e:
            self.logger.error(f"AI query failed: {e}")
            return None

    def query_ai(self, selected_text: str, current_doc_id: int,
                 on_success, on_link_created,
                 prefix: str = None,
                 sel_start: int = None,
                 sel_end: int = None):
        """
        1) Builds a prompt from selected_text (with optional prefix)
        2) Queries the AI
        3) Saves the reply as a new document
        4) Embeds a markdown link back to the new doc in the original document
           using character offsets if provided, or falling back to substring replace.
        5) Invokes callbacks to update the GUI or CLI
        """
        # 1) Build prompt
        if prefix:
            prompt = f"{prefix} {selected_text}"
        else:
            prompt = f"Please expand on this: {selected_text}"
        self.logger.info(f"Sending prompt: {prompt}")

        # 2) Query AI
        try:
            reply = self.ai.query(prompt)
        except Exception as e:
            self.logger.error(f"AI query failed: {e}")
            return
        self.logger.info("AI query successful")

        # 3) Save reply as new document
        new_doc_id = self.doc_store.add_document("AI Response", reply)
        self.logger.info(f"Created new document {new_doc_id}")

        # 4) Embed markdown link in original document
        original = self.doc_store.get_document(current_doc_id)
        if original:
            body = original.get("body", "")
            link_md = f"[{selected_text}](doc:{new_doc_id})"
            if sel_start is not None and sel_end is not None and sel_start < sel_end <= len(body):
                # Embed by slicing
                updated = body[:sel_start] + link_md + body[sel_end:]
                self.logger.info(f"Embedded link at offsets {sel_start}-{sel_end}")
            else:
                # Fallback: substring replace
                if selected_text in body:
                    updated = body.replace(selected_text, link_md, 1)
                    self.logger.info("Embedded link by substring replace")
                else:
                    updated = body
                    self.logger.info("Selected text not found; no link embedded")
            self.doc_store.update_document(current_doc_id, updated)
        else:
            self.logger.error(f"Original document {current_doc_id} not found")

        # 5) Trigger callbacks
        on_link_created()
        on_success(new_doc_id)

    def set_api_key(self, api_key: str):
        """
        Proxy setting of API key to underlying AIInterface.
        """
        try:
            self.ai.set_api_key(api_key)
            self.logger.info("API key successfully set in AI interface")
        except Exception as e:
            self.logger.error(f"Failed to set API key: {e}")

    def get_context_menu_actions(self) -> dict:
        """
        Return mappings for GUI context menu items, if any.
        """
        return {
            "Import CSV": self.doc_store.import_csv,
            "Export CSV": self.doc_store.export_csv
        }
