import tkinter as tk
from modules.document_store import DocumentStore
from modules.ai_interface import AIInterface
from modules.command_processor import CommandProcessor
import modules.gui_tkinter as gui_tkinter

if __name__ == "__main__":
    root = tk.Tk()
    root.title("DemoKit")

    store = DocumentStore("storage/documents.db")
    ai = AIInterface()
    processor = CommandProcessor(store, ai, None)  # Pass `None` or the logger if required

    app = gui_tkinter.DemoKitGUI(root, store, processor)
    app.pack(fill="both", expand=True)
    app.mainloop()

