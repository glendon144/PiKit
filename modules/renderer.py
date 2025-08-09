"""
renderer.py — Extended renderer utilities for PyKit

This version adds HyperScope-inspired features:
- High-resolution anchors with helper lookups (find_by_nid)
- Viewspeclike parsing and application (outline depth, firstline, show_attrs)
- Optional per-node deep links using a PiKit URI scheme (pikit://doc/<id>#<nid>?...)
- Basic backlink extraction from <a href> tags found in outline node text

Existing features retained:
- render_binary_as_text(file_path, min_length=4) -> str
- render_image_preview_from_base64(base64_data, max_size=(400,400)) -> ImageTk.PhotoImage | None
- render_opml_outline(file_path, show_attrs=False, max_depth=None) -> str (now extended)
- html_string_to_opml(html_text, source_url=None, title=None) -> str
- html_file_to_opml_file(html_path, out_opml_path, source_url=None, title=None) -> str
"""
from __future__ import annotations

from html.parser import HTMLParser
from html import escape
import subprocess
import base64
from io import BytesIO
try:
    from PIL import Image, ImageTk  # optional at runtime
except Exception:
    Image = None
    ImageTk = None
import os
import re
import uuid
import datetime
import xml.etree.ElementTree as ET
from typing import Dict, List, Optional, Tuple

HS_NS = "http://www.hyperscope.org/hyperscope/opml/public/2006/05/09"
ET.register_namespace("hs", HS_NS)

# --------------------
# Existing functions
# --------------------
def render_binary_as_text(file_path: str, min_length: int = 4) -> str:
    """Extract printable ASCII strings from a binary file using the Unix `strings` command."""
    try:
        result = subprocess.run(
            ["strings", "-n", str(min_length), file_path],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=True,
            text=True,
        )
        return result.stdout
    except Exception as e:
        return f"[Error extracting strings: {e}]"

def render_image_preview_from_base64(base64_data: str, max_size=(400, 400)):
    """Decode a base64 image and return a resized PIL ImageTk.PhotoImage (if Pillow is available)."""
    if Image is None or ImageTk is None:
        print("[renderer] Pillow not available; cannot render image preview.")
        return None
    try:
        decoded = base64.b64decode(base64_data)
        image = Image.open(BytesIO(decoded))
        image.thumbnail(max_size)
        return ImageTk.PhotoImage(image)
    except Exception as e:
        print(f"[Error rendering image preview: {e}]")
        return None

# --------------------
# Viewspeclike support
# --------------------
Viewspec = Dict[str, object]

_DEF_VIEW: Viewspec = {
    "view": "outline",      # reserved for future view modes
    "depth": None,           # int | None
    "show_attrs": False,     # include hs:* attrs
    "firstline": False,      # show only first line of each node's text
}

_VIEWSPEC_BOOL = {"1": True, "true": True, "yes": True, "on": True, "0": False, "false": False, "no": False, "off": False}


def parse_viewspec(spec: Optional[str]) -> Viewspec:
    """Parse a simple querystring-like viewspec: "view=outline&depth=2&attrs=1&firstline=1".
    Unknown keys are ignored. Returns a dict merged with defaults.
    """
    vs = dict(_DEF_VIEW)
    if not spec:
        return vs
    for part in spec.split("&"):
        if not part:
            continue
        if "=" in part:
            k, v = part.split("=", 1)
        else:
            k, v = part, "1"
        k = k.strip().lower()
        v = v.strip()
        if k in ("depth", "max_depth"):
            try:
                vs["depth"] = int(v)
            except Exception:
                pass
        elif k in ("attrs", "show_attrs"):
            vs["show_attrs"] = _VIEWSPEC_BOOL.get(v.lower(), True)
        elif k in ("firstline", "first_line"):
            vs["firstline"] = _VIEWSPEC_BOOL.get(v.lower(), True)
        elif k == "view":
            vs["view"] = v.lower()
    return vs

# --------------------
# OPML outline preview
# --------------------

def _firstline_of_html(html_text: str) -> str:
    """Heuristic: take text up to first <br> or first sentence period; keep inline tags minimal."""
    # Stop at first <br/?>
    br_pos = html_text.lower().find("<br")
    if br_pos != -1:
        return html_text[:br_pos].strip()
    # Otherwise, take up to first full stop followed by space (avoid abbreviations: naive)
    m = re.search(r"\.(\s|$)", html_text)
    if m:
        return html_text[: m.start()+1].strip()
    # Fallback: truncate long strings
    return html_text[:160].strip()


