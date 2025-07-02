
from modules import document_store, logger, ai_interface, command_processor, gui_tkinter

if __name__ == "__main__":
    doc_store = document_store.DocumentStore("storage/documents.csv")
    log = logger.Logger()
    ai = ai_interface.AIInterface()
    processor = command_processor.CommandProcessor(doc_store, log, ai)

    app = gui_tkinter.DemoKitGUI(processor)
    app.mainloop()
