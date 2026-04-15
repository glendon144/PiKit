# gui_tkinter.py — Universal, compatibility-hardened GUI for PiKit/DemoKit
# Release: v1.31 (2025-08-23)
#
# Key features:
# - Restored image rendering (BLOB + Base64 string/bytes)
# - OPML outline view (expandable Treeview)
# - Sidebar previews + Size column
# - File menu, context menu, Export, Save as Text
# - Flask “Intraweb” server button
# - ASK + green link refresh stable
# - Reparse Links working
# This build borrows the proven image workflow (label + thumbnail + zoom window) from your phase2_3 prefs file
# while keeping all universal shims and features.

from __future__ import annotations

import base64
from io import BytesIO
from pathlib import Path
import sqlite3
import tkinter as tk
from tkinter import ttk, filedialog, simpledialog, messagebox
from typing import Any, Tuple, Optional
import xml.etree.ElementTree as ET

# ---- Optional image support (Pillow) ----
try:
    from PIL import Image, ImageTk  # type: ignore

    PIL_AVAILABLE = True
except Exception:
    PIL_AVAILABLE = False


# ---- Safe importer ----
def _try_import(modpath: str, name: str | None = None, default=None):
    try:
        mod = __import__(modpath, fromlist=["*"])
        return getattr(mod, name, mod) if name else mod
    except Exception:
        return default


# ---- Primary module names ----
command_processor_mod = _try_import("modules.command_processor")
document_store_mod = _try_import("modules.document_store")
hypertext_parser_mod = _try_import("modules.hypertext_parser")
renderer_mod = _try_import("modules.renderer")
opml_plugin = _try_import("modules.opml_extras_plugin_v3")
logger_mod = _try_import("modules.logger")
ecm_dialog_mod = _try_import("modules.ecm_settings_dialog")
flask_server_path = Path("modules") / "flask_server.py"

# ---- Legacy/alternate module names (shims) ----
if command_processor_mod is None:
    command_processor_mod = _try_import("modules.cmdprocessor")
if hypertext_parser_mod is None:
    hypertext_parser_mod = _try_import("modules.hypertextparser")

# Resolve CP class (CommandProcessor or CmdProcessor)
CommandProcessor = None
if command_processor_mod:
    CommandProcessor = getattr(
        command_processor_mod,
        "CommandProcessor",
        getattr(command_processor_mod, "CmdProcessor", None),
    )

# Resolve link parser function(s)
parse_links = None
if hypertext_parser_mod:
    for fname in ("parse_links", "parse_links_v2", "reparse_links"):
        parse_links = getattr(hypertext_parser_mod, fname, None)
        if callable(parse_links):
            break

# Optional renderer helpers
render_binary_preview = getattr(renderer_mod or object(), "render_binary_preview", None)
render_binary_as_text = getattr(renderer_mod or object(), "render_binary_as_text", None)

# Logger
Logger = getattr(logger_mod or object(), "Logger", None)
open_ecm_settings_dialog = getattr(
    ecm_dialog_mod or object(),
    "open_ecm_settings_dialog",
    None,
)

# ---------- Helpers ----------


def _human_size(n: int) -> str:
    for unit in ("B", "KB", "MB", "GB"):
        if n < 1024 or unit == "GB":
            return f"{n:.0f} {unit}" if unit == "B" else f"{n/1024:.1f} {unit}"
        n /= 1024
    return f"{n:.1f} GB"


def _extract_title_content(doc: Any) -> Tuple[str, Any]:
    """Return (title, content) from dict / sqlite3.Row / list/tuple / other."""
    # sqlite3.Row → dict
    if isinstance(doc, sqlite3.Row):
        m = dict(doc)
        title = str(m.get("title", m.get("name", m.get("heading", ""))) or "")
        # Prefer textual content fields
        for key in ("content", "body", "text", "raw", "data", "value", "description"):
            if key in m and m[key] not in (None, ""):
                return title, m[key]
        # Fallback: longest string
        best = ""
        for v in m.values():
            if isinstance(v, str) and len(v) > len(best):
                best = v
        return title, best if best else str(m)

    # dict
    if isinstance(doc, dict):
        title = str(doc.get("title", doc.get("name", doc.get("heading", ""))) or "")
        for key in ("content", "body", "text", "raw", "data", "value", "description"):
            if key in doc and doc[key] not in (None, ""):
                return title, doc[key]
        # fallback
        best = ""
        for v in doc.values():
            if isinstance(v, str) and len(v) > len(best):
                best = v
        return title, best if best else str(doc)

    # tuple/list
    if isinstance(doc, (list, tuple)):
        title = ""
        if len(doc) > 1 and isinstance(doc[1], str):
            title = doc[1]
        # choose longest string as content
        str_elems = [s for s in doc if isinstance(s, str)]
        if str_elems:
            content_val = max(str_elems, key=len)
            return title, content_val
        # else bytes
        for v in doc:
            if isinstance(v, (bytes, bytearray)):
                return title, v
        return title, str(doc)

    return "", str(doc)


_BASE64_CHARS = set(
    b"ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/=\r\n \t"
)