def _format_outline_element(
    el: ET.Element,
    depth: int = 0,
    show_attrs: bool = False,
    max_depth: Optional[int] = None,
    firstline: bool = False,
    include_links: bool = False,
    doc_id: Optional[int] = None,
) -> str:
    """Recursively pretty-print <outline> elements from an OPML file.
    If include_links and doc_id are set, append a PiKit deep link per node.
    """
    if max_depth is not None and depth > max_depth:
        return ""
    text = (el.get("text", "").strip() or "(no text)")
    if firstline and text:
        text = _firstline_of_html(text)

    nid = el.get(f"{{{HS_NS}}}nid", "")

    # Collect common hs:* attrs
    hs_attrs = []
    for k, v in el.attrib.items():
        if k.startswith("{" + HS_NS + "}"):
            local = k.split("}", 1)[1]
            if local in ("nid", "anchor", "sourceUrl", "opml"):
                hs_attrs.append(f"{local}={v}")

    attr_str = f"  [{' '.join(hs_attrs)}]" if hs_attrs and show_attrs else ""

    # Optional per-node link (let the GUI auto-detect as a clickable URL)
    link_str = ""
    if include_links and doc_id is not None and nid:
        uri = f"pikit://doc/{doc_id}#{nid}"
        link_str = f"  <{uri}>"

    prefix = "  " * depth + "• "
    out_lines = [f"{prefix}{text}{attr_str}{link_str}"]

    for child in el.findall("outline"):
        chunk = _format_outline_element(
            child,
            depth + 1,
            show_attrs,
            max_depth,
            firstline,
            include_links,
            doc_id,
        )
        if chunk:
            out_lines.append(chunk)
    return "\n".join(out_lines)


def render_opml_outline(
    file_path: str,
    show_attrs: bool = False,
    max_depth: Optional[int] = None,
    *,
    viewspec: Optional[str] = None,
    include_links: bool = False,
    doc_id: Optional[int] = None,
) -> str:
    """
    Parse an OPML file and return a human-readable outline preview.
    Now supports:
      - viewspec: querystring-like string (e.g., "depth=2&attrs=1&firstline=1")
      - include_links + doc_id: append PiKit deep links per node
    """
    vs = parse_viewspec(viewspec)
    if vs.get("depth") is not None and max_depth is None:
        max_depth = int(vs["depth"])  # prefer viewspec depth if provided
    show_attrs = bool(vs.get("show_attrs", show_attrs))
    firstline = bool(vs.get("firstline", False))

    try:
        tree = ET.parse(file_path)
        root = tree.getroot()
        body = root.find("body")
        if body is None:
            return "[OPML has no <body>]"
        lines: List[str] = []
        head = root.find("head")
        if head is not None:
            title_el = head.find("title")
            if title_el is not None and title_el.text:
                lines.append(f"# {title_el.text.strip()}")
                lines.append("")
        for outline in body.findall("outline"):
            lines.append(
                _format_outline_element(
                    outline,
                    0,
                    show_attrs,
                    max_depth,
                    firstline,
                    include_links,
                    doc_id,
                )
            )
        return "\n".join(lines) if lines else "[No <outline> elements in OPML body]"
    except Exception as e:
        return f"[Error parsing OPML: {e}]"

# --------------------
# Anchor helpers and backlinks
# --------------------

def find_outline_by_nid(file_path: str, nid: str) -> Optional[ET.Element]:
    """Return the first <outline> element with the given hs:nid, or None."""
    try:
        tree = ET.parse(file_path)
        for el in tree.iterfind(".//outline"):
            if el.get(f"{{{HS_NS}}}nid") == nid:
                return el
        return None
    except Exception:
        return None


def get_outline_path(file_path: str, nid: str) -> Optional[List[int]]:
    """Return the index path from OPML <body> to the node with hs:nid as a list like [2,0,5]."""
    try:
        tree = ET.parse(file_path)
        root = tree.getroot()
        body = root.find("body")
        if body is None:
            return None

        target: Optional[List[int]] = None

        def dfs(node: ET.Element, nid_val: str, path: List[int]) -> bool:
            nonlocal target
            for idx, child in enumerate(list(node)):
                if child.tag != "outline":
                    continue
                if child.get(f"{{{HS_NS}}}nid") == nid_val:
                    target = path + [idx]
                    return True
                if dfs(child, nid_val, path + [idx]):
                    return True
            return False

        dfs(body, nid, [])
        return target
    except Exception:
        return None


def generate_deep_link(doc_id: int, nid: str, viewspec: Optional[str] = None) -> str:
    """Create a PiKit deep link URI for GUI usage."""
    base = f"pikit://doc/{doc_id}#{nid}"
    if viewspec:
        return f"{base}?{viewspec}"
    return base


def extract_backlinks_from_opml(file_path: str) -> List[Tuple[str, Optional[str]]]:
    """Scan outline node text for <a href="..."> and return [(href, nid_of_source)]."""
    href_re = re.compile(r"<a\s+[^>]*href=\"([^\"]+)\"", re.IGNORECASE)
    out: List[Tuple[str, Optional[str]]] = []
    try:
        tree = ET.parse(file_path)
        for el in tree.iterfind(".//outline"):
            text = el.get("text", "")
            if not text:
                continue
            for href in href_re.findall(text):
                out.append((href, el.get(f"{{{HS_NS}}}nid")))
        return out
    except Exception:
        return []

