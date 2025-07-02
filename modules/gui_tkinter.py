
import tkinter as tk
from tkinter import messagebox, simpledialog
import re
from modules import hypertext_parser

class DemoKitGUI(tk.Tk):
    _link_pattern = re.compile(r'\[([^\]]+)\]\(doc:(\d+)\)')

    def __init__(self, processor):
        super().__init__()
        self.processor = processor
        self.title("Engelbart Journal")
        self.geometry("1000x600")
            # ===== sidebar frame with fixed height listbox =====
            sidebar_frame = tk.Frame(self)
            sidebar_frame.pack(side=tk.LEFT, fill=tk.Y, padx=4, pady=4)

            self.sidebar = tk.Listbox(sidebar_frame, width=36, height=20, exportselection=False)
            self.sidebar.pack(side=tk.LEFT, fill=tk.X)

            sb = tk.Scrollbar(sidebar_frame, orient=tk.VERTICAL, command=self.sidebar.yview)
            sb.pack(side=tk.LEFT, fill=tk.Y)
            self.sidebar.config(yscrollcommand=sb.set)

            self.sidebar.bind("<<ListboxSelect>>", self._on_select)

        # ========== sidebar on the left using pack ================= #
        sidebar_frame = tk.Frame(self)
        sidebar_frame.pack(side=tk.LEFT, fill=tk.Y, padx=4, pady=4)

        self.sidebar = tk.Listbox(sidebar_frame, width=36, exportselection=False)
        self.sidebar.pack(side=tk.TOP, fill=tk.Y, expand=True)
        self.sidebar.bind("<<ListboxSelect>>", self._on_select)

        btn_frame = tk.Frame(sidebar_frame)
        btn_frame.pack(side=tk.TOP, fill=tk.X, pady=6)

        tk.Button(btn_frame, text="Edit", width=10,
                  command=self._sidebar_edit).pack(fill=tk.X)
        tk.Button(btn_frame, text="Delete", width=10,
                  command=self._sidebar_delete).pack(fill=tk.X, pady=(4,0))

        # keyboard shortcuts (global, work when listbox focused)
        self.bind_all("<Return>", lambda e: self._sidebar_edit())
        self.bind_all("<Delete>", lambda e: self._sidebar_delete())
        self.bind_all("<BackSpace>", lambda e: self._sidebar_delete())

        # ========== editor in remaining space ====================== #
        self.text_editor = tk.Text(self, wrap=tk.WORD)
        self.text_editor.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        # context menu in editor
        self.editor_menu = tk.Menu(self, tearoff=0)
        self.editor_menu.add_command(label="ASK AI + Link", command=self.ask_ai_autolink)
        for seq in ("<Button-3>", "<Control-Button-1>"):
            self.text_editor.bind(seq, self._popup_editor_menu)

        # back button at very bottom
        tk.Button(self, text="Back", command=self.go_back)                .pack(side=tk.BOTTOM, fill=tk.X)

        self.history = []
        self._refresh_sidebar()
        self.sidebar.focus_set()

    def _popup_editor_menu(self, event):
        try:
            self.editor_menu.tk_popup(event.x_root, event.y_root)
        finally:
            self.editor_menu.grab_release()

    # ----- sidebar helpers --------------------------------------- #
    def _refresh_sidebar(self):
        self.sidebar.delete(0, tk.END)
        self.docs = self.processor.doc_store.list_documents()
        for _, row in self.docs.iterrows():
            self.sidebar.insert(tk.END, f"{row['doc_id']}: {row['title']}")

    def _on_select(self, _=None):
        sel = self.sidebar.curselection()
        if not sel:
            return
        doc_id = int(str(self.sidebar.get(sel[0])).split(":")[0])
        self.open_document(doc_id, remember=True)

    # ----- navigation ------------------------------------------- #
    def open_document(self, doc_id, remember=False):
        if remember and getattr(self, 'current_doc_id', None):
            self.history.append(self.current_doc_id)
        self.current_doc_id = doc_id
        body = self.processor.view_document(doc_id)
        self._display_body(body)

    def go_back(self):
        if self.history:
            self.open_document(self.history.pop(), remember=False)

    # ----- display & links -------------------------------------- #
    def _display_body(self, body):
        self.text_editor.config(state="normal")
        self.text_editor.delete("1.0", tk.END)
        self.text_editor.insert("1.0", body)
        self._render_links()

    def _render_links(self):
        body = self.text_editor.get("1.0", "end-1c")
        plain, links = hypertext_parser.strip_and_extract_links(body)

        self.text_editor.delete("1.0", tk.END)
        self.text_editor.insert("1.0", plain)

        for tag in self.text_editor.tag_names():
            if tag.startswith("link-"):
                self.text_editor.tag_delete(tag)

        for i, (start, end, doc_id) in enumerate(links):
            tag = f"link-{i}"
            self.text_editor.tag_add(tag, f"1.0+{start}c", f"1.0+{end}c")
            self.text_editor.tag_config(tag, foreground="blue", underline=1)
            self.text_editor.tag_bind(tag, "<Enter>",
                                      lambda e: self.text_editor.config(cursor="hand2"))
            self.text_editor.tag_bind(tag, "<Leave>",
                                      lambda e: self.text_editor.config(cursor=""))
            self.text_editor.tag_bind(tag, "<Button-1>",
                                      lambda e, did=doc_id: self.open_document(did, True))

    # ----- sidebar actions --------------------------------------- #
    def _sidebar_edit(self):
        sel = self.sidebar.curselection()
        if sel:
            doc_id = int(str(self.sidebar.get(sel[0])).split(":")[0])
            self.open_document(doc_id, remember=True)

    def _sidebar_delete(self):
        sel = self.sidebar.curselection()
        if not sel:
            return
        doc_id = int(str(self.sidebar.get(sel[0])).split(":")[0])
        if messagebox.askyesno("Delete Document", f"Delete document {doc_id}?"):
            self.processor.doc_store.delete_document(doc_id)
            if getattr(self, 'current_doc_id', None) == doc_id:
                self.text_editor.delete("1.0", tk.END)
            self._refresh_sidebar()

    # ----- AI link ---------------------------------------------- #
    def ask_ai_autolink(self):
        ranges = self.text_editor.tag_ranges("sel")
        if not ranges:
            messagebox.showwarning("No selection", "Highlight text first.")
            return
        start, end = ranges[0], ranges[1]
        selected = self.text_editor.get(start, end).strip()

        prompt = simpledialog.askstring("ASK AI", "Optional question or context:")
        query = (prompt + " " if prompt else "") + selected
        response = self.processor.ai.ask(query)

        new_id = self.processor.doc_store.new_document(
            f"AI Response to: {selected}", response)

        link_markup = f"[{selected}](doc:{new_id})"
        self.text_editor.delete(start, end)
        self.text_editor.insert(start, link_markup)

        body = self.text_editor.get("1.0", "end-1c")
        self.processor.doc_store.edit_document(self.current_doc_id, body)

        self._render_links()
        self._refresh_sidebar()
        messagebox.showinfo("AI Response", f"AI response saved to Document {new_id}.")
