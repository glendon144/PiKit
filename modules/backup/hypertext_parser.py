import re

def parse_links(text_widget, content, link_callback):
    """
    Parses markdown-style links such as “[label](id:123)” **or** “[label](doc:123)”
    and makes them clickable.

    Parameters
    ----------
    text_widget : tkinter.Text
        The widget where the text will be rendered.
    content : str
        The full document text, which may include markdown-style links.
    link_callback : Callable[[int], None]
        Function to invoke when a link is clicked (receives the doc-ID).
    """
    # Accept both id:123 and doc:123
    link_pattern = re.compile(r'\[([^\]]+)\]\((?:id|doc):(\d+)\)')

    pos = 0
    for match in link_pattern.finditer(content):
        start, end = match.span()
        label, doc_id = match.groups()

        # Plain text before the link
        if start > pos:
            text_widget.insert("end", content[pos:start])

        # Insert link text with a unique tag
        link_start = text_widget.index("end")
        text_widget.insert("end", label)
        link_end = text_widget.index("end")

        tag_name = f"link_{link_start.replace('.', '_')}"
        text_widget.tag_add(tag_name, link_start, link_end)
        text_widget.tag_config(tag_name, foreground="blue", underline=True)
        text_widget.tag_bind(tag_name, "<Button-1>",
                             lambda _e, d=doc_id: link_callback(int(d)))

        pos = end

    # Remainder of the text
    if pos < len(content):
        text_widget.insert("end", content[pos:])

