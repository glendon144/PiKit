
import tkinter as tk
from tkinter import ttk, messagebox, simpledialog
from modules.logger import log
from modules.hypertext_parser import parse_links

class DemoKitGUI(tk.Frame):
    def __init__(self, master, doc_store, processor):
        super().__init__(master)
        self.master = master
        self.processor = processor
        self.pack(fill="both", expand=True)

        self.create_widgets()
        self.render_index()

        self.previous_doc_id = None

    def create_widgets(self):
        self.sidebar = tk.Listbox(self)
        self.sidebar.pack(side="left", fill="y")
        self.sidebar.bind("<<ListboxSelect>>", self.on_select_document)

        self.text = tk.Text(self, wrap="word")
        self.text.pack(side="left", fill="both", expand=True)
        self.text.bind("<Button-3>", self.show_context_menu)

        self.ask_button = tk.Button(self, text="ASK", command=self.handle_ask)
        self.ask_button.pack(side="bottom", fill="x")

        self.back_button = tk.Button(self, text="BACK", command=self.go_back)
        self.back_button.pack(side="bottom", fill="x")

        self.context_menu = tk.Menu(self, tearoff=0)
        self.context_menu.add_command(label="Import OpenAI Key", command=self.import_openai_key)
        self.context_menu.add_command(label="ASK", command=self.handle_ask)

    def render_index(self):
        self.sidebar.delete(0, tk.END)
        for doc in self.processor.doc_store.list_documents():
            self.sidebar.insert(tk.END, f"{doc[0]}")

    def on_select_document(self, event):
        try:
            index = self.sidebar.curselection()[0]
            doc_id = int(self.sidebar.get(index))
            self.previous_doc_id = getattr(self, "current_doc_id", None)
            self.current_doc_id = doc_id
            doc = self.processor.doc_store.get_document(doc_id)
            self.render_document(doc)
        except IndexError:
            pass

    def render_document(self, doc):
        self.text.delete("1.0", tk.END)
        self.text.insert("1.0", doc[2])
        parse_links(self.text, doc[2], self.open_doc_by_id)

    def open_doc_by_id(self, doc_id):
        doc = self.processor.doc_store.get_document(doc_id)
        self.previous_doc_id = getattr(self, "current_doc_id", None)
        self.current_doc_id = doc_id
        self.render_document(doc)

    def go_back(self):
        if self.previous_doc_id is not None:
            doc = self.processor.doc_store.get_document(self.previous_doc_id)
            self.current_doc_id, self.previous_doc_id = self.previous_doc_id, self.current_doc_id
            self.render_document(doc)

    def show_context_menu(self, event):
        try:
            self.context_menu.tk_popup(event.x_root, event.y_root)
        finally:
            self.context_menu.grab_release()

    def import_openai_key(self):
        key = simpledialog.askstring("Import OpenAI Key", "Enter your OpenAI API key:", show="*")
        if key:
            self.processor.ai.set_api_key(key)
            log.info("API key successfully set")
            messagebox.showinfo("Success", "API key saved successfully.")
        else:
            messagebox.showwarning("Warning", "No API key was entered.")
            log.debug("No API key was entered")

    def handle_ask(self):
        try:
            selected_text = self.text.get(tk.SEL_FIRST, tk.SEL_LAST)
        except tk.TclError:
            messagebox.showwarning("No Selection", "Please select some text first.")
            return

        prefix = simpledialog.askstring("Optional Prompt Prefix", "Add a prompt (optional):")
        prompt = f"{prefix.strip()} {selected_text}" if prefix else selected_text
        self.processor.query_ai(
            prompt,
            self.current_doc_id,
            self.on_ai_success,
             self.on_link_created
        )

    def on_ai_success(self, new_doc_id):
        self.render_index()
        self.open_doc_by_id(new_doc_id)

    def on_link_created(self, *args):
        self.render_document(self.processor.doc_store.get_document(self.current_doc_id))