# --------------------
# Minimal HTML → OPML (stdlib-only, experimental)
# --------------------
class _SimpleHTMLToOutline(HTMLParser):
    """
    VERY BASIC structural extractor:
      - H1..H6 as levels 1..6
      - <p> blocks at current level (or 1 if none)
      - <ul>/<ol>/<li> nesting increases level for items
    Keeps inline tags: em/strong/code/a/br (others stripped).
    """
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.blocks: List[Tuple[int, str]] = []  # (level, html_text)
        self._buf: List[str] = []               # text buffer for current block
        self._current_level: Optional[int] = None
        self._list_depth = 0                    # ul/ol depth

    def _flush(self, level: Optional[int] = None):
        if not self._buf:
            return
        html_text = "".join(self._buf).strip()
        if html_text:
            lvl = level if level is not None else (self._current_level or 1)
            self.blocks.append((lvl, html_text))
        self._buf = []

    def handle_starttag(self, tag, attrs):
        tag = tag.lower()
        if tag in [f"h{i}" for i in range(1,7)]:
            self._flush()
            self._current_level = int(tag[1])
        elif tag == "p":
            self._flush()
        elif tag in ("ul", "ol"):
            self._list_depth += 1
        elif tag == "li":
            self._flush((self._current_level or 1) + self._list_depth)
            self._buf.append("• ")
        elif tag in ("em","strong","code","a","br"):
            if tag == "a":
                href = ""
                for k,v in attrs:
                    if k.lower() == "href":
                        href = v
                        break
                self._buf.append(f'<a href="{escape(href, quote=True)}">')
            elif tag == "br":
                self._buf.append("<br/>")
            else:
                self._buf.append(f"<{tag}>")

    def handle_endtag(self, tag):
        tag = tag.lower()
        if tag in [f"h{i}" for i in range(1,7)]:
            self._flush(self._current_level or 1)
        elif tag == "p":
            self._flush(self._current_level or 1)
        elif tag in ("ul", "ol"):
            self._list_depth = max(0, self._list_depth - 1)
        elif tag == "li":
            self._flush((self._current_level or 1) + self._list_depth)
        elif tag in ("em","strong","code","a"):
            self._buf.append(f"</{tag}>")

    def handle_data(self, data):
        if data:
            self._buf.append(escape(data))


def _uuid5_for(url: str, salt: str) -> str:
    ns = uuid.uuid5(uuid.NAMESPACE_URL, url or "about:blank")
    return str(uuid.uuid5(ns, salt or ""))


def html_string_to_opml(html_text: str, source_url: str | None = None, title: str | None = None) -> str:
    """Convert HTML (string) into a simple OPML 2.0 string with hs:* metadata. Stdlib-only."""
    parser = _SimpleHTMLToOutline()
    parser.feed(html_text or "")
    blocks = parser.blocks

    opml = ET.Element("opml", {"version": "2.0"})
    head = ET.SubElement(opml, "head")
    ET.SubElement(head, "title").text = title or (source_url or "HTML Import")
    if source_url:
        ET.SubElement(head, f"{{{HS_NS}}}sourceUrl").text = source_url
    ET.SubElement(head, "dateCreated").text = datetime.date.today().isoformat()

    body = ET.SubElement(opml, "body")

    # Simple hierarchical placement based on heading/list levels
    stack: List[Tuple[int, ET.Element]] = []  # list[(level, ET.Element)]
    for level, html_snippet in blocks:
        outline_el = ET.Element("outline")
        outline_el.set("text", html_snippet)
        nid = _uuid5_for(source_url or "about:blank", html_snippet[:64])
        outline_el.set(f"{{{HS_NS}}}nid", nid)

        while stack and stack[-1][0] >= level:
            stack.pop()
        if not stack:
            body.append(outline_el)
        else:
            stack[-1][1].append(outline_el)
        stack.append((level, outline_el))

    # Serialize with xml declaration + stylesheet PI
    xml_bytes = ET.tostring(opml, encoding="utf-8")
    xml = xml_bytes.decode("utf-8")
    pi = "<?xml-stylesheet type='text/xsl' href='hyperscope.xsl'?>\n"
    if not xml.startswith("<?xml"):
        xml = "<?xml version='1.0' encoding='UTF-8'?>\n" + pi + xml
    else:
        parts = xml.split("\n", 1)
        xml = parts[0] + "\n" + pi + (parts[1] if len(parts) > 1 else "")
    return xml


def html_file_to_opml_file(html_path: str, out_opml_path: str, source_url: str | None = None, title: str | None = None) -> str:
    """Read an HTML file, write an OPML file, return the output path."""
    with open(html_path, "r", encoding="utf-8", errors="ignore") as f:
        html_text = f.read()
    opml_text = html_string_to_opml(html_text, source_url=source_url, title=title)
    os.makedirs(os.path.dirname(out_opml_path) or ".", exist_ok=True)
    with open(out_opml_path, "w", encoding="utf-8") as f:
        f.write(opml_text)
    return out_opml_path
