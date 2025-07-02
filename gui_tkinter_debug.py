
import tkinter as tk
from tkinter import ttk, simpledialog, messagebox, filedialog
from modules.hypertext_parser import insert_hyperlink_tags, extract_links

class DemoKitGUI(tk.Frame):
    def __init__(self, master, store, processor):
        super().__init__(master)
        self.master = master
        self.store = store
        self.processor = processor

        print("[DEBUG] Initializing GUI")
        self.pack(fill="both", expand=True)
        self.create_widgets()
        self.load_documents()

    def create_widgets(self):
        print("[DEBUG] Creating widgets")
        self.sidebar = tk.Listbox(self)
        self.sidebar.pack(side="left", fill="y")
        self.sidebar.bind("<<ListboxSelect>>", self.on_document_select)

        self.text = tk.Text(self, wrap="word")
        self.text.pack(side="right", fill="both", expand=True)

        self.ask_button = tk.Button(self, text="ASK", command=self.handle_ask)
        self.ask_button.pack(side="bottom")

        self.context_menu = tk.Menu(self, tearoff=0)
        actions = self.processor.get_context_menu_actions()
        for name, method in actions.items():
            self.context_menu.add_command(label=name, command=method)
        self.text.bind("<Button-3>", self.show_context_menu)

    def show_context_menu(self, event):
        try:
            self.context_menu.tk_popup(event.x_root, event.y_root)
        finally:
            self.context_menu.grab_release()

    def load_documents(self):
        print("[DEBUG] Loading documents")
        self.sidebar.delete(0, tk.END)
        for doc in self.store.list_documents():
            print(f"[DEBUG] Document loaded: {doc}")
            self.sidebar.insert(tk.END, doc[1])  # doc[1] is title

    def on_document_select(self, event):
        print("[DEBUG] Document selected")
        selection = event.widget.curselection()
        if selection:
            index = selection[0]
            doc_id = self.store.list_documents()[index][0]
            doc = self.processor.get_document(doc_id)
            print(f"[DEBUG] Displaying document ID {doc_id}")
            self.text.delete("1.0", tk.END)
            self.text.insert("1.0", doc[2])  # doc[2] is body
            insert_hyperlink_tags(self.text, doc[2])

    def handle_ask(self):
        try:
            prompt = self.text.get("sel.first", "sel.last")
        except tk.TclError:
            messagebox.showinfo("Selection Error", "Please select text to ASK.")
            return

        prepend_text = simpledialog.askstring("Query Prefix", "Prepend something to your query:", initialvalue="Please expand on this: ")
        if prepend_text:
            prompt = prepend_text + prompt

        print(f"[DEBUG] Sending query: {prompt}")
        response = self.processor.ask_question(prompt)
        if response:
            print("[DEBUG] AI Query successful. Response received.")
            messagebox.showinfo("AI Response", "The AI query was successful.")
            new_doc_id = self.store.add_document("AI Response", response)
            self.text.insert(tk.SEL_LAST, f" [See: {new_doc_id}] ", ("hyperlink",))
        else:
            print("[DEBUG] AI Query failed or returned no result.")
            messagebox.showwarning("AI Response", "The AI query failed or returned no result.")

    def import_api_key(self):
        print("[DEBUG] Prompting for API key")
        api_key = simpledialog.askstring("Enter API Key", "Please enter your OpenAI API key:")
        if api_key:
            self.processor.set_api_key(api_key)
            messagebox.showinfo("API Key", "API key submitted successfully.")
            print("[DEBUG] API key submitted successfully.")
        else:
            messagebox.showwarning("API Key", "No API key was entered.")
            print("[DEBUG] No API key was entered.")
