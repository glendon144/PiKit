import re
import tkinter as tk

LINK_PATTERN = re.compile(r"\[([^\]]+)]\(doc:(\d+)\)")


def parse_links(text_widget: tk.Text, raw_text: str, on_open_doc):
    """Scan *raw_text* for markdown links like `[label](doc:123)`.

    When found, add a `link` tag to the matching range in *text_widget* and bind
    a click to `on_open_doc(doc_id)`.
    """
    # Wipe old link tags
    text_widget.tag_delete("link")
    text_widget.tag_configure("link", foreground="green", underline=True)

    # The Text widget already contains *raw_text*; walk through matches
    for match in LINK_PATTERN.finditer(raw_text):
        label, doc_id = match.groups()
        start_idx = f"1.0+{match.start()}c"
        end_idx = f"1.0+{match.end()}c"

        # Tag this span so it appears as a clickable link
        text_widget.tag_add("link", start_idx, end_idx)

        # Need a closure to capture doc_id for each match
        def _make_callback(did):
            return lambda _evt, _did=did: on_open_doc(int(_did))

        text_widget.tag_bind("link", "<Button-1>", _make_callback(doc_id))
