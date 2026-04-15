from pathlib import Path
from modules.document_store import DocumentStore
from modules.command_processor import CommandProcessor
from modules.gui_tkinter import DemoKitGUI
from modules.ai_interface import AIInterface
# Plugins
from modules.memory_dialog  import open_memory_dialog
from modules.ecm_settings_dialog import open_ecm_settings_dialog
from modules.opml_extras_plugin import install_opml_extras_into_app
from modules.save_as_text_plugin_v3 import install_save_as_text_into_app
from modules.image_render_overlay import attach_image_rendering
# NOTE: Do NOT import the old modules.opml_extras_plugin.
# NOTE: Do NOT import export_doc_patch; gui_tkinter already has robust _export_doc.

def main():
    # Ensure the storage directory exists
    Path("storage").mkdir(parents=True, exist_ok=True)

    # Initialize the document store
    doc_store = DocumentStore("storage/documents.db")

    # Initialize the AI interface
    ai = AIInterface()

    # Initialize the command processor with doc store and AI
    processor = CommandProcessor(doc_store, ai)

    # Launch the GUI
    app = DemoKitGUI(doc_store, processor)
    attach_image_rendering(app)
    open_memory_dialog(app)   # adds Tools → Memory… and Ctrl+M
    app.open_ecm_settings_dialog = lambda: open_ecm_settings_dialog(app)

    # Wire plugins
    install_opml_extras_into_app(app)      # URL→OPML, Convert→OPML, Batch Convert
    install_save_as_text_into_app(app)     # Save Binary As Text (DB-safe)

    app.mainloop()

if __name__ == "__main__":
    main()