def _looks_like_b64_text(s: str) -> bool:
    if not isinstance(s, str) or len(s) < 200:
        return False
    # strip header
    i = s.find("base64,")
    payload = s[i + 7 :] if i != -1 else s
    payload = "".join(payload.split())
    if len(payload) % 4 != 0:
        return False
    head = payload[:200]
    return all(ord(ch) < 128 and ch.encode() in _BASE64_CHARS for ch in head)


def _decode_b64_text(s: str) -> Optional[bytes]:
    i = s.find("base64,")
    payload = s[i + 7 :] if i != -1 else s
    payload = "".join(payload.split())
    try:
        return base64.b64decode(payload, validate=True)
    except Exception:
        try:
            missing = (-len(payload)) % 4
            return base64.b64decode(payload + ("=" * missing))
        except Exception:
            return None


def _looks_like_b64_bytes(b: bytes) -> bool:
    if not isinstance(b, (bytes, bytearray)) or len(b) < 200:
        return False
    head = b[:400]
    if any(ch not in _BASE64_CHARS for ch in head):
        return False
    stripped = b"".join(ch for ch in b if ch in _BASE64_CHARS)
    return len(stripped) % 4 == 0


def _decode_b64_bytes(b: bytes) -> Optional[bytes]:
    payload = b"".join(ch for ch in b if ch in _BASE64_CHARS)
    try:
        return base64.b64decode(payload, validate=True)
    except Exception:
        try:
            missing = (-len(payload)) % 4
            return base64.b64decode(payload + b"=" * missing)
        except Exception:
            return None


def _make_preview(title: str, content: Any) -> str:
    generic = {"ai response", "response", "untitled", ""}
    tnorm = (title or "").strip().lower()
    if tnorm not in generic and not tnorm.startswith("opml"):
        return title
    if isinstance(content, str) and content.strip():
        words = content.strip().split()
        preview = " ".join(words[:10])
        return (preview + "…") if len(words) > 10 else preview
    return title or "(untitled)"


# ---------- App ----------


