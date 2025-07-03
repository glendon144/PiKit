import tkinter as tk
from tkinter import ttk, messagebox, simpledialog
from modules import hypertext_parser

class DemoKitGUI(tk.Tk):
    def __init__(self, doc_store, processor):
        super().__init__()
        self.doc_store = doc_store
        self.processor = processor

        self.title("Engelbart Journal")
        self.geometry("1100x650")

        # Sidebar with Treeview
        sidebar_frame = tk.Frame(self, bg="orange")
        sidebar_frame.pack(side=tk.LEFT, fill=tk.Y, padx=4, pady=4)

        self.sidebar = ttk.Treeview(
            sidebar_frame, columns=('ID', 'Title', 'Description'),
            show='headings', height=25
        )
        self.sidebar.heading('ID', text='ID')
        self.sidebar.heading('Title', text='Title')
        self.sidebar.heading('Description', text='Description')
        self.sidebar.column('ID', width=60, anchor='center')
        self.sidebar.column('Title', width=220, anchor='w')
        self.sidebar.column('Description', width=480, anchor='w')
        self.sidebar.pack(side=tk.LEFT, fill=tk.Y)

        sb = tk.Scrollbar(sidebar_frame, orient=tk.VERTICAL, command=self.sidebar.yview)
        sb.pack(side=tk.LEFT, fill=tk.Y)
        self.sidebar.config(yscrollcommand=sb.set)
        self.sidebar.bind("<<TreeviewSelect>>", self._on_select)

        # Main text widget
        main_frame = tk.Frame(self, bg="lightblue")
        main_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=4, pady=4)
        self.text = tk.Text(main_frame, wrap="word", cursor="xterm")
        self.text.pack(side=tk.TOP, fill=tk.BOTH, expand=True)
        self.text.tag_configure("green_link", foreground="green", underline=True)
        self.text.bind("<Button-3>", self.show_context_menu)

        # Button frame
        button_frame = tk.Frame(main_frame, bg="yellow")
        button_frame.pack(side=tk.BOTTOM, fill=tk.X, pady=4)
        self.ask_button = tk.Button(button_frame, text="ASK", command=self.handle_ask)
        self.ask_button.pack(side=tk.LEFT, padx=5)

        # Right-click context menu
        self.context_menu = tk.Menu(self, tearoff=0)
        self.context_menu.add_command(label="ASK", command=self.handle_ask)
        self.context_menu.add_command(label="Load API Key", command=self.load_api_key)
        self.context_menu.add_command(label="IMPORT", command=self.import_text)
        self.context_menu.add_command(label="EXPORT", command=self.export_text)

        self.load_documents()

    def show_context_menu(self, event):
        try:
            self.context_menu.tk_popup(event.x_root, event.y_root)
        finally:
            self.context_menu.grab_release()

    def handle_ask(self):
        selected_text = self.text.get(tk.SEL_FIRST, tk.SEL_LAST) if self.text.tag_ranges(tk.SEL) else ""
        if not selected_text:
            messagebox.showwarning("No text selected", "Please select text to expand.")
            return

        prefix = simpledialog.askstring("Query", "Enter prompt prefix:", initialvalue="Please expand on this: ")
        if prefix is None:
            return

        prompt = prefix + selected_text
        current_doc_id = self.current_doc_id

        def on_success(reply):
            new_doc_id = self.processor.doc_store.add_document("AI Reply", reply)
            self.insert_link(selected_text, new_doc_id)

        self.processor.query_ai(
            selected_text=prompt,
            current_doc_id=current_doc_id,
            on_success=on_success,
            on_link_created=lambda link_text: None
        )

    def insert_link(self, selected_text, doc_id):
        start = self.text.search(selected_text, "1.0", stopindex=tk.END)
        if start:
            end = f"{start}+{len(selected_text)}c"
            self.text.delete(start, end)
            link_text = f"{selected_text} → ({doc_id})"
            self.text.insert(start, link_text)
            self.text.tag_add("green_link", start, f"{start}+{len(link_text)}c")

    def _on_select(self, event):
        selected_item = self.sidebar.focus()
        if selected_item:
            doc_id = int(self.sidebar.item(selected_item)['values'][0])
            doc = self.doc_store.get_document(doc_id)
            if doc:
                self.current_doc_id = doc_id
                self.text.delete("1.0", tk.END)
                self.text.insert("1.0", doc[2])
                hypertext_parser.parse_links(self.text, doc[2], self.open_doc_by_id)

    def open_doc_by_id(self, doc_id):
        doc = self.doc_store.get_document(doc_id)
        if doc:
            self.current_doc_id = doc_id
            self.text.delete("1.0", tk.END)
            self.text.insert("1.0", doc[2])
            hypertext_parser.parse_links(self.text, doc[2], self.open_doc_by_id)

    def load_documents(self):
        self.sidebar.delete(*self.sidebar.get_children())
        for doc_id, title, body in self.doc_store.get_document_index():
            preview = body.replace("\n", " ")[:100] + "..."
            self.sidebar.insert("", "end", values=(doc_id, title, preview))

    def load_api_key(self):
        key = simpledialog.askstring("API Key", "Enter your OpenAI API key:")
        if key:
            self.processor.set_api_key(key)

    def import_text(self):
        text = simpledialog.askstring("Import", "Paste text to import:")
        if text:
            new_doc_id = self.doc_store.add_document("Imported", text)
            self.load_documents()

    def export_text(self):
        current = self.text.get("1.0", tk.END).strip()
        if current:
            print("Exported text:\n", current)
