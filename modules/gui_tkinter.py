import os
import threading
import tkinter as tk
from tkinter import ttk, filedialog, simpledialog, messagebox
from pathlib import Path
from PIL import ImageTk
from modules import hypertext_parser, image_generator
from modules.logger import Logger


class DemoKitGUI(tk.Tk):
    """DemoKit with ASK/BACK/IMAGE and Import-Export."""  # brief docstring

    SIDEBAR_WIDTH = 320

    def __init__(self, doc_store, processor):
        super().__init__()
        self.doc_store = doc_store
        self.processor = processor
        self.logger: Logger = processor.logger if hasattr(processor, "logger") else Logger()
        self.current_doc_id = None
        self.history = []

        # ------------- window -------------
        self.title("Engelbart Journal – DemoKit")
        self.geometry("1200x800")
        self.columnconfigure(0, minsize=self.SIDEBAR_WIDTH, weight=0)
        self.columnconfigure(1, weight=3)
        self.rowconfigure(0, weight=1)

        # ------------- sidebar -------------
        sframe = tk.Frame(self)
        sframe.grid(row=0, column=0, sticky="nswe")
        self.sidebar = ttk.Treeview(
            sframe, columns=("ID", "Title", "Description"), show="headings"
        )
        for col, w in (("ID", 60), ("Title", 120), ("Description", 160)):
            self.sidebar.heading(col, text=col)
            self.sidebar.column(col, width=w, anchor="w", stretch=col == "Description")
        self.sidebar.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        ttk.Scrollbar(sframe, orient="vertical", command=self.sidebar.yview).pack(
            side=tk.RIGHT, fill=tk.Y
        )
        self.sidebar.bind("<<TreeviewSelect>>", self._on_select)

        # ------------- document + image pane -------------
        pane = tk.Frame(self)
        pane.grid(row=0, column=1, sticky="nswe", padx=4, pady=4)
        pane.rowconfigure(0, weight=3)   # text takes 3/4
        pane.rowconfigure(1, weight=1)   # image pane 1/4
        pane.columnconfigure(0, weight=1)

        self.text = tk.Text(pane, wrap="word")
        self.text.grid(row=0, column=0, sticky="nswe")
        self.text.tag_configure("green_link", foreground="green", underline=True)
        self.text.bind("<Button-3>", self._show_context_menu)

        self.img_label = tk.Label(pane)
        self.img_label.bind("<Button-1>", self._toggle_image)
        self.img_label.grid(row=1, column=0, sticky="nwe", pady=(8, 0))

        # Buttons
        btn_frame = tk.Frame(pane)
        btn_frame.grid(row=2, column=0, sticky="we", pady=(6, 0))
        for col in range(3):
            btn_frame.columnconfigure(col, weight=1)
        tk.Button(btn_frame, text="ASK", command=self._handle_ask).grid(
            row=0, column=0, sticky="we", padx=(0, 5)
        )
        tk.Button(btn_frame, text="BACK", command=self._go_back).grid(
            row=0, column=1, sticky="we", padx=(0, 5)
        )
        tk.Button(btn_frame, text="IMAGE", command=self._handle_image).grid(
            row=0, column=2, sticky="we"
        )

        # Context menu
        self.ctx_menu = tk.Menu(self, tearoff=0)
        for lbl, cmd in [("ASK", self._handle_ask),
                         ("IMAGE", self._handle_image),
                         ("Load API Key", self._load_api_key)]:
            self.ctx_menu.add_command(label=lbl, command=cmd)
        self.ctx_menu.add_separator()
        self.ctx_menu.add_command(label="Import", command=self._import_doc)
        self.ctx_menu.add_command(label="Export", command=self._export_doc)
        self.ctx_menu.add_separator()
        self.ctx_menu.add_command(label="Quit", command=self.destroy)

        self._refresh_sidebar()

    # ---------- sidebar ----------
    def _refresh_sidebar(self):
        self.sidebar.delete(*self.sidebar.get_children())
        for rec in self.doc_store.get_document_index():
            self.sidebar.insert("", "end", values=(rec["id"], rec["title"], rec["description"]))

    def _on_select(self, _evt=None):
        sel = self.sidebar.selection()
        if sel:
            doc_id = int(self.sidebar.item(sel[0])["values"][0])
            self._open_doc(doc_id)

    # ---------- document ----------
    def _open_doc(self, doc_id):
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

    # ---------- ASK ----------
    def _handle_ask(self):
        if not self.text.tag_ranges(tk.SEL):
            messagebox.showwarning("No selection", "Select text first.")
            return
        prompt_sel = self.text.get(tk.SEL_FIRST, tk.SEL_LAST)
        prefix = simpledialog.askstring(
            "Prompt", "Edit prompt:", initialvalue="Please expand on this: "
        )
        if prefix is None:
            return
        full_prompt = prefix + prompt_sel
        cid = self.current_doc_id

        def on_success(new_id):
            self.logger.info(f"AI reply stored as doc {new_id}")
            self._refresh_sidebar()
            self._insert_link(prompt_sel, new_id)

        self.processor.query_ai(full_prompt, cid, on_success=on_success, on_link_created=lambda _l: None)

    # ---------- IMAGE ----------
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
                self.after(0, lambda: self._show_image(tk_img))
            except Exception as exc:
                self.after(0, lambda: messagebox.showerror("DALL-E error", str(exc)))

        threading.Thread(target=worker, daemon=True).start()

    def _show_image(self, tk_img):
        self.img_label.configure(image=tk_img)
        self.img_label.image = tk_img  # retain reference
            # ----- IMAGE click handler -----
    def _toggle_image(self, _event=None):
        """First click enlarges the image; second click opens Save-As."""
        if self._last_pil_img is None:
            return

        if self._image_enlarged:
            # Second click → save dialog
            default = f"doc_{self.current_doc_id or 'unknown'}_image.png"
            path = filedialog.asksaveasfilename(
                title="Save image",
                defaultextension=".png",
                initialfile=default,
                initialdir=str(Path.home()),
            )
            if path:
                self._last_pil_img.save(path)
        else:
            # First click → enlarge
            self.text.grid_remove()  # hide document pane
            self.img_label.grid(row=0, column=0, sticky="nswe")
            self._image_enlarged = True

    # ---------- link insertion ----------
    def _insert_link(self, text, doc_id):
        idx = self.text.search(text, "1.0", tk.END)
        if not idx:
            return
        end_idx = f"{idx}+{len(text)}c"
        self.text.delete(idx, end_idx)
        md = f"[{text}](doc:{doc_id})"
        self.text.insert(idx, md)
        body = self.text.get("1.0", tk.END)
        hypertext_parser.parse_links(self.text, body, self._open_doc)
        if self.current_doc_id:
            self.doc_store.update_document(self.current_doc_id, body)

    # ---------- misc ----------
    def _go_back(self):
        if not self.history:
            messagebox.showinfo("Back", "No previous document.")
            return
        self._open_doc(self.history.pop())

    def _load_api_key(self):
        key = simpledialog.askstring("API Key", "Paste OpenAI key:", show="*")
        if key:
            self.processor.ai.set_api_key(key.strip())

    def _import_doc(self):
        path = filedialog.askopenfilename(title="Import text file")
        if not path:
            return
        try:
            text = Path(path).read_text(errors="ignore")
            text = "".join(ch for ch in text if 32 <= ord(ch) < 127 or ch in "\n\r\t")
            title = Path(path).name
            new_id = self.doc_store.add_document(title, text)
            self.logger.info(f"Imported doc {new_id}")
            self._refresh_sidebar()
        except Exception as exc:
            messagebox.showerror("Import failed", str(exc))

    def _export_doc(self):
        if not self.current_doc_id:
            messagebox.showinfo("Export", "No doc selected.")
            return
        save_path = filedialog.asksaveasfilename(
            title="Export document", defaultextension=".txt", initialfile=f"doc_{self.current_doc_id}.txt"
        )
        if not save_path:
            return
        body = self.text.get("1.0", tk.END).strip()
        try:
            Path(save_path).write_text(body)
            new_id = self.doc_store.add_document(f"Exported {Path(save_path).name}", body)
            self.logger.info(f"Exported doc to {save_path}; copy saved as {new_id}")
            self._refresh_sidebar()
            messagebox.showinfo("Export", f"Saved to {save_path}")
        except Exception as exc:
            messagebox.showerror("Export failed", str(exc))

    def _show_context_menu(self, event):
        self.ctx_menu.tk_popup(event.x_root, event.y_root)

# ── menu popup ────────────────────────────────────────────
def _show_menu(self, evt):
    try:
        self.menu.tk_popup(evt.x_root, evt.y_root)
    finally:
        self.menu.grab_release()
