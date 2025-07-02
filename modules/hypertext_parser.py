import re

def parse_links(text_widget, content, link_callback):
    """
    Parses markdown-style links such as "[label](id:123)" or "[label](doc:123)"
    and makes them clickable, marking visited links in dark green.
    This method delegates all text insertion to the parser to avoid raw markdown.
    """
    # Accept both id:123 and doc:123
    link_pattern = re.compile(r'\[([^\]]+)\]\((?:id|doc):(\d+)\)')
    pos = 0
    for match in link_pattern.finditer(content):
        start, end = match.span()
        label, doc_id = match.groups()

        # Insert plain text before the link
        if start > pos:
            text_widget.insert("end", content[pos:start])

        # Insert the link text with a unique tag
        link_start = text_widget.index("end")
        text_widget.insert("end", label)
        link_end = text_widget.index("end")

        tag_name = f"link_{link_start.replace('.', '_')}"
        # Configure link appearance
        text_widget.tag_add(tag_name, link_start, link_end)
        text_widget.tag_config(tag_name, foreground="green", underline=True)

        # On click, navigate and mark visited
        def on_click(e, d=doc_id, tag=tag_name):
            link_callback(int(d))
            text_widget.tag_config(tag, foreground="darkgreen")
        text_widget.tag_bind(tag_name, "<Button-1>", on_click)

        pos = end

    # Insert any remaining text after last link
    if pos < len(content):
        text_widget.insert("end", content[pos:])
