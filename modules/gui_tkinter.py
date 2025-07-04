import os
import threading
import tkinter as tk
from tkinter import ttk, filedialog, simpledialog, messagebox
from pathlib import Path
from PIL import ImageTk, Image

from modules import hypertext_parser, image_generator
from modules.logger import Logger


class DemoKitGUI(tk.Tk):
    """DemoKit GUI – ASK / IMAGE / BACK buttons, context menu, image overlay, and history."""

    SIDEBAR_WIDTH = 320

    # ───────── INITIALISATION ─────────
    def __init__(self, doc_store, processor):
        super().__init__()

        # state
        self.doc_store = doc_store
        self.processor = processor
        self.logger: Logger = getattr(processor, "logger", Logger())
        self.current_doc_id: int | None = None
        self.history: list[int] = []

        self._last_pil_img: Image | None = None
        self._last_tk_img: ImageTk.PhotoImage | None = None
        self._image_enlarged: bool = False

        # window
        self.title("Engelbart Journal – DemoKit")
        self.geometry("1200x800")
        self.columnconfigure(0, minsize=self.SIDEBAR_WIDTH, weight=0)
        self.columnconfigure(1, weight=1)
        self.rowconfigure(0, weight=1)

        self._build_sidebar()
        self._build_main_pane()
        self._build_context_menu()

        self._refresh_sidebar()

    # ═════════ UI BUILDERS ═════════
    def _build_sidebar(self):
        frame = tk.Frame(self)
        frame.grid(row=0, column=0, sticky="nswe")
        self.sidebar = ttk.Treeview(
            frame, columns=("ID", "Title", "Description"), show="headings"
        )
        for col, w in (("ID", 60), ("Title", 120), ("Description", 160)):
            self.sidebar.heading(col, text=col)
            self.sidebar.column(col, width=w, anchor="w", stretch=col == "Description")
        self.sidebar.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        ttk.Scrollbar(frame, orient="vertical", command=self.sidebar.yview).pack(
            side=tk.RIGHT, fill=tk.Y
        )
        self.sidebar.bind("<<TreeviewSelect>>", self._on_select)

    def _build_main_pane(self):
        pane = tk.Frame(self)
        pane.grid(row=0, column=1, sticky="nswe", padx=4, pady=4)
        pane.rowconfigure(0, weight=3)  # text 3/4
        pane.rowconfigure(1, weight=1)  # image 1/4
        pane.columnconfigure(0, weight=1)

        # text
        self.text = tk.Text(pane, wrap="word")
        self.text.grid(row=0, column=0, sticky="nswe")
        self.text.tag_configure("green_link", foreground="green", underline=True)
        self.text.bind("<Button-3>", self._show_context_menu)

        # image thumbnail / overlay
        self.img_label = tk.Label(pane)
        self.img_label.grid(row=1, column=0, sticky="ew", pady=(8, 0))
        self.img_label.bind("<Button-1>", self._toggle_image)

        # button row
        btns = tk.Frame(pane)
        btns.grid(row=2, column=0, sticky="we", pady=(6, 0))
        for c in range(3):
            btns.columnconfigure(c, weight=1)
        ttk.Button(btns, text="ASK",   command=self._handle_ask).grid(row=0, column=0, sticky="we", padx=(0, 4))
        ttk.Button(btns, text="BACK",  command=self._go_back).grid(row=0, column=1, sticky="we", padx=(0, 4))
        ttk.Button(btns, text="IMAGE", command=self._handle_image).grid(row=0, column=2, sticky="we")

    def _build_context_menu(self):
        self.ctx_menu = tk.Menu(self, tearoff=0)
        for lbl, fn in (
            ("ASK", self._handle_ask),
            ("IMAGE", self._handle_image),
            ("Load API Key", self._load_api_key),
        ):
            self.ctx_menu.add_command(label=lbl, command=fn)
        self.ctx_menu.add_separator()
        self.ctx_menu.add_command(label="Import", command=self._import_doc)
        self.ctx_menu.add_command(label="Export", command=self._export_doc)
        self.ctx_menu.add_separator()
        self.ctx_menu.add_command(label="Quit", command=self.destroy)

    # alias for widget bindings
    def _show_context_menu(self, event):
        return self._show_ctx(event)

    def _show_ctx(self, event):
        try:
            (self.ctx_menu.tk_popup if hasattr(self.ctx_menu, "tk_popup") else self.ctx_menu.post)(
                event.x_root, event.y_root
            )
        finally:
            self.ctx_menu.grab_release()

    # ═════════ SIDEBAR / DOC VIEW ═════════
    def _refresh_sidebar(self):
        self.sidebar.delete(*self.sidebar.get_children())
        for rec in self.doc_store.get_document_index():
            self.sidebar.insert(
                "", "end", values=(rec["id"], rec["title"], rec["description"])
            )

    def _on_select(self, _evt=None):
        sel = self.sidebar.selection()
        if sel:
            doc_id = int(self.sidebar.item(sel[0])["values"][0])
            self._open_doc(doc_id)

    def _open_doc(self, doc_id: int):
        if self._image_enlarged:
            self._restore_layout()
        if self.current_doc_id and doc_id != self.current_doc_id:
            self.history.append(self.current_doc_id)
        rec = self.doc_store.get_document(doc_id)
        if not rec:
            return
        self.current_doc_id = doc_id
        body = rec["body"] if isinstance(rec, dict) else rec[2]
        self.text.delete("1.0", tk.END)
        self.text.insert("1.0", body)
        hypertext_parser.parse_links(self.text, body, self._open_doc)

    # ═════════ ASK / IMAGE ═════════
    def _handle_ask(self):
        if not self.text.tag_ranges(tk.SEL):
            messagebox.showwarning("No selection", "Select text first.")
            return
        snippet = self.text.get(tk.SEL_FIRST, tk.SEL_LAST)
        prefix = simpledialog.askstring(
            "Prompt", "Edit prompt:", initialvalue="Please expand on this: "
        )
        if prefix is None:
            return
        full_prompt = prefix + snippet
        cid = self.current_doc_id

        def on_success(new_id):
            self.logger.info(f"AI reply stored as doc {new_id}")
            self._refresh_sidebar()
            self._insert_link(snippet, new_id)

        self.processor.query_ai(
            full_prompt, cid, on_success=on_success, on_link_created=lambda _: None
        )

    def _handle_image(self):
        if not self.text.tag_ranges(tk.SEL):
            messagebox.showwarning("No selection", "Select text first.")
            return
        prompt = self.text.get(tk.SEL_FIRST, tk.SEL_LAST).strip()
        if not prompt:
            return

        def worker():
            try:
                pil_img = image_generator.generate_image(prompt)
                tk_img = ImageTk.PhotoImage(pil_img)
                self.after(0, lambda: self._show_image(tk_img, pil_img))
            except Exception as exc:
                self.after(
                    0, lambda: messagebox.showerror("Image error", str(exc))
                )

        threading.Thread(target=worker, daemon=True).start()

    def _show_image(self, tk_img, pil_img):
        self._last_pil_img = pil_img
        self._last_tk_img = tk_img
        self._image_enlarged = False
        self.img_label.grid(row=1, column=0, sticky="ew", pady=(8, 0))
        self.img_label.configure(image=tk_img)
        self.img_label.image = tk_img

    def _toggle_image(self, _=None):
        if self._last_pil_img is None:
            return
        if self._image_enlarged:
            default = f"doc_{self.current_doc_id or 'unknown'}_image.png"
            path = filedialog.asksaveasfilename(
                title="Save image",
                defaultextension=".png",
                initialfile=default,
                initialdir=str(Path.home()),
            )
            if path:
                self._last_pil_img.save(path)
            self._restore_layout()
        else:
            self.text.grid_remove()
            self.img_label.grid(row=0, column=0, columnspan=2, sticky="nsew")
            self._image_enlarged = True

    def _restore_layout(self):
        self.img_label.grid(row=1, column=0, sticky="ew", pady=(8, 0))
        self.text.grid(row=0, column=1, rowspan=2, sticky="nsew")
        self._image_enlarged = False

    # ═════════ NAVIGATION ═════════
    def _go_back(self):
        if self._image_enlarged:
            self._restore_layout()
            return
        if self.history:
            self._open_doc(self.history.pop())
        self.img_label.configure(image="")
        self.img_label.grid_remove()
        self._last_pil_img = None
        self._last_tk_img = None

    # ═════════ HELPERS ═════════
    def _insert_link(self, text, doc_id):
        idx = self.text.search(text, "1.0", tk.END)
        if not idx:
            return
        end_idx = f"{idx}+{len(text)}c"
        self.text.delete(idx, end_idx)
        self.text.insert(idx, f"[{text}](doc:{doc_id})")
        body = self.text.get("1.0", tk.END)
        hypertext_parser.parse_links(self.text, body, self._open_doc)
        if self.current_doc_id:
            self.doc_store.update_document(self.current_doc_id, body)

    def _load_api_key(self):
        key = simpledialog.askstring("API Key", "Paste OpenAI key:", show="*")
        if key:
            self.processor.ai.set_api_key(key.strip())

    # ---------- Import ----------
    def _import_doc(self):
        path = filedialog.askopenfilename(title="Import text file")
        if not path:
            return
        try:
            text = Path(path).read_text(errors="ignore")
            text = "".join(
                ch for ch in text if 32 <= ord(ch) < 127 or ch in "\n\r\t"
            )
            title = Path(path).name
            new_id = self.doc_store.add_document(title, text)
            self.logger.info(f"Imported doc {new_id}")
            self._refresh_sidebar()
        except Exception as exc:
            messagebox.showerror("Import error", str(exc))

    # ---------- Export ----------
    def _export_doc(self):
        if self.current_doc_id is None:
            messagebox.showwarning("No document", "Nothing to export.")
            return
        path = filedialog.asksaveasfilename(
            title="Export", defaultextension=".txt"
        )
        if not path:
            return
        try:
            rec = self.doc_store.get_document(self.current_doc_id)
            body = rec["body"] if isinstance(rec, dict) else rec[2]
            Path(path).write_text(body)
            self.logger.info(f"Exported doc {self.current_doc_id} -> {path}")
        except Exception as exc:
            messagebox.showerror("Export error", str(exc))