class App(tk.Tk):
    def __init__(self, *args, **kwargs):
        doc_store_pos = args[0] if len(args) >= 1 else None
        processor_pos = args[1] if len(args) >= 2 else None

        super().__init__()
        self.title("PiKit / DemoKit — GUI v1.31")

        self.geometry("1180x780")

        # Public state
        self.current_doc_id: int | None = None
        self.history: list[int] = []
        self._last_selection: Tuple[str, str] | None = None
        self._current_content: str | bytes | None = None  # for Reparse Links
        self._mode: str = "text"  # 'text' or 'opml'
        self._last_pil_img: Optional[Image.Image] = None
        self._last_tk_img: Optional[ImageTk.PhotoImage] = None
        self._image_zoom_win: Optional[tk.Toplevel] = None

        self.doc_store = kwargs.get("doc_store") or doc_store_pos
        self.processor = kwargs.get("processor") or processor_pos
        self.logger = getattr(self.processor, "logger", Logger() if Logger else None)

        if (
            self.doc_store is None
            and document_store_mod
            and hasattr(document_store_mod, "DocumentStore")
        ):
            try:
                self.doc_store = document_store_mod.DocumentStore()
            except Exception as e:
                print("Warning: DocumentStore failed to init:", e)

        if self.processor is None and CommandProcessor:
            try:
                self.processor = CommandProcessor()
            except Exception as e:
                print("Warning: CommandProcessor failed to init:", e)

        self._build_ui()
        self.protocol("WM_DELETE_WINDOW", self._on_close)
        self._refresh_index()

    # ---------- UI ----------
    def _build_ui(self):
        root = self

        # Menubar (File + OPML + View)
        menubar = tk.Menu(root)
        filemenu = tk.Menu(menubar, tearoff=0)
        filemenu.add_command(label="Import Text…", command=self._import_text_file)
        filemenu.add_command(label="Export Current…", command=self._export_current)
        filemenu.add_separator()
        filemenu.add_command(
            label="Export to Intraweb (Flask)…", command=self._export_and_launch_flask
        )
        filemenu.add_separator()
        filemenu.add_command(label="Quit", command=self._on_close)
        menubar.add_cascade(label="File", menu=filemenu)

        opmlmenu = tk.Menu(menubar, tearoff=0)
        opmlmenu.add_command(label="Open OPML/XML…", command=self._open_opml_from_file)
        opmlmenu.add_command(
            label="Convert Selection → OPML", command=self._convert_selection_to_opml
        )
        menubar.add_cascade(label="OPML", menu=opmlmenu)

        root.config(menu=menubar)

        # Toolbar
        bar = ttk.Frame(root)
        bar.pack(side="top", fill="x")

        ttk.Button(bar, text="Ask", command=self._on_ask).pack(
            side="left", padx=4, pady=4
        )
        ttk.Button(bar, text="Back", command=self._go_back).pack(
            side="left", padx=4, pady=4
        )
        ttk.Button(bar, text="Open by ID", command=self._open_by_id).pack(
            side="left", padx=4, pady=4
        )

        ttk.Separator(bar, orient="vertical").pack(side="left", fill="y", padx=6)

        ttk.Button(bar, text="Import Dir", command=self._import_directory).pack(
            side="left", padx=4, pady=4
        )
        ttk.Button(bar, text="Open OPML", command=self._open_opml_from_file).pack(
            side="left", padx=4, pady=4
        )
        ttk.Button(
            bar, text="Convert → OPML", command=self._convert_selection_to_opml
        ).pack(side="left", padx=4, pady=4)

        ttk.Separator(bar, orient="vertical").pack(side="left", fill="y", padx=6)

        ttk.Button(bar, text="Search", command=self._on_search_clicked).pack(
            side="left", padx=4, pady=4
        )
        ttk.Button(bar, text="Reparse Links", command=self._reparse_links).pack(
            side="left", padx=4, pady=4
        )
        ttk.Button(bar, text="ECM", command=self._on_ecm).pack(
            side="left", padx=4, pady=4
        )
        ttk.Button(bar, text="Flask", command=self._export_and_launch_flask).pack(
            side="left", padx=4, pady=4
        )

        # Panes
        self.panes = ttk.Panedwindow(root, orient="horizontal")
        self.panes.pack(fill="both", expand=True)

        # Left: index
        left = ttk.Frame(self.panes)
        self.sidebar = ttk.Treeview(
            left, columns=("id", "title", "size"), show="headings", height=20
        )
        self.sidebar.heading("id", text="ID")
        self.sidebar.heading("title", text="Title / Preview")
        self.sidebar.heading("size", text="Size")
        self.sidebar.column("id", width=80, anchor="w")
        self.sidebar.column("title", width=420, anchor="w")
        self.sidebar.column("size", width=90, anchor="e")
        self.sidebar.pack(fill="both", expand=True)
        self.sidebar.bind("<<TreeviewSelect>>", self._on_sidebar_select)

        left_bottom = ttk.Frame(left)
        left_bottom.pack(fill="x")
        ttk.Button(left_bottom, text="Refresh", command=self._refresh_index).pack(
            side="left", padx=4, pady=4
        )
        self.panes.add(left, weight=1)

        # Right stack: Text pane + Image label + OPML tree
        right = ttk.Frame(self.panes)
        self.right_stack = ttk.Frame(right)
        self.right_stack.pack(fill="both", expand=True)

        # Text mode widgets
        self.text_frame = ttk.Frame(self.right_stack)
        self.text = tk.Text(self.text_frame, wrap="word", undo=True)
        yscroll = ttk.Scrollbar(
            self.text_frame, orient="vertical", command=self.text.yview
        )
        self.text.configure(yscrollcommand=yscroll.set)
        self.text.pack(side="top", fill="both", expand=True)
        yscroll.pack(side="right", fill="y")

        # Image label (below text)
        self.img_label = tk.Label(self.text_frame)
        self.img_label.pack(side="bottom", fill="x", pady=(6, 0))
        self.img_label.bind("<Button-1>", lambda e: self._toggle_image_zoom())

        # Context menu on text
        self.text.bind("<Button-3>", self._show_context_menu)
        self.text.bind("<KeyPress>", self._on_text_keypress, add="+")

        # OPML Tree mode widgets
        self.tree_frame = ttk.Frame(self.right_stack)
        self.opml_tree = ttk.Treeview(self.tree_frame, show="tree")
        tree_scroll = ttk.Scrollbar(
            self.tree_frame, orient="vertical", command=self.opml_tree.yview
        )
        self.opml_tree.configure(yscrollcommand=tree_scroll.set)
        self.opml_tree.pack(side="left", fill="both", expand=True)
        tree_scroll.pack(side="left", fill="y")

        # Start in text mode
        self._show_text_mode()

        self.panes.add(right, weight=3)

        # Status
        self.status = tk.StringVar(value="Ready")
        ttk.Label(root, textvariable=self.status, anchor="w").pack(
            side="bottom", fill="x"
        )

        # Context menu
        self.context_menu = tk.Menu(root, tearoff=0)
        self.context_menu.add_command(label="Ask", command=self._on_ask)
        self.context_menu.add_command(
            label="Export Current…", command=self._export_current
        )
        self.context_menu.add_separator()
        self.context_menu.add_command(
            label="Save Visible Text…", command=self._save_visible_text
        )

        # Shortcuts
        root.bind_all("<Control-Return>", lambda e: self._on_ask())
        root.bind_all("<Control-Shift-O>", lambda e: self._convert_selection_to_opml())
        root.bind_all("<Control-u>", lambda e: self._open_opml_from_file())

    def _show_context_menu(self, event):
        try:
            self.context_menu.tk_popup(event.x_root, event.y_root)
        finally:
            self.context_menu.grab_release()

    def _on_text_keypress(self, event):
        if self.processor and hasattr(self.processor, "ingest_tk_keypress"):
            try:
                self.processor.ingest_tk_keypress(event)
            except Exception:
                pass

    def _on_close(self):
        if self.processor and hasattr(self.processor, "shutdown"):
            try:
                self.processor.shutdown()
            except Exception:
                pass
        self.destroy()

    # ---------- Mode switching ----------
    def _show_text_mode(self):
        self._mode = "text"
        self.tree_frame.pack_forget()
        self.text_frame.pack(fill="both", expand=True)

    def _show_tree_mode(self):
        self._mode = "opml"
        self.text_frame.pack_forget()
        self.tree_frame.pack(fill="both", expand=True)

    # ---------- Selection handling ----------
    def _on_text_selection_changed(self, event=None):
        if self._mode != "text":
            self._last_selection = None
            return
        try:
            start = self.text.index("sel.first")
            end = self.text.index("sel.last")
            self._last_selection = (start, end)
        except Exception:
            self._last_selection = None

    def _get_selected_text(self) -> str:
        if self._mode != "text":
            return ""
        try:
            return self.text.get("sel.first", "sel.last")
        except Exception:
            pass
        if self._last_selection:
            s, e = self._last_selection
            try:
                return self.text.get(s, e)
            except Exception:
                return ""
        return ""

    # ---------- Index / navigation ----------
    def _approx_payload_size(self, content: Any) -> int:
        if isinstance(content, (bytes, bytearray)):
            # Could be image bytes OR base64 text as bytes
            if _looks_like_b64_bytes(content):
                b = _decode_b64_bytes(content)
                return len(b) if b else len(content)
            return len(content)
        if isinstance(content, str):
            if _looks_like_b64_text(content):
                b = _decode_b64_text(content)
                return len(b) if b else len(content)
            return len(content.encode("utf-8", errors="ignore"))
        return 0

    def _refresh_index(self):
        try:
            self.sidebar.delete(*self.sidebar.get_children())
        except Exception:
            return

        rows = []
        if self.doc_store and hasattr(self.doc_store, "get_document_index"):
            try:
                rows = self.doc_store.get_document_index() or []
            except Exception as e:
                print("get_document_index failed:", e)

        for row in rows:
            # Support dict/Row/tuple
            if isinstance(row, sqlite3.Row):
                m = dict(row)
                doc_id = m.get("id", m.get("doc_id", m.get("pk", None)))
                title = str(m.get("title", m.get("name", "")) or "")
                content = (
                    m.get("content")
                    or m.get("body")
                    or m.get("text")
                    or m.get("raw")
                    or m.get("data")
                    or m.get("value")
                    or m.get("description")
                    or ""
                )
            elif isinstance(row, dict):
                doc_id = row.get("id") or row.get("doc_id") or row.get("pk")
                title = str(row.get("title", row.get("name", "")) or "")
                content = (
                    row.get("content")
                    or row.get("body")
                    or row.get("text")
                    or row.get("raw")
                    or row.get("data")
                    or row.get("value")
                    or row.get("description")
                    or ""
                )
            else:
                # tuple/list
                doc_id = (
                    row[0] if isinstance(row, (list, tuple)) and len(row) > 0 else None
                )
                title = (
                    row[1]
                    if isinstance(row, (list, tuple))
                    and len(row) > 1
                    and isinstance(row[1], str)
                    else ""
                )
                content = (
                    row[2] if isinstance(row, (list, tuple)) and len(row) > 2 else ""
                )

            preview = _make_preview(title, content)
            size = self._approx_payload_size(content)
            self.sidebar.insert("", "end", values=(doc_id, preview, _human_size(size)))

    def _on_sidebar_select(self, event=None):
        sel = self.sidebar.selection()
        if not sel:
            return
        item = self.sidebar.item(sel[0])
        vals = item.get("values") or []
        if not vals:
            return
        doc_id = vals[0]
        self._open_doc_id(doc_id)

    def _open_doc_id(self, doc_id):
        try:
            doc_id = int(doc_id)
        except Exception:
            messagebox.showerror("Open", f"Invalid document id: {doc_id}")
            return

        if self.current_doc_id is not None:
            self.history.append(self.current_doc_id)

        doc = None
        if self.doc_store and hasattr(self.doc_store, "get_document"):
            try:
                doc = self.doc_store.get_document(doc_id)
            except Exception as e:
                print("get_document failed:", e)
        if not doc:
            messagebox.showerror("Open", f"Document {doc_id} not found.")
            return

        self.current_doc_id = doc_id
        self._render_document(doc)

    # ---------- Render ----------
    def _looks_like_opml(self, text: str) -> bool:
        t = text.strip()
        if "<opml" in t[:200].lower():
            return True
        if t.startswith("<?xml") and "<opml" in t.lower():
            return True
        return False

    def _render_opml_outline(self, xml_text: str):
        """Render OPML as an expandable outline using a Treeview."""
        try:
            s = xml_text.lstrip("\ufeff\r\n\t ")
            root = ET.fromstring(s)
        except Exception as e:
            # Fall back to plain text if parsing fails
            self._show_text_mode()
            self.text.delete("1.0", "end")
            self.text.insert("1.0", xml_text)
            self.status.set(f"OPML parse failed: {e}; showing raw XML")
            return

        self._show_tree_mode()
        self.opml_tree.delete(*self.opml_tree.get_children())

        body = root.find(".//body")
        outlines = body.findall("outline") if body is not None else []

        def node_label(elem: ET.Element) -> str:
            for attr in ("text", "title"):
                if elem.get(attr):
                    return elem.get(attr)  # type: ignore
            for attr in ("url", "htmlUrl", "xmlUrl"):
                if elem.get(attr):
                    return elem.get(attr)  # type: ignore
            return "(item)"

        def add_outline(e: ET.Element, parent=""):
            this_id = self.opml_tree.insert(parent, "end", text=node_label(e))
            for child in e.findall("outline"):
                add_outline(child, this_id)

        for top in outlines:
            add_outline(top, "")

        for child in self.opml_tree.get_children(""):
            self.opml_tree.item(child, open=True)

    def _set_img_label(self, pil_img: Image.Image):
        # Size to fit window-ish
        w = max(100, self.winfo_width() - 40)
        h = max(100, self.winfo_height() - 180)  # leave room for text/status
        img = pil_img.copy()
        img.thumbnail((w, h))
        self._last_pil_img = pil_img
        self._last_tk_img = ImageTk.PhotoImage(img)
        self.img_label.configure(image=self._last_tk_img)

    def _hide_image(self):
        self.img_label.configure(image="")
        self._last_pil_img = None
        self._last_tk_img = None
        if self._image_zoom_win and self._image_zoom_win.winfo_exists():
            try:
                self._image_zoom_win.destroy()
            except Exception:
                pass
        self._image_zoom_win = None

    def _toggle_image_zoom(self):
        if not self._last_pil_img:
            return
        if self._image_zoom_win and self._image_zoom_win.winfo_exists():
            self._image_zoom_win.destroy()
            self._image_zoom_win = None
            return
        win = tk.Toplevel(self)
        win.title("Image Preview")
        sw, sh = self.winfo_screenwidth(), self.winfo_screenheight()
        iw, ih = self._last_pil_img.size
        win.geometry(f"{min(iw, sw)}x{min(ih, sh)}")
        canvas = tk.Canvas(win, scrollregion=(0, 0, iw, ih))
        hbar = ttk.Scrollbar(win, orient="horizontal", command=canvas.xview)
        vbar = ttk.Scrollbar(win, orient="vertical", command=canvas.yview)
        canvas.configure(xscrollcommand=hbar.set, yscrollcommand=vbar.set)
        canvas.grid(row=0, column=0, sticky="nsew")
        hbar.grid(row=1, column=0, sticky="we")
        vbar.grid(row=0, column=1, sticky="ns")
        win.grid_rowconfigure(0, weight=1)
        win.grid_columnconfigure(0, weight=1)
        tk_img = ImageTk.PhotoImage(self._last_pil_img)
        canvas.create_image(0, 0, anchor="nw", image=tk_img)
        canvas.image = tk_img
        self._image_zoom_win = win

    def _render_document(self, doc):
        """Render text / OPML / image from text(base64) or bytes."""
        title, content = _extract_title_content(doc)
        self._current_content = content

        # OPML?
        if isinstance(content, str) and self._looks_like_opml(content):
            self._render_opml_outline(content)
            self.status.set(f"Viewing OPML: {title} (id={self.current_doc_id})")
            return

        # Text mode
        self._show_text_mode()
        self.text.delete("1.0", "end")
        self._hide_image()

        # Try Base64 (string)
        if PIL_AVAILABLE and isinstance(content, str) and _looks_like_b64_text(content):
            decoded = _decode_b64_text(content)
            if decoded:
                try:
                    pil = Image.open(BytesIO(decoded))
                    self._set_img_label(pil)
                    self.status.set(
                        f"Viewing image (decoded from Base64 text): id={self.current_doc_id}, {_human_size(len(decoded))}"
                    )
                    return
                except Exception as e:
                    print("Base64 text image render failed:", e)

        # Try bytes that are Base64 text
        if (
            PIL_AVAILABLE
            and isinstance(content, (bytes, bytearray))
            and _looks_like_b64_bytes(content)
        ):
            decoded = _decode_b64_bytes(content)
            if decoded:
                try:
                    pil = Image.open(BytesIO(decoded))
                    self._set_img_label(pil)
                    self.status.set(
                        f"Viewing image (decoded from Base64 bytes): id={self.current_doc_id}, {_human_size(len(decoded))}"
                    )
                    return
                except Exception as e:
                    print("Base64 bytes image render failed:", e)

        # Try raw image bytes
        if PIL_AVAILABLE and isinstance(content, (bytes, bytearray)):
            try:
                pil = Image.open(BytesIO(content))
                self._set_img_label(pil)
                self.status.set(
                    f"Viewing image (BLOB): id={self.current_doc_id}, {_human_size(len(content))}"
                )
                return
            except Exception as e:
                print("BLOB image render failed:", e)

        # Fallback: textual content
        display = (
            content
            if isinstance(content, str)
            else (
                render_binary_as_text(content)
                if render_binary_as_text and isinstance(content, (bytes, bytearray))
                else str(content)
            )
        )
        self.text.insert("1.0", display)

        # Parse links if available and content is textual
        if parse_links and isinstance(display, str):
            try:
                parse_links(self.text, display, self._open_doc_id)
            except Exception as e:
                print("parse_links failed:", e)

        self.status.set(f"Viewing: {title} (id={self.current_doc_id})")

    def _render_binary_preview(self, payload):
        if render_binary_preview:
            try:
                render_binary_preview(self.text, payload)
                return
            except Exception as e:
                print("render_binary_preview failed:", e)
        if render_binary_as_text:
            try:
                display = render_binary_as_text(self.text, payload)
                self.text.insert("1.0", display)
            except Exception as e:
                print("render_binary_as_text failed:", e)

    # ---------- Commands ----------

    def _on_ask(self):
        sel = self._get_selected_text()
        if not sel.strip():
            messagebox.showinfo("ASK", "Please select some text in the document first.")
            return

        # Check for processor
        if not self.processor or not hasattr(self.processor, "query_ai"):
            messagebox.showerror("ASK", "CommandProcessor.query_ai is unavailable.")
            return

        current_id = self.current_doc_id

        # Ask user for prefix
        prefix = simpledialog.askstring(
            "ASK prefix",
            "Enter prefix (optional):",
            initialvalue="Please expand on this: ",
        )
        if prefix is None:
            return

        # ----------------------------------------------------
        # Success callback
        # ----------------------------------------------------
        def _on_success(new_id):
            try:
                messagebox.showinfo("ASK", f"Created new document {new_id}")
            finally:
                self._refresh_index()

        # ----------------------------------------------------
        # Link creation callback (canonical PiKit green-link path)
        # ----------------------------------------------------
        def _on_link_created(new_id):
            print("DEBUG: on_link_created called with new_id =", new_id)
            try:
                if current_id is not None and self.doc_store:
                    doc = self.doc_store.get_document(current_id)
                    if doc:
                        # Re-render so the newly updated body (with green link)
                        # becomes visible immediately.
                        self._render_document(doc)
            except Exception as e:
                print("on_link_created error:", e)

        # ----------------------------------------------------
        # Main AI call (new-style, with prefix + callbacks)
        # ----------------------------------------------------
        try:
            self.processor.query_ai(
                selected_text=sel,
                current_doc_id=current_id,
                on_success=_on_success,
                on_link_created=_on_link_created,
                prefix=prefix,
            )
        except TypeError:
            # Legacy 4-arg signature
            try:
                self.processor.query_ai(sel, current_id, _on_success, _on_link_created)
            except Exception as e:
                messagebox.showerror("ASK", f"query_ai failed: {e}")
        except Exception as e:
            messagebox.showerror("ASK", f"query_ai error: {e}")

    def _go_back(self):
        if not self.history:
            messagebox.showinfo("Back", "No previous document.")
            return
        prev = self.history.pop()
        self._open_doc_id(prev)

    def _open_by_id(self):
        s = simpledialog.askstring("Open", "Document ID:")
        if not s:
            return
        self._open_doc_id(s)

    def _import_directory(self):
        from pathlib import Path
        # Try preferred module-based importer first
        import_fn = None
        try:
            from modules import directory_import
            import_fn = getattr(directory_import, "import_text_files_from_directory", None)
        except Exception:
            import_fn = None

        path = filedialog.askdirectory(title="Choose a directory to import")
        if not path:
            return

        if callable(import_fn):
            try:
                imported, skipped = import_fn(Path(path), self.doc_store, skip_existing=True)
                messagebox.showinfo(
                    "Directory Import",
                    f"Imported {imported} file(s), skipped {skipped} existing."
                )
                self._refresh_index()
                return
            except Exception as e:
                messagebox.showerror("Directory Import", f"Import failed: {e}")
                return

        # Fallback: try common CommandProcessor methods if the module isn't available
        for name in ("import_directory", "import_dir", "import_from_directory"):
            fn = getattr(self.processor, name, None)
            if callable(fn):
                try:
                    try:
                        added = fn(path)
                    except TypeError:
                        added = fn(directory=path)
                    messagebox.showinfo("Directory Import", f"Imported {added}")
                    self._refresh_index()
                    return
                except Exception as e:
                    messagebox.showerror("Directory Import", f"Import failed: {e}")
                    return

        messagebox.showerror(
            "Directory Import",
            "No usable entrypoint found. Expected modules.directory_import.import_text_files_from_directory(...) "
            "or a CommandProcessor import method."
        )

    def _open_opml_from_file(self):
        # Prefer plugin flow when available
        if opml_plugin and hasattr(opml_plugin, "open_opml_file_dialog"):
            try:
                new_id = opml_plugin.open_opml_file_dialog(self)
                if new_id:
                    self._open_doc_id(new_id)
                return
            except Exception as e:
                messagebox.showerror("OPML", f"Open OPML failed: {e}")
                return

        # Fallback: let user pick a file and call into processor with any of the common names
        filepath = filedialog.askopenfilename(
            title="Open OPML file",
            filetypes=[("OPML files", "*.opml *.xml"), ("All files", "*.*")],
        )
        if not filepath:
            return

        if not self.processor:
            messagebox.showerror("OPML", "OPML feature unavailable (no processor).")
            return

        # Try common import function names
        func = None
        for name in ("import_opml_from_path", "import_opml", "import_opml_file"):
            func = getattr(self.processor, name, None)
            if callable(func):
                break

        if not func:
            messagebox.showerror(
                "OPML", "No OPML import function found in CommandProcessor."
            )
            return

        try:
            new_id = func(filepath)
        except Exception as e:
            messagebox.showerror("OPML", f"OPML import failed: {e}")
            return
        if new_id:
            self._open_doc_id(new_id)

    def _convert_selection_to_opml(self):
        if self._mode != "text":
            messagebox.showinfo(
                "Convert → OPML",
                "Switch to a text document and select text to convert.",
            )
            return

        sel = self._get_selected_text()
        if not sel.strip():
            messagebox.showinfo("Convert → OPML", "Select some text first.")
            return
        # Prefer plugin conversion if present
        xml_text = None
        if opml_plugin:
            conv = getattr(opml_plugin, "convert_text_to_opml_inplace", None)
            if callable(conv):
                try:
                    xml_text = conv(sel)
                except Exception as e:
                    messagebox.showerror("Convert → OPML", f"Conversion failed: {e}")
                    return
        if xml_text is None:
            xml_text = self._basic_text_to_opml(sel)

        win = tk.Toplevel(self)
        win.title("OPML Preview")
        txt = tk.Text(win, wrap="word")
        txt.pack(fill="both", expand=True)
        txt.insert("1.0", xml_text)

        def _save():
            out = filedialog.asksaveasfilename(
                title="Save OPML",
                defaultextension=".opml",
                filetypes=[
                    ("OPML files", "*.opml"),
                    ("XML files", "*.xml"),
                    ("All files", "*.*"),
                ],
            )
            if not out:
                return
            Path(out).write_text(xml_text, encoding="utf-8")
            messagebox.showinfo("OPML", f"Saved to {out}")

        ttk.Button(win, text="Save…", command=_save).pack(pady=6)

    def _reparse_links(self):
        """Re-run link parsing on the current Text widget content (text mode only)."""
        if self._mode != "text":
            messagebox.showinfo(
                "Reparse Links", "Not applicable for OPML outline view."
            )
            return
        if not parse_links:
            messagebox.showinfo("Reparse Links", "No link parser available.")
            return
        try:
            current_text = self.text.get("1.0", "end-1c")
            self._current_content = current_text
            parse_links(self.text, current_text, self._open_doc_id)
            self.status.set("Links reparsed.")
        except Exception as e:
            messagebox.showerror("Reparse Links", f"Failed: {e}")

    def _on_search_clicked(self):
        q = simpledialog.askstring("Search", "Enter query (matches title/content):")
        if not q:
            return
        ql = q.lower()

        rows = []
        if self.doc_store and hasattr(self.doc_store, "get_document_index"):
            try:
                rows = self.doc_store.get_document_index() or []
            except Exception as e:
                print("get_document_index failed:", e)

        try:
            self.sidebar.delete(*self.sidebar.get_children())
        except Exception:
            pass

        for row in rows:
            if isinstance(row, sqlite3.Row):
                m = dict(row)
                doc_id = m.get("id", m.get("doc_id", m.get("pk", None)))
                title = str(m.get("title", m.get("name", "")) or "")
                content = (
                    m.get("content")
                    or m.get("body")
                    or m.get("text")
                    or m.get("raw")
                    or m.get("data")
                    or m.get("value")
                    or m.get("description")
                    or ""
                )
            elif isinstance(row, dict):
                doc_id = row.get("id") or row.get("doc_id") or row.get("pk")
                title = str(row.get("title", row.get("name", "")) or "")
                content = (
                    row.get("content")
                    or row.get("body")
                    or row.get("text")
                    or row.get("raw")
                    or row.get("data")
                    or row.get("value")
                    or row.get("description")
                    or ""
                )
            else:
                doc_id = (
                    row[0] if isinstance(row, (list, tuple)) and len(row) > 0 else None
                )
                title = (
                    row[1]
                    if isinstance(row, (list, tuple))
                    and len(row) > 1
                    and isinstance(row[1], str)
                    else ""
                )
                content = (
                    row[2] if isinstance(row, (list, tuple)) and len(row) > 2 else ""
                )

            hay = (_make_preview(title, content) + "\n" + str(content)).lower()
            if ql in hay:
                size = self._approx_payload_size(content)
                self.sidebar.insert(
                    "",
                    "end",
                    values=(doc_id, _make_preview(title, content), _human_size(size)),
                )

    def _on_ecm(self):
        """Open ECM controls if available, otherwise fall back to a read-only view."""
        if open_ecm_settings_dialog:
            open_ecm_settings_dialog(self)
            return
        if not self.processor or not hasattr(self.processor, "ecm_bridge"):
            messagebox.showinfo("ECM", "ECM Bridge not available in processor.")
            return

        import json
        info = {
            "preamp": self.processor.ecm_bridge.get_debug_info(),
            "ecm2": self.processor.get_ecm_snapshot()
            if hasattr(self.processor, "get_ecm_snapshot")
            else {},
        }
        msg = json.dumps(info, indent=2)

        win = tk.Toplevel(self)
        win.title("ECM Status")
        txt = tk.Text(win, wrap="none", font=("Courier", 10))
        txt.pack(fill="both", expand=True)
        txt.insert("1.0", msg)
        txt.config(state="disabled")

    def _save_visible_text(self):
        if self._mode != "text":
            messagebox.showinfo("Save Visible Text", "Switch to a text document first.")
            return
        visible = self.text.get("1.0", "end-1c")
        if not visible.strip():
            messagebox.showinfo("Save Visible Text", "No text to save.")
            return
        out = filedialog.asksaveasfilename(
            title="Save Visible Text",
            defaultextension=".txt",
            filetypes=[("Text", "*.txt"), ("All files", "*.*")],
        )
        if not out:
            return
        Path(out).write_text(visible, encoding="utf-8")
        messagebox.showinfo("Saved", f"Saved to {out}")

    def _import_text_file(self):
        path = filedialog.askopenfilename(
            title="Import", filetypes=[("Text", "*.txt"), ("All", "*.*")]
        )
        if not path:
            return
        body = Path(path).read_text(encoding="utf-8", errors="replace")
        title = Path(path).stem
        nid = self.doc_store.add_document(title, body)
        self._refresh_index()
        doc = self.doc_store.get_document(nid)
        if doc:
            self._render_document(doc)

    def _export_current(self):
        if self.current_doc_id is None:
            messagebox.showwarning("Export", "No document loaded.")
            return
        doc = self.doc_store.get_document(self.current_doc_id)
        if not doc:
            messagebox.showerror("Export", "Not found.")
            return
        title, content = _extract_title_content(doc)

        # Choose extension
        if isinstance(content, (bytes, bytearray)) or _looks_like_b64_text(
            content if isinstance(content, str) else ""
        ):
            default_ext = ".png"
            types = [("PNG image", "*.png"), ("All files", "*.*")]
        elif isinstance(content, str) and self._looks_like_opml(content):
            default_ext = ".opml"
            types = [("OPML", "*.opml"), ("XML", "*.xml"), ("All files", "*.*")]
        else:
            default_ext = ".txt"
            types = [("Text", "*.txt"), ("All files", "*.*")]

        default_name = f"document_{self.current_doc_id}{default_ext}"
        out = filedialog.asksaveasfilename(
            title="Export Current",
            defaultextension=default_ext,
            initialfile=default_name,
            filetypes=types,
        )
        if not out:
            return

        try:
            if isinstance(content, (bytes, bytearray)):
                Path(out).write_bytes(content)
            elif isinstance(content, str) and _looks_like_b64_text(content):
                b = _decode_b64_text(content)
                if b:
                    Path(out).write_bytes(b)
                else:
                    Path(out).write_text(content, encoding="utf-8")
            else:
                Path(out).write_text(str(content), encoding="utf-8")
            messagebox.showinfo("Export", f"Saved to:\n{out}")
        except Exception as e:
            messagebox.showerror("Export", f"Failed to save: {e}")

    def _export_and_launch_flask(self):
        export_path = Path("exported_docs")
        export_path.mkdir(exist_ok=True)

        # export simple JSON docs (best-effort)
        try:
            import json

            if self.doc_store and hasattr(self.doc_store, "get_document_index"):
                for row in self.doc_store.get_document_index() or []:
                    doc_id = (
                        row.get("id")
                        if isinstance(row, dict)
                        else (row[0] if isinstance(row, (list, tuple)) else None)
                    )
                    if doc_id is None:
                        continue
                    doc = self.doc_store.get_document(doc_id)
                    if isinstance(doc, sqlite3.Row):
                        data = dict(doc)
                    elif isinstance(doc, dict):
                        data = dict(doc)
                    elif isinstance(doc, (list, tuple)):
                        data = {
                            "id": doc[0] if len(doc) > 0 else None,
                            "title": doc[1] if len(doc) > 1 else "",
                            "body": doc[2] if len(doc) > 2 else "",
                        }
                    else:
                        data = {"id": doc_id, "title": "", "body": str(doc)}
                    with open(
                        export_path / f"{data.get('id')}.json", "w", encoding="utf-8"
                    ) as f:
                        json.dump(data, f, indent=2)
        except Exception as e:
            print("Export JSON failed:", e)

        # Launch Flask if present
        try:
            import subprocess, sys

            if flask_server_path.exists():
                subprocess.Popen([sys.executable, str(flask_server_path)])
                messagebox.showinfo(
                    "Server Started", "Flask server launched at http://127.0.0.1:5050"
                )
            else:
                messagebox.showwarning("Flask", "modules/flask_server.py not found.")
        except Exception as e:
            messagebox.showerror("Flask", f"Failed to launch: {e}")

    @staticmethod
    def _basic_text_to_opml(text: str) -> str:
        import html

        body = "\n".join(
            f'<outline text="{html.escape(line)}" />'
            for line in text.splitlines()
            if line.strip()
        )
        return (
            '<?xml version="1.0" encoding="UTF-8"?>\n'
            '<opml version="2.0">\n'
            "  <head><title>Converted</title></head>\n"
            "  <body>\n"
            f"{body}\n"
            "  </body>\n"
            "</opml>\n"
        )


def main():
    app = App()
    app.mainloop()


if __name__ == "__main__":
    main()

# --- Compatibility alias for old imports ---
DemoKitGUI = App
