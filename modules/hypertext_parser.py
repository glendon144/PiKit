import re
import tkinter as tk

# Match markdown-style links: [label](doc:123)
LINK_PATTERN = re.compile(r"\[([^\]]+)]\(doc:(\d+)\)")


def parse_links(text_widget: tk.Text, raw_text: str, on_open_doc):
    """
    Convert occurrences of [label](doc:123) into individually clickable green links.
    Each link receives its own unique tag so callbacks do not collide.
    """

    # Remove OLD link tags (anything beginning with link_)
    for tag in text_widget.tag_names():
        if tag.startswith("link_"):
            text_widget.tag_delete(tag)

    # Scan the raw text buffer for markdown link patterns
    for match in LINK_PATTERN.finditer(raw_text):
        label, doc_id = match.groups()
        start_idx = f"1.0+{match.start()}c"
        end_idx   = f"1.0+{match.end()}c"

        # Use a unique tag for every link: link_17, link_42, etc.
        tag_name = f"link_{doc_id}"

        # Apply tag to this specific span
        text_widget.tag_add(tag_name, start_idx, end_idx)

        # Formatting (green and underlined)
        text_widget.tag_configure(
            tag_name,
            foreground="green",
            underline=True,
        )

        # Bind callback specifically for THIS link
        def _callback(evt, did=doc_id):
            on_open_doc(int(did))

        text_widget.tag_bind(tag_name, "<Button-1>", _callback)

