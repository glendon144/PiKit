import tkinter as tk
from tkinter import ttk, simpledialog, messagebox, filedialog
from modules.hypertext_parser import insert_hyperlink_tags, extract_links

class DemoKitGUI(tk.Frame):
    def __init__(self, master, store, processor):
        super().__init__(master)
        self.master = master
        self.store = store
        self.processor = processor
        self.history = []

        self.pack(fill="both", expand=True)
        self.create_widgets()
        self.load_documents()

    def create_widgets(self):
        self.sidebar = tk.Listbox(self)
        self.sidebar.pack(side="left", fill="y")
        self.sidebar.bind("<<ListboxSelect>>", self.on_document_select)

        self.text = tk.Text(self, wrap="word")
        self.text.pack(side="right", fill="both", expand=True)

        self.ask_button = tk.Button(self, text="ASK", command=self.handle_ask)
        self.ask_button.pack(side="bottom")

        self.back_button = tk.Button(self, text="BACK", command=self.go_back)
        self.back_button.pack(side="bottom")

        self.context_menu = tk.Menu(self, tearoff=0)
        actions = self.processor.get_context_menu_actions()
        for name, method in actions.items():
            if name == "Import API Key":
                self.context_menu.add_command(label=name, command=self.import_api_key)
            else:
                self.context_menu.add_command(label=name, command=method)
        self.context_menu.add_command(label="ASK", command=self.handle_ask)
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
            print(f"[DEBUG] Document found: {doc}")
            self.sidebar.insert(tk.END, doc[1])

    def on_document_select(self, event):
        selection = event.widget.curselection()
        if selection:
            index = selection[0]
            doc_id = self.store.list_documents()[index][0]
            self.load_document_by_id(doc_id)

    def load_document_by_id(self, doc_id, return_point=None):
        try:
            doc = self.processor.get_document(doc_id)
            if not doc:
                raise ValueError("Document not found")
            self.current_doc_id = doc_id
            self.text.delete("1.0", tk.END)
            content = doc[2]
            self.text.insert("1.0", content)
            insert_hyperlink_tags(self.text, content)
            self.bind_hyperlinks()
            if return_point:
                self.text.see(return_point)
        except Exception as e:
            print(f"[ERROR] Failed to load document {doc_id}: {e}")
            messagebox.showerror("Error", f"Failed to load document: {e}")

    def bind_hyperlinks(self):
        for tag in self.text.tag_names():
            if tag.startswith("hyperlink_doc_"):
                doc_id = int(tag.split("_")[-1])
                self.text.tag_bind(tag, "<Button-1>", lambda e, d=doc_id: self.follow_link(d))

    def follow_link(self, doc_id):
        cursor_pos = self.text.index(tk.INSERT)
        self.history.append((self.current_doc_id, cursor_pos))
        self.load_document_by_id(doc_id)

    def go_back(self):
        if self.history:
            doc_id, index = self.history.pop()
            self.load_document_by_id(doc_id, return_point=index)
        else:
            messagebox.showinfo("Back", "No previous document in history.")

    def handle_ask(self):
        try:
            sel_start = self.text.index("sel.first")
            sel_end = self.text.index("sel.last")
            selected_text = self.text.get(sel_start, sel_end)
        except tk.TclError:
            messagebox.showinfo("Selection Error", "Please select text to ASK.")
            return

        print(f"[DEBUG] Selection: {sel_start} to {sel_end} → '{selected_text}'")
        custom_prefix = simpledialog.askstring("Prompt", "Enter prompt prefix:", initialvalue="Please expand on this: ")
        if custom_prefix is None:
            return

        if not custom_prefix.strip():
            custom_prefix = "Please expand on this: "

        full_prompt = f"{custom_prefix}{selected_text}"
        print(f"[DEBUG] Sending query: {full_prompt}")

        try:
            response = self.processor.ask_question(full_prompt)
            print(f"[DEBUG] AI response: {response}")
            if response:
                new_doc_id = self.store.add_document("AI Response", response)
                print(f"[DEBUG] Document added with ID: {new_doc_id}")
                link_tag = f"hyperlink_doc_{new_doc_id}"
                link_text = f"[link:{new_doc_id}:{selected_text}]"
                self.text.delete(sel_start, sel_end)
                self.text.insert(sel_start, link_text, (link_tag, "hyperlink"))
                self.text.tag_config("hyperlink", foreground="blue", underline=1)
                self.text.tag_bind(link_tag, "<Button-1>", lambda e, d=new_doc_id: self.follow_link(d))
                messagebox.showinfo("AI Response", f"Document #{new_doc_id} created.")
            else:
                messagebox.showwarning("AI Response", "The AI query failed or returned no result.")
        except Exception as e:
            print(f"[ERROR] AI query error: {e}")
            messagebox.showerror("Error", f"AI query error: {e}")

    def import_api_key(self):
        print("[DEBUG] Running import_api_key dialog")
        api_key = simpledialog.askstring("Enter API Key", "Please enter your OpenAI API key:")

        if api_key is None:
            print("[DEBUG] User cancelled API key entry.")
            return

        if not api_key.strip():
            print("[DEBUG] No API key entered.")
            messagebox.showwarning("API Key", "No API key was entered.")
            return

        try:
            self.processor.set_api_key(api_key.strip())
            messagebox.showinfo("API Key", "API key submitted successfully.")
            print("[DEBUG] API key submitted successfully")
        except Exception as e:
            print(f"[ERROR] Failed to set API key: {e}")
            messagebox.showerror("API Key", f"Failed to set API key: {e}")

