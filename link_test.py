import tkinter as tk, re

def render(txt):
    pattern = re.compile(r"\[([^\]]+)\]\(doc:(\d+)\)")
    idx = 0
    for m in pattern.finditer(txt):
        start, end = m.span()
        if start > idx:
            t.insert(tk.END, txt[idx:start])
        link, doc = m.group(1), m.group(2)
        tag = f"doc{doc}"
        pos0 = t.index(tk.END)
        t.insert(tk.END, link)
        pos1 = t.index(tk.END)
        t.tag_add(tag, pos0, pos1)
        t.tag_config(tag, foreground="#ff0000", background="#ffff66", underline=1)
        idx = end
    if idx < len(txt):
        t.insert(tk.END, txt[idx:])

root = tk.Tk()
t = tk.Text(root, font=("Arial", 12))
t.pack()
render("Example [Click me](doc:42) end.")
root.mainloop()

