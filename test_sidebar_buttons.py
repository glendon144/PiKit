# save as test_sidebar_buttons.py and run: python test_sidebar_buttons.py
import tkinter as tk

root = tk.Tk()
root.title("Sidebar-button test")
root.geometry("300x250")

# sidebar
sidebar_frame = tk.Frame(root, bg="#eeeeee")
sidebar_frame.grid(row=0, column=0, sticky="ns")
lb = tk.Listbox(sidebar_frame, width=20); lb.grid(row=0, column=0, sticky="ns")
for i in range(1, 6):
    lb.insert(tk.END, f"Doc {i}")

btn_frame = tk.Frame(sidebar_frame, bg="#cccccc")
btn_frame.grid(row=1, column=0, pady=8)

tk.Button(btn_frame, text="Edit").pack(fill=tk.X)
tk.Button(btn_frame, text="Delete").pack(fill=tk.X, pady=4)

# a dummy editor to fill the right side
editor = tk.Text(root, width=25); editor.grid(row=0, column=1, sticky="nsew")

root.grid_rowconfigure(0, weight=1)
root.grid_columnconfigure(1, weight=1)
root.mainloop()

