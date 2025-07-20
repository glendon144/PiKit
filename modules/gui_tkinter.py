import os
import threading
import tkinter as tk
from tkinter import ttk, filedialog, simpledialog, messagebox
from pathlib import Path
from PIL import ImageTk, Image
from modules import hypertext_parser, image_generator
from modules.logger import Logger
import subprocess
import sys
import json

class DemoKitGUI(tk.Tk):
    """DemoKit GUI – ASK / IMAGE / BACK buttons, context menu, image overlay, and history."""

    SIDEBAR_WIDTH = 320

    def __init__(self, doc_store, processor):
        super().__init__()
        self.doc_store = doc_store
        self.processor = processor
        self.logger: Logger = getattr(processor, "logger", Logger())
        self.current_doc_id: int | None = None
        self.history: list[int] = []

        self._last_pil_img: Image.Image | None = None
        self._last_tk_img: ImageTk.PhotoImage | None = None
        self._image_enlarged: bool = False

        self.title("Engelbart Journal – DemoKit")
        self.geometry("1200x800")
        self.columnconfigure(0, minsize=self.SIDEBAR_WIDTH, weight=0)
        self.columnconfigure(1, weight=1)
        self.rowconfigure(0, weight=1)

        self._build_sidebar()
        self._build_main_pane()
        self._build_context_menu()

        menubar = tk.Menu(self)
        filemenu = tk.Menu(menubar, tearoff=0)
        filemenu.add_command(label="Import", command=self._import_doc)
        filemenu.add_command(label="Export Current", command=self._export_doc)
        filemenu.add_separator()
        filemenu.add_command(label="Export to Intraweb", command=self.export_and_launch_server)
        filemenu.add_separator()
        filemenu.add_command(label="Quit", command=self.destroy)
        menubar.add_cascade(label="File", menu=filemenu)
        self.config(menu=menubar)

        self._refresh_sidebar()

    def _build_sidebar(self):
        frame = tk.Frame(self)
        frame.grid(row=0, column=0, sticky="nswe")
        self.sidebar = ttk.Treeview(frame, columns=("ID","Title","Description"), show="headings")
        for col,w in (("ID",60),("Title",120),("Description",160)):
            self.sidebar.heading(col, text=col)
            self.sidebar.column(col, width=w, anchor="w", stretch=(col=="Description"))
        self.sidebar.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        ttk.Scrollbar(frame, orient="vertical", command=self.sidebar.yview).pack(side=tk.RIGHT, fill=tk.Y)
        self.sidebar.bind("<<TreeviewSelect>>", self._on_select)
        self.sidebar.bind("<Delete>", lambda e: self._on_delete_clicked())

    def _on_select(self, event):
        sel = self.sidebar.selection()
        if not sel:
            return
        item = self.sidebar.item(sel[0])
        try:
            nid = int(item["values"][0])
        except (ValueError,TypeError):
            return
        if self.current_doc_id is not None:
            self.history.append(self.current_doc_id)
        self.current_doc_id = nid
        doc = self.doc_store.get_document(nid)
        if doc:
            self._render_document(doc)

    def _build_main_pane(self):
        pane = tk.Frame(self)
        pane.grid(row=0, column=1, sticky="nswe", padx=4, pady=4)
        pane.rowconfigure(0, weight=3)
        pane.rowconfigure(1, weight=1)
        pane.columnconfigure(0, weight=1)

        self.text = tk.Text(pane, wrap="word")
        self.text.grid(row=0, column=0, sticky="nswe")
        self.text.tag_configure("link", foreground="green", underline=True)
        self.text.bind("<Button-3>", self._show_context_menu)
        self.text.bind("<Delete>", lambda e: self._on_delete_clicked())

        self.img_label = tk.Label(pane)
        self.img_label.grid(row=1, column=0, sticky="ew", pady=(8,0))
        self.img_label.bind("<Button-1>", lambda e: self._toggle_image())

        btns = tk.Frame(pane)
        btns.grid(row=2, column=0, sticky="we", pady=(6,0))
        acts = [("ASK",self._handle_ask),("BACK",self._go_back),
                ("DELETE",self._on_delete_clicked),("IMAGE",self._handle_image),("FLASK",self.export_and_launch_server)]
        for i,(lbl,cmd) in enumerate(acts):
            ttk.Button(btns, text=lbl, command=cmd).grid(row=0, column=i, sticky="we", padx=(0,4))

    def _build_context_menu(self):
        self.context_menu = tk.Menu(self, tearoff=0)
        self.context_menu.add_command(label="ASK", command=self._handle_ask)
        self.context_menu.add_command(label="Delete", command=self._on_delete_clicked)
        self.context_menu.add_separator()
        self.context_menu.add_command(label="Import", command=self._import_doc)
        self.context_menu.add_command(label="Export", command=self._export_doc)

    def _show_context_menu(self, event):
        try:
            self.context_menu.tk_popup(event.x_root, event.y_root)
        finally:
            self.context_menu.grab_release()

    def _handle_ask(self):
        try:
            start = self.text.index(tk.SEL_FIRST)
            end   = self.text.index(tk.SEL_LAST)
            selected_text = self.text.get(start, end)
        except tk.TclError:
            messagebox.showwarning("ASK","Please select some text first.")
            return
        cid = self.current_doc_id
        def on_success(nid):
            messagebox.showinfo("ASK",f"Created new document {nid}.")
            self._refresh_sidebar()
            # replace selection with link
            self.text.delete(start,end)
            link_md = f"[{selected_text}](doc:{nid})"
            self.text.insert(start, link_md)
            full = self.text.get("1.0",tk.END)
            hypertext_parser.parse_links(self.text, full, self._on_link_click)
        prefix = simpledialog.askstring("Prefix","Optional prefix:",initialvalue="Please expand:")
        self.processor.query_ai(selected_text, cid, on_success, lambda *_:None,
                                 prefix=prefix, sel_start=None, sel_end=None)

    def _go_back(self):
        if not self.history:
            messagebox.showinfo("BACK","No history.")
            return
        prev = self.history.pop()
        self.current_doc_id = prev
        doc = self.doc_store.get_document(prev)
        if doc:
            self._render_document(doc)
        else:
            messagebox.showerror("BACK",f"Document {prev} not found.")

    def _handle_image(self):
        try:
            start = self.text.index(tk.SEL_FIRST)
            end   = self.text.index(tk.SEL_LAST)
            prompt = self.text.get(start,end).strip()
        except tk.TclError:
            messagebox.showwarning("IMAGE","Please select some text first.")
            return
        def wrk():
            try:
                pil = image_generator.generate_image(prompt)
                self._last_pil_img = pil
                thumb = pil.copy()
                thumb.thumbnail((800,400))
                self._last_tk_img = ImageTk.PhotoImage(thumb)
                self._image_enlarged = False
                self.after(0,lambda: self.img_label.configure(image=self._last_tk_img))
            except Exception as e:
                self.after(0,lambda: messagebox.showerror("Image Error",str(e)))
        threading.Thread(target=wrk,daemon=True).start()

    def _toggle_image(self):
        if not self._last_pil_img:
            return
        if not self._image_enlarged:
            win = tk.Toplevel(self)
            win.title("Image Preview")
            sw,sh=self.winfo_screenwidth(),self.winfo_screenheight()
            iw,ih=self._last_pil_img.size
            win.geometry(f"{min(iw,sw)}x{min(ih,sh)}")
            canvas=tk.Canvas(win)
            hbar=ttk.Scrollbar(win,orient='horizontal',command=canvas.xview)
            vbar=ttk.Scrollbar(win,orient='vertical',command=canvas.yview)
            canvas.configure(xscrollcommand=hbar.set,yscrollcommand=vbar.set,
                             scrollregion=(0,0,iw,ih))
            canvas.grid(row=0,column=0,sticky='nsew')
            hbar.grid(row=1,column=0,sticky='we')
            vbar.grid(row=0,column=1,sticky='ns')
            win.grid_rowconfigure(0,weight=1)
            win.grid_columnconfigure(0,weight=1)
            tk_img=ImageTk.PhotoImage(self._last_pil_img)
            canvas.create_image(0,0,anchor='nw',image=tk_img)
            canvas.image=tk_img
            win.bind("<Button-1>",lambda e: self._toggle_image())
            self._image_enlarged = True
        else:
            default=f"document_{self.current_doc_id}.png"
            path=filedialog.asksaveasfilename(
                title="Save Image",initialfile=default,
                defaultextension=".png",filetypes=[("PNG","*.png"),("All Files","*.*")]
            )
            if path:
                try:
                    self._last_pil_img.save(path)
                    messagebox.showinfo("Save Image",f"Image saved to:\n{path}")
                except Exception as e:
                    messagebox.showerror("Save Image",f"Error saving image:{e}")
            self._image_enlarged=False

    def _import_doc(self):
        path=filedialog.askopenfilename(title="Import",filetypes=[("Text","*.txt"),("All","*.*")])
        if not path:
            return
        content=Path(path).read_text(encoding="utf-8")
        title=Path(path).stem
        nid=self.doc_store.add_document(title,content)
        self.logger.info(f"Imported {nid}")
        self._refresh_sidebar()
        doc=self.doc_store.get_document(nid)
        if doc:
            self._render_document(doc)

    def _export_doc(self):
        if self.current_doc_id is None:
            messagebox.showwarning("Export","No document loaded.")
            return
        doc=self.doc_store.get_document(self.current_doc_id)
        if not doc:
            messagebox.showerror("Export","Not found.")
            return
        default=f"document_{self.current_doc_id}.txt"
        path=filedialog.asksaveasfilename(
            title="Export",initialfile=default,defaultextension=".txt",
            filetypes=[("Text","*.txt"),("All","*.*")]
        )
        if not path:
            return
        Path(path).write_text(doc["body"],encoding="utf-8")
        messagebox.showinfo("Export",f"Saved to:\n{path}")

    def export_and_launch_server(self):
        export_path=Path("exported_docs")
        export_path.mkdir(exist_ok=True)
        for doc in self.doc_store.get_document_index():
            data=self.doc_store.get_document(doc["id"])
            if data:
                out={"id":data["id"],"title":data["title"],"body":data["body"]}
                with open(export_path/f"{data['id']}.json","w",encoding="utf-8") as f:
                    json.dump(out, f, indent=2)
        def launch():
            fp=Path("modules")/"flask_server.py"
            if fp.exists():
                subprocess.Popen([sys.executable,str(fp)])
        threading.Thread(target=launch,daemon=True).start()
        messagebox.showinfo("Server Started","Flask server launched at http://127.0.0.1:5050")

    def _refresh_sidebar(self):
        self.sidebar.delete(*self.sidebar.get_children())
        for doc in self.doc_store.get_document_index():
            self.sidebar.insert("","end",
                                values=(doc["id"],doc["title"],doc["description"]))


    def _on_delete_clicked(self):
        """Delete the currently selected document."""
        sel = self.sidebar.selection()
        if not sel:
            messagebox.showwarning("Delete", "No document selected.")
            return

        item = self.sidebar.item(sel[0])
        try:
            nid = int(item["values"][0])
        except (ValueError, TypeError):
            messagebox.showerror("Delete", "Invalid document ID.")
            return

        confirm = messagebox.askyesno("Confirm Delete", f"Delete document ID {nid}?")
        if not confirm:
            return

        self.doc_store.delete_document(nid)
        self._refresh_sidebar()
        self.text.delete("1.0", tk.END)
        self.img_label.configure(image="")
        self.current_doc_id = None
        self._last_pil_img = None
        self._last_tk_img = None
        self._image_enlarged = False
        messagebox.showinfo("Deleted", f"Document {nid} has been deleted.")

    def _render_document(self, doc):
        self.text.delete("1.0",tk.END)
        self.img_label.configure(image="")
        self._last_pil_img=None
        self._last_tk_img=None
        self._image_enlarged=False
        body=doc.get("body") if isinstance(doc,dict) else doc[2]
        self.text.insert(tk.END,body)
        hypertext_parser.parse_links(self.text,body,self._on_link_click)

    def _on_link_click(self,doc_id):
        if self.current_doc_id is not None:
            self.history.append(self.current_doc_id)
        self.current_doc_id=doc_id
        doc=self.doc_store.get_document(doc_id)
        if doc:
            self._render_document(doc)
