import re
import tkinter as tk

# Match markdown-style links: [label](doc:123)
LINK_PATTERN = re.compile(r"\[([^\]]+)]\(doc:(\d+)\)")


def parse_links(text_widget: tk.Text, raw_text: str, on_open_doc):
    """
    Convert occurrences of [label](doc:123) into individually clickable green links.
    The markdown syntax [ ](doc:123) is stripped so only the label is visible.
    """

    # Remove OLD link tags
    for tag in text_widget.tag_names():
        if tag.startswith("link_"):
            text_widget.tag_delete(tag)

    # We iterate in REVERSE so that replacing text at the end of the widget
    # doesn't invalidate the indices of the matches found at the beginning.
    matches = list(LINK_PATTERN.finditer(raw_text))
    for match in reversed(matches):
        label, doc_id = match.groups()
        start_idx = f"1.0+{match.start()}c"
        end_idx   = f"1.0+{match.end()}c"

        # 1. Delete the full [label](doc:123) string
        text_widget.delete(start_idx, end_idx)

        # 2. Insert ONLY the label
        text_widget.insert(start_idx, label)

        # 3. Calculate new end index for the label only
        new_end_idx = f"{start_idx}+{len(label)}c"

        # 4. Apply unique tag to the label
        tag_name = f"link_{doc_id}_{match.start()}"  # unique per occurrence
        text_widget.tag_add(tag_name, start_idx, new_end_idx)

        # Formatting
        text_widget.tag_configure(
            tag_name,
            foreground="green",
            underline=True,
        )

        # Bind callback
        def _make_cb(did):
            return lambda evt: on_open_doc(int(did))

        text_widget.tag_bind(tag_name, "<Button-1>", _make_cb(doc_id))
        # Cursor change
        text_widget.tag_bind(tag_name, "<Enter>", lambda e: text_widget.config(cursor="hand2"))
        text_widget.tag_bind(tag_name, "<Leave>", lambda e: text_widget.config(cursor=""))

