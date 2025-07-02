# 🚀 PHASE 6.4.2.2 — FULL STABLE BUILD STARTING NOW 🚀

# Create clean workspace
workspace_phase6422_tkinter = "/mnt/data/demokit_phase6422_tkinter"
os.makedirs(f"{workspace_phase6422_tkinter}/modules", exist_ok=True)
os.makedirs(f"{workspace_phase6422_tkinter}/storage", exist_ok=True)
os.makedirs(f"{workspace_phase6422_tkinter}/credentials", exist_ok=True)
os.makedirs(f"{workspace_phase6422_tkinter}/logs", exist_ok=True)

# Reuse backend modules identical to previous build (clean preserved code)
with open(f"{workspace_phase6422_tkinter}/modules/document_store.py", "w") as f:
    f.write(document_store_code)
with open(f"{workspace_phase6422_tkinter}/modules/logger.py", "w") as f:
    f.write(logger_code)
with open(f"{workspace_phase6422_tkinter}/modules/hypertext_parser.py", "w") as f:
    f.write(hypertext_parser_code)
with open(f"{workspace_phase6422_tkinter}/modules/ai_interface.py", "w") as f:
    f.write(ai_interface_code)
with open(f"{workspace_phase6422_tkinter}/modules/command_processor.py", "w") as f:
    f.write(command_processor_code)
with open(f"{workspace_phase6422_tkinter}/modules/__init__.py", "w") as f:
    f.write("")

# Now patch GUI with:
# 1. Highlight wrapping instead of deletion.
# 2. Sidebar refresh after document creation.
# 3. Back button retained.
# 4. run() method included.

gui_tkinter_code_6422 = gui_tkinter_code + """

    def ask_ai_autolink(self):
        try:
            selected_text = self.text_editor.selection_get()
        except tk.TclError:
            messagebox.showwarning("No selection", "Please select text first.")
            return

        question = simpledialog.askstring("ASK AI", "Enter optional question or context:")
        query = (question + " " if question else "") + selected_text
        response = self.processor.ai.ask(query)
        new_doc_id = self.processor.doc_store.new_document(f"AI Response to: {selected_text}", response)

        # Instead of deleting, insert link markup wrapping selection
        self.text_editor.insert(tk.SEL_FIRST, f"[[")
        self.text_editor.insert(tk.SEL_LAST, f"|doc:{new_doc_id}]]")
        self.display_body_with_links(self.text_editor.get("1.0", tk.END))

        messagebox.showinfo("AI Response", f"AI response saved to Document {new_doc_id}.")
        self.load_documents()

    def run(self):
        self.root.mainloop()
"""

# Write patched GUI module
with open(f"{workspace_phase6422_tkinter}/modules/gui_tkinter.py", "w") as f:
    f.write(gui_tkinter_code_6422)

# Main launcher remains identical
with open(f"{workspace_phase6422_tkinter}/main.py", "w") as f:
    f.write("""
from modules import document_store, logger, ai_interface, command_processor, gui_tkinter

if __name__ == "__main__":
    doc_store = document_store.DocumentStore("storage/documents.csv")
    log = logger.Logger()
    ai = ai_interface.AIInterface()
    processor = command_processor.CommandProcessor(doc_store, ai, log)

    app = gui_tkinter.DemoKitGUI(processor)
    app.run()
""")

# Package Phase 6.4.2.2 Build
zip_path_phase6422_tkinter = "/mnt/data/demokit_phase6422_tkinter.zip"
with zipfile.ZipFile(zip_path_phase6422_tkinter, 'w') as zipf:
    for root, dirs, files in os.walk(workspace_phase6422_tkinter):
        for file in files:
            file_path = os.path.join(root, file)
            arcname = os.path.relpath(file_path, workspace_phase6422_tkinter)
            zipf.write(file_path, arcname)

zip_path_phase6422_tkinter

