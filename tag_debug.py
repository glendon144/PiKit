import tkinter as tk, re

root = tk.Tk()
t     = tk.Text(root, font=("Arial", 14))
t.pack()

text = "Example [Click me](doc:42) end."
pat  = re.compile(r"\[([^\]]+)\]\(doc:(\d+)\)")

idx = 0
for m in pat.finditer(text):
    start, end  = m.span()
    if start > idx:
        t.insert(tk.END, text[idx:start])

    link, doc = m.group(1), m.group(2)
    tag       = f"doc{doc}"
    pos0      = t.index(tk.END)
    t.insert(tk.END, link)
    pos1      = t.index(tk.END)

    # configure loud colours
    t.tag_add(tag, pos0, pos1)
    t.tag_config(tag, foreground="#ff0000", background="#ffff66", underline=1)

    # DEBUG: print exactly what Tk thinks
    print("ranges:", t.tag_ranges(tag),
          "fg:", t.tag_cget(tag, "foreground"),
          "bg:", t.tag_cget(tag, "background"),
          "ul:", t.tag_cget(tag, "underline"))
    idx = end

if idx < len(text):
    t.insert(tk.END, text[idx:])

root.mainloop()