if __name__ == "__main__":
    from modules import document_store, command_processor

    store = document_store.DocumentStore("storage/documents.db")
    proc = command_processor.CommandProcessor(store)
    DemoKitGUI(store, proc).mainloop()

import os
import threading
import tkinter as tk
from tkinter import ttk, filedialog, simpledialog, messagebox
from pathlib import Path
from PIL import ImageTk, Image

from modules import hypertext_parser, image_generator
from modules.logger import Logger


class DemoKitGUI(tk.Tk):
    """DemoKit GUI – ASK / IMAGE / BACK buttons, context menu, image overlay, and history."""

    SIDEBAR_WIDTH = 320

    # ───────── INITIALISATION ─────────
    def __init__(self, doc_store, processor):
        super().__init__()

        # state
        self.doc_store = doc_store
        self.processor = processor
        self.logger: Logger = getattr(processor, "logger", Logger())
        self.current_doc_id: int | None = None
        self.history: list[int] = []

        self._last_pil_img: Image | None = None
        self._last_tk_img: ImageTk.PhotoImage | None = None
        self._image_enlarged: bool = False

        # window
        self.title("Engelbart Journal – DemoKit")
        self.geometry("1200x800")
        self.columnconfigure(0, minsize=self.SIDEBAR_WIDTH, weight=0)
        self.columnconfigure(1, weight=1)
        self.rowconfigure(0, weight=1)

        self._build_sidebar()
        self._build_main_pane()
        self._build_context_menu()

        self._refresh_sidebar()

    # ═════════ UI BUILDERS ═════════
    def _build_sidebar(self):
        frame = tk.Frame(self)
        frame.grid(row=0, column=0, sticky="nswe")
        self.sidebar = ttk.Treeview(
            frame, columns=("ID", "Title", "Description"), show="headings"
        )
        for col, w in (("ID", 60), ("Title", 120), ("Description", 160)):
            self.sidebar.heading(col, text=col)
            self.sidebar.column(col, width=w, anchor="w", stretch=col == "Description")
        self.sidebar.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        ttk.Scrollbar(frame, orient="vertical", command=self.sidebar.yview).pack(
            side=tk.RIGHT, fill=tk.Y
        )
        self.sidebar.bind("<<TreeviewSelect>>", self._on_select)

    def _build_main_pane(self):
        pane = tk.Frame(self)
        pane.grid(row=0, column=1, sticky="nswe", padx=4, pady=4)
        pane.rowconfigure(0, weight=3)  # text 3/4
        pane.rowconfigure(1, weight=1)  # image 1/4
        pane.columnconfigure(0, weight=1)

        # text
        self.text = tk.Text(pane, wrap="word")
        self.text.grid(row=0, column=0, sticky="nswe")
        self.text.tag_configure("green_link", foreground="green", underline=True)
        self.text.bind("<Button-3>", self._show_context_menu)

        # image thumbnail / overlay
        self.img_label = tk.Label(pane)
        self.img_label.grid(row=1, column=0, sticky="ew", pady=(8, 0))
        self.img_label.bind("<Button-1>", self._toggle_image)

        # button row
        btns = tk.Frame(pane)
        btns.grid(row=2, column=0, sticky="we", pady=(6, 0))
        for c in range(3):
            btns.columnconfigure(c, weight=1)
        ttk.Button(btns, text="ASK",   command=self._handle_ask).grid(row=0, column=0, sticky="we", padx=(0, 4))
        ttk.Button(btns, text="BACK",  command=self._go_back).grid(row=0, column=1, sticky="we", padx=(0, 4))
        ttk.Button(btns, text="IMAGE", command=self._handle_image).grid(row=0, column=2, sticky="we")

    def _build_context_menu(self):
        self.ctx_menu = tk.Menu(self, tearoff=0)
        for lbl, fn in (
            ("ASK", self._handle_ask),
            ("IMAGE", self._handle_image),
            ("Load API Key", self._load_api_key),
        ):
            self.ctx_menu.add_command(label=lbl, command=fn)
        self.ctx_menu.add_separator()
        self.ctx_menu.add_command(label="Import", command=self._import_doc)
        self.ctx_menu.add_command(label="Export", command=self._export_doc)
        self.ctx_menu.add_separator()
        self.ctx_menu.add_command(label="Quit", command=self.destroy)

    # alias for widget bindings
    def _show_context_menu(self, event):
        return self._show_ctx(event)

    def _show_ctx(self, event):
        try:
            (self.ctx_menu.tk_popup if hasattr(self.ctx_menu, "tk_popup") else self.ctx_menu.post)(
                event.x_root, event.y_root
            )
        finally:
            self.ctx_menu.grab_release()

    # ═════════ SIDEBAR / DOC VIEW ═════════
    def _refresh_sidebar(self):
        self.sidebar.delete(*self.sidebar.get_children())
        for rec in self.doc_store.get_document_index():
            self.sidebar.insert(
                "", "end", values=(rec["id"], rec["title"], rec["description"])
            )

    def _on_select(self, _evt=None):
        sel = self.sidebar.selection()
        if sel:
            doc_id = int(self.sidebar.item(sel[0])["values"][0])
            self._open_doc(doc_id)

    def _open_doc(self, doc_id: int):
        if self._image_enlarged:
            self._restore_layout()
        if self.current_doc_id and doc_id != self.current_doc_id:
            self.history.append(self.current_doc_id)
        rec = self.doc_store.get_document(doc_id)
        if not rec:
            return
        self.current_doc_id = doc_id
        body = rec["body"] if isinstance(rec, dict) else rec[2]
        self.text.delete("1.0", tk.END)
        self.text.insert("1.0", body)
        hypertext_parser.parse_links(self.text, body, self._open_doc)

    # ═════════ ASK / IMAGE ═════════
    def _handle_ask(self):
        if not self.text.tag_ranges(tk.SEL):
            messagebox.showwarning("No selection", "Select text first.")
            return
        snippet = self.text.get(tk.SEL_FIRST, tk.SEL_LAST)
        prefix = simpledialog.askstring(
            "Prompt", "Edit prompt:", initialvalue="Please expand on this: "
        )
        if prefix is None:
            return
        full_prompt = prefix + snippet
        cid = self.current_doc_id

        def on_success(new_id):
            self.logger.info(f"AI reply stored as doc {new_id}")
            self._refresh_sidebar()
            self._insert_link(snippet, new_id)

        self.processor.query_ai(
            full_prompt, cid, on_success=on_success, on_link_created=lambda _: None
        )

    def _handle_image(self):
        if not self.text.tag_ranges(tk.SEL):
            messagebox.showwarning("No selection", "Select text first.")
            return
        prompt = self.text.get(tk.SEL_FIRST, tk.SEL_LAST).strip()
        if not prompt:
            return

        def worker():
            try:
                pil_img = image_generator.generate_image(prompt)
                tk_img = ImageTk.PhotoImage(pil_img)
                self.after(0, lambda: self._show_image(tk_img, pil_img))
            except Exception as exc:
                self.after(
                    0, lambda: messagebox.showerror("Image error", str(exc))
                )

        threading.Thread(target=worker, daemon=True).start()

    def _show_image(self, tk_img, pil_img):
        self._last_pil_img = pil_img
        self._last_tk_img = tk_img
        self._image_enlarged = False
        self.img_label.grid(row=1, column=0, sticky="ew", pady=(8, 0))
        self.img_label.configure(image=tk_img)
        self.img_label.image = tk_img

    def _toggle_image(self, _=None):
        if self._last_pil_img is None:
            return
        if self._image_enlarged:
            default = f"doc_{self.current_doc_id or 'unknown'}_image.png"
            path = filedialog.asksaveasfilename(
                title="Save image",
                defaultextension=".png",
                initialfile=default,
                initialdir=str(Path.home()),
            )
            if path:
                self._last_pil_img.save(path)
            self._restore_layout()
        else:
            self.text.grid_remove()
            self.img_label.grid(row=0, column=0, columnspan=2, sticky="nsew")
            self._image_enlarged = True

    def _restore_layout(self):
        self.img_label.grid(row=1, column=0, sticky="ew", pady=(8, 0))
        self.text.grid(row=0, column=1, rowspan=2, sticky="nsew")
        self._image_enlarged = False

    # ═════════ NAVIGATION ═════════
    def _go_back(self):
        if self._image_enlarged:
            self._restore_layout()
            return
        if self.history:
            self._open_doc(self.history.pop())
        self.img_label.configure(image="")
        self.img_label.grid_remove()
        self._last_pil_img = None
        self._last_tk_img = None

    # ═════════ HELPERS ═════════
    def _insert_link(self, text, doc_id):
        idx = self.text.search(text, "1.0", tk.END)
        if not idx:
            return
        end_idx = f"{idx}+{len(text)}c"
        self.text.delete(idx, end_idx)
        self.text.insert(idx, f"[{text}](doc:{doc_id})")
        body = self.text.get("1.0", tk.END)
        hypertext_parser.parse_links(self.text, body, self._open_doc)
        if self.current_doc_id:
            self.doc_store.update_document(self.current_doc_id, body)

    def _load_api_key(self):
        key = simpledialog.askstring("API Key", "Paste OpenAI key:", show="*")
        if key:
            self.processor.ai.set_api_key(key.strip())

    # ---------- Import ----------
    def _import_doc(self):
        path = filedialog.askopenfilename(title="Import text file")
        if not path:
            return
        try:
            text = Path(path).read_text(errors="ignore")
            text = "".join(
                ch for ch in text if 32 <= ord(ch) < 127 or ch in "\n\r\t"
            )
            title = Path(path).name
            new_id = self.doc_store.add_document(title, text)
            self.logger.info(f"Imported doc {new_id}")
            self._refresh_sidebar()
        except Exception as exc:
            messagebox.showerror("Import error", str(exc))

    # ---------- Export ----------
    def _export_doc(self):
        if self.current_doc_id is None:
            messagebox.showwarning("No document", "Nothing to export.")
            return
        path = filedialog.asksaveasfilename(
            title="Export", defaultextension=".txt"
        )
        if not path:
            return
        try:
            rec = self.doc_store.get_document(self.current_doc_id)
            body = rec["body"] if isinstance(rec, dict) else rec[2]
            Path(path).write_text(body)
            self.logger.info(f"Exported doc {self.current_doc_id} -> {path}")
        except Exception as exc:
            messagebox.showerror("Export error", str(exc))


if __name__ == "__main__":
    from modules import document_store, command_processor

    store = document_store.DocumentStore("storage/documents.db")
    proc = command_processor.CommandProcessor(store)
    DemoKitGUI(store, proc).mainloop()

