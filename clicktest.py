import tkinter as tk

root = tk.Tk()
txt = tk.Text(root)
txt.pack()
txt.insert("1.0", "This is a link: ")
txt.insert(tk.END, "test")
txt.tag_add("mylink", "1.16", "1.20")
txt.tag_config("mylink", foreground="blue", underline=1, cursor="hand2")
txt.tag_bind("mylink", "<Button-1>", lambda e: print("clicked!"))
root.mainloop()

