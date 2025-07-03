import modules.gui_tkinter as gui_tkinter
from modules.document_store import DocumentStore
from modules.ai_interface import AIInterface
from modules.command_processor import CommandProcessor

if __name__ == "__main__":
    store = DocumentStore("storage/documents.db")
    ai = AIInterface()
    processor = CommandProcessor(store, ai, None)  # Pass `None` or the logger if required

    app = gui_tkinter.DemoKitGUI(store, processor)
    app.mainloop()