"""
hypertext_parser.py — PiKit URI + green-link parsing utilities for the GUI

Responsibilities (keep renderer.py pure):
- Build/parse PiKit deep-link URIs: pikit://doc/<doc_id>#<nid>?<viewspec>
- Viewspec helpers (round-trip): normalize/parse/encode
- Detect links in rendered text for Text widget tagging (http(s), file, pikit URIs, green links)
- Extract hs:nid from rendered lines (to support Copy Deep Link, Jump/Hoist)

Usage in GUI:
    from hypertext_parser import (
        is_pikit_uri, build_pikit_uri, parse_pikit_uri,
        normalize_viewspec, viewspec_to_dict, dict_to_viewspec,
        find_links_for_textwidget, iter_greenlinks,
        extract_nid_from_rendered_line,
    )

    spans = find_links_for_textwidget(rendered_text)
    # apply spans as clickable tags in Text widget

Notes:
- This file intentionally has no Tk imports; GUI binds clicks externally.
- Depends lightly on renderer.parse_viewspec for consistent viewspec semantics.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional, Tuple, Dict
import re
import urllib.parse as _url

try:
    # Keep an optional import; if unavailable, callers can fallback.
    from renderer import parse_viewspec  # type: ignore
except Exception:  # pragma: no cover
    def parse_viewspec(spec: Optional[str]) -> Dict[str, object]:  # fallback noop
        return {}

# --------------------
# PiKit URI helpers
# --------------------
_PIKIT_SCHEME = "pikit"
_PIKIT_RE = re.compile(r"^pikit://doc/(\d+)(?:#([A-Za-z0-9\-]{8,}))?(?:\?(.*))?$")


def is_pikit_uri(s: str) -> bool:
    return bool(_PIKIT_RE.match(s.strip()))


def build_pikit_uri(doc_id: int, nid: str, viewspec: Optional[str] = None) -> str:
    base = f"{_PIKIT_SCHEME}://doc/{int(doc_id)}#{nid}"
    return f"{base}?{viewspec}" if viewspec else base


def parse_pikit_uri(uri: str) -> Tuple[int, Optional[str], Optional[str]]:
    """Return (doc_id, nid, viewspec). NID or viewspec may be None."""
    m = _PIKIT_RE.match(uri.strip())
    if not m:
        raise ValueError(f"Not a PiKit URI: {uri}")
    doc_id = int(m.group(1))
    nid = m.group(2) or None
    vs = m.group(3) or None
    return doc_id, nid, vs

# --------------------
# Viewspec round-trip
# --------------------
_BOOL_TRUE = {"1", "true", "yes", "on"}
_BOOL_FALSE = {"0", "false", "no", "off"}


def normalize_viewspec(spec: Optional[str]) -> Optional[str]:
    """Normalize a querystring-like viewspec: order keys, strip empties."""
    if not spec:
        return None
    q = _url.parse_qs(spec, keep_blank_values=False)
    # canonical order of known keys
    order = ["view", "depth", "show_attrs", "attrs", "firstline"]
    items = []
    for k in order:
        if k in q:
            for v in q[k]:
                items.append((k, v))
    # include any unknown keys sorted
    for k in sorted(k for k in q.keys() if k not in set(order)):
        for v in q[k]:
            items.append((k, v))
    return _url.urlencode(items)


def viewspec_to_dict(spec: Optional[str]) -> Dict[str, object]:
    if not spec:
        return {}
    return parse_viewspec(spec)


def dict_to_viewspec(d: Dict[str, object]) -> str:
    parts: List[Tuple[str, str]] = []
    for k, v in d.items():
        if isinstance(v, bool):
            parts.append((k, "1" if v else "0"))
        else:
            parts.append((k, str(v)))
    return _url.urlencode(parts)

# --------------------
# Link detection for Text widget
# --------------------
@dataclass(frozen=True)
class LinkSpan:
    start: str   # Tk Text index: "line.char"
    end: str
    target: str  # the URI to open

# URL patterns
_HTTP_RE = re.compile(r"\bhttps?://[\w\-._~:/?#\[\]@!$&'()*+,;=%]+", re.IGNORECASE)
_FILE_RE = re.compile(r"\bfile://[\w\-._~:/?#\[\]@!$&'()*+,;=%]+", re.IGNORECASE)
# PiKit URIs are matched with _PIKIT_RE but we also need span discovery in text
_PIKIT_INLINE_RE = re.compile(r"\bpikit://doc/\d+(?:#[A-Za-z0-9\-]{8,})?(?:\?[\w\-._~:/?#@!$&'()*+,;=%]+)?")

# Legacy green-link markup example (tweak if your format differs):
# "selected phrase → [selected phrase → (43)]" or similar.
_GREEN_LINK_RE = re.compile(r"\[[^\]]+\((\d+)\)\]")  # captures doc id inside parentheses


def _iter_matches_with_indices(text: str, regex: re.Pattern) -> List[Tuple[str, int, int]]:
    return [(m.group(0), m.start(), m.end()) for m in regex.finditer(text)]


def _byte_to_text_index(text: str, byte_pos: int) -> Tuple[int, int]:
    """Convert 0-based byte index into (line, col) 1-based for Tk Text indices."""
    # Since text is Python str (unicode), use slicing to count by codepoints.
    s = text[:byte_pos]
    line = s.count("\n") + 1
    # column is chars since last newline
    last_nl = s.rfind("\n")
    col = (len(s) - last_nl - 1) if last_nl != -1 else len(s)
    return line, col


def _span(line: int, col_start: int, col_end: int, target: str) -> LinkSpan:
    return LinkSpan(start=f"{line}.{col_start}", end=f"{line}.{col_end}", target=target)


def find_links_for_textwidget(text: str) -> List[LinkSpan]:
    """Find http(s), file, and pikit URIs and return Tk Text spans for tagging.
    The caller is responsible for inserting the same `text` into the Text widget before applying spans.
    """
    spans: List[LinkSpan] = []
    for regex in (_HTTP_RE, _FILE_RE, _PIKIT_INLINE_RE):
        for match, a, b in _iter_matches_with_indices(text, regex):
            line, col = _byte_to_text_index(text, a)
            spans.append(_span(line, col, col + len(match), match))
    # Green-link to PiKit URI mapping (best-effort): when a green link embeds a doc id, make it clickable to that doc root
    for match, a, b in _iter_matches_with_indices(text, _GREEN_LINK_RE):
        doc_id = _GREEN_LINK_RE.match(match).group(1)  # type: ignore
        uri = build_pikit_uri(int(doc_id), nid="root")
        line, col = _byte_to_text_index(text, a)
        spans.append(_span(line, col, col + len(match), uri))
    return spans

# --------------------
# NID extraction from rendered lines
# --------------------
# Two supported tails from renderer formatting:
#  1) attribute block when show_attrs=True:  " [nid=xxxx ...]"
#  2) appended URI when include_links=True: " <pikit://doc/ID#NID>"
_ATTR_NID_RE = re.compile(r"\[([^\]]*?)\]")
_IN_TAIL_URI_RE = re.compile(r"<\s*pikit://doc/\d+#([A-Za-z0-9\-]{8,})(?:\?[^>]+)?>")
_KEYVAL_RE = re.compile(r"(\w+)=([^\s]+)")


def extract_nid_from_rendered_line(line: str) -> Optional[str]:
    # Try URI tail first (unambiguous)
    m = _IN_TAIL_URI_RE.search(line)
    if m:
        return m.group(1)
    # Then try attribute block
    m = _ATTR_NID_RE.search(line)
    if m:
        attrs = m.group(1)
        for k, v in _KEYVAL_RE.findall(attrs):
            if k.lower() == "nid":
                return v
    return None

# --------------------
# Green-link helpers (round-trip)
# --------------------
# Keep minimal; adapt to your exact format if different.

def to_greenlink_markup(caption: str, uri: str) -> str:
    """Produce a visible green-link style snippet, embedding a doc id if present."""
    try:
        doc_id, nid, vs = parse_pikit_uri(uri)
        suffix = f" → ({doc_id})"
    except Exception:
        suffix = ""
    return f"{caption} → [{caption}{suffix}]"


def iter_greenlinks(text: str) -> List[LinkSpan]:
    spans: List[LinkSpan] = []
    for match, a, b in _iter_matches_with_indices(text, _GREEN_LINK_RE):
        line, col = _byte_to_text_index(text, a)
        doc_id = _GREEN_LINK_RE.match(match).group(1)  # type: ignore
        uri = build_pikit_uri(int(doc_id), nid="root")
        spans.append(_span(line, col, col + len(match), uri))
    return spans


# --------------------
# Back-compat: parse_links() shim for existing GUI
# --------------------
# Your GUI calls: hypertext_parser.parse_links(self.text, body, on_click)
# This function assumes the Text widget already contains exactly `body`.
# It tags link spans and binds clicks to `on_click(url)`.

def parse_links(text_widget, content: str, on_click):
    """
    Apply clickable link tags to the given Tk Text widget for the provided `content`.
    Assumes the widget already contains `content` verbatim.
    Creates unique tags per link so each has its own bound target URL.
    """
    # Create a base style tag (optional underline + hand cursor)
    try:
        text_widget.tag_configure("link_base", underline=1)
    except Exception:
        pass

    spans = find_links_for_textwidget(content)

    # Remove old per-link tags
    for tag in list(text_widget.tag_names()):
        if tag.startswith("link_"):
            try:
                text_widget.tag_delete(tag)
            except Exception:
                pass

    for i, sp in enumerate(spans, start=1):
        tag = f"link_{i}"
        text_widget.tag_add(tag, sp.start, sp.end)
        # Visual + cursor
        try:
            text_widget.tag_configure(tag, foreground=None)  # keep theme color
            text_widget.tag_bind(tag, "<Enter>", lambda e: text_widget.config(cursor="hand2"))
            text_widget.tag_bind(tag, "<Leave>", lambda e: text_widget.config(cursor=""))
        except Exception:
            pass
        # Click binding (capture URL via default arg)
        def _cb(event, url=sp.target):
            try:
                on_click(url)
            except TypeError:
                # Older handlers may expect (widget, url)
                on_click(text_widget, url)
        text_widget.tag_bind(tag, "<Button-1>", _cb)
        # Inherit base style
        try:
            text_widget.tag_raise(tag)
            text_widget.tag_add("link_base", sp.start, sp.end)
        except Exception:
            pass

# --------------------
# Back-compat: parse_links() — enhanced to support green links
# --------------------
def parse_links(text_widget, content: str, on_click):
    """
    Apply clickable link tags to the given Tk Text widget for the provided `content`.

    Supports:
      - http(s):// and file:// URLs  -> handler called with URL string
      - pikit://doc/<id>#<nid>?...   -> handler called with URL string
      - [label](doc:123) green links -> handler called with int(doc_id)
    """
    import re as _re

    # Base style for generic links
    try:
        text_widget.tag_configure("link_base", underline=1)
    except Exception:
        pass

    # Remove old per-link tags
    for tag in list(text_widget.tag_names()):
        if tag.startswith("link_") or tag in ("green_link", "link"):
            try:
                text_widget.tag_delete(tag)
            except Exception:
                pass

    # 1) Tag standard URLs and PiKit URIs
    spans = find_links_for_textwidget(content)
    for i, sp in enumerate(spans, start=1):
        tag = f"link_{i}"
        text_widget.tag_add(tag, sp.start, sp.end)
        try:
            text_widget.tag_configure(tag, foreground=None)
            text_widget.tag_bind(tag, "<Enter>", lambda e: text_widget.config(cursor="hand2"))
            text_widget.tag_bind(tag, "<Leave>", lambda e: text_widget.config(cursor=""))
        except Exception:
            pass

        def _cb(event, url=sp.target):
            try:
                on_click(url)                 # expected by your _on_link_click
            except TypeError:
                on_click(text_widget, url)    # legacy signature fallback
        text_widget.tag_bind(tag, "<Button-1>", _cb)

        try:
            text_widget.tag_raise(tag)
            text_widget.tag_add("link_base", sp.start, sp.end)
        except Exception:
            pass

    # 2) Tag GREEN LINKS: markdown-style `[label](doc:123)`
    LINK_PATTERN = _re.compile(r"\[([^\]]+)\]\(doc:(\d+)\)")
    for m in LINK_PATTERN.finditer(content):
        start_idx = f"1.0+{m.start()}c"
        end_idx   = f"1.0+{m.end()}c"
        text_widget.tag_add("green_link", start_idx, end_idx)
        try:
            text_widget.tag_configure("green_link", foreground="green", underline=True)
            text_widget.tag_bind("green_link", "<Enter>", lambda e: text_widget.config(cursor="hand2"))
            text_widget.tag_bind("green_link", "<Leave>", lambda e: text_widget.config(cursor=""))
        except Exception:
            pass

        doc_id = int(m.group(2))
        def _cb_doc(event, _did=doc_id):
            try:
                on_click(_did)                # your historic on_open_doc(doc_id)
            except TypeError:
                on_click(text_widget, _did)   # legacy signature fallback
        text_widget.tag_bind("green_link", "<Button-1>", _cb_doc)

    return len(spans)

