import tkinter as tk
from tkinter import ttk, messagebox, simpledialog
from tkinter.scrolledtext import ScrolledText
from modules.hypertext_parser import insert_hyperlink_tags

class DemoKitGUI(tk.Frame):
    def __init__(self, root, store, processor):
        super().__init__(root)
        self.root = root
        self.store = store
        self.processor = processor
        self.current_doc_id = None
        self.previous_doc_id = None
        self.previous_cursor_index = None

        self.sidebar = tk.Listbox(self)
        self.sidebar.pack(side="left", fill="y")
        self.sidebar.bind("<<ListboxSelect>>", self.on_select)

        self.text = ScrolledText(self, wrap="word")
        self.text.pack(side="right", fill="both", expand=True)

        self.ask_button = tk.Button(self, text="ASK", command=self.handle_ask)
        self.ask_button.pack(side="bottom")

        self.back_button = tk.Button(self, text="BACK", command=self.go_back)
        self.back_button.pack(side="bottom")

        self.load_documents()
        self.text.tag_config("hyperlink", foreground="blue", underline=True)
        self.text.tag_bind("hyperlink", "<Button-1>", self.follow_link)

    def load_documents(self):
        self.sidebar.delete(0, tk.END)
        self.documents = self.store.list_documents()
        for doc in self.documents:
            self.sidebar.insert(tk.END, f"{doc[0]}: {doc[1]}")

    def on_select(self, event):
        if not self.sidebar.curselection():
            return
        index = self.sidebar.curselection()[0]
        doc_id = self.documents[index][0]
        self.display_document(doc_id)

    def display_document(self, doc_id):
        doc = self.store.get_document(doc_id)
        if doc:
            self.previous_doc_id = self.current_doc_id
            self.previous_cursor_index = self.text.index(tk.INSERT)
            self.current_doc_id = doc_id
            self.text.delete("1.0", tk.END)
            self.text.insert(tk.END, doc[2])
            insert_hyperlink_tags(self.text)

    def go_back(self):
        if self.previous_doc_id:
            self.display_document(self.previous_doc_id)
            if self.previous_cursor_index:
                self.text.mark_set(tk.INSERT, self.previous_cursor_index)
                self.text.see(self.previous_cursor_index)

    def follow_link(self, event):
        index = self.text.index(f"@{event.x},{event.y}")
        for tag in self.text.tag_names(index):
            if tag.startswith("link_"):
                target_id = int(tag.split("_")[1])
                self.display_document(target_id)

    def handle_ask(self):
        selected_text = self.text.get(tk.SEL_FIRST, tk.SEL_LAST)
        if not selected_text.strip():
            messagebox.showerror("Selection Error", "Please select some text to ask about.")
            return

        api_key = self.processor.ai.get_api_key()
        if not api_key:
            messagebox.showerror("API Key Error", "Please set the OpenAI API key first.")
            return

        self.processor.query_ai(
            selected_text,
            callback=self.insert_ai_response
        )

    def insert_ai_response(self, response):
        if not response:
            messagebox.showerror("AI Error", "No response from AI.")
            return

        new_doc_id = self.store.add_document("AI Response", response)
        self.load_documents()
        self.text.insert(tk.INSERT, f"[link:{new_doc_id}:See AI Response]")
        self.store.update_document(self.current_doc_id, self.text.get("1.0", tk.END))
        insert_hyperlink_tags(self.text)
        messagebox.showinfo("Success", "AI response added as a new document.")
