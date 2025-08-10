from pathlib import Path
import re

p = Path("modules/gui_tkinter.py")
src = p.read_text(encoding="utf-8")
backup = Path("modules/gui_tkinter.py.bak")
backup.write_text(src, encoding="utf-8")

# 1) Locate DemoKitGUI class block (start at class, end at next top-level class or EOF)
cls_pat = re.compile(r'(?m)^class\s+DemoKitGUI\b[^\n]*:\s*\n')
m = cls_pat.search(src)
if not m:
    raise SystemExit("Could not find class DemoKitGUI")

cls_start = m.start()
# Find end of class by next top-level class/def OR EOF
after = src[m.end():]
m_end = re.search(r'(?m)^(class\s+\w+|def\s+\w+)\b', after)
cls_end = m.end() + (m_end.start() if m_end else len(after))

class_block = src[m.end():cls_end]

# 2) Remove ANY existing export_and_launch_server defs in the class block (def and its body)
def_pat = re.compile(r'(?m)^\s{4}def\s+export_and_launch_server\s*\(\s*self\s*\)\s*:[\s\S]*?(?=^\s{4}def\s+\w+\s*\(|\Z)')
class_block_clean = def_pat.sub('', class_block)

# 3) Build the correctly indented method (4 spaces)
method = """
    def export_and_launch_server(self):
        \"\"\"Export documents to JSON and ensure the Flask server is running on 5050, then open browser.\"\"\"
        try:
            # 1) Export current docs for the Flask UI to consume
            export_path = Path("exported_docs")
            export_path.mkdir(exist_ok=True)

            for doc in self.doc_store.get_document_index():
                data = dict(self.doc_store.get_document(doc["id"]))
                if not data:
                    continue
                data = sanitize_doc(data)
                with open(export_path / f"{data['id']}.json", "w", encoding="utf-8") as f:
                    json.dump(data, f, indent=2)

            # 2) Resolve paths relative to the repository, not CWD
            repo_root = Path(__file__).resolve().parent.parent         # <repo>/
            fp = Path(__file__).resolve().parent / "flask_server.py"   # <repo>/modules/flask_server.py

            # 3) Start Flask if it's not already listening on 5050
            if not _is_port_open(FLASK_HOST, FLASK_PORT):
                if not fp.exists():
                    messagebox.showerror("Flask Launch", f"Cannot find {fp}")
                    return
                try:
                    subprocess.Popen(
                        [sys.executable, str(fp)],
                        cwd=str(repo_root),          # run from repo root so relative paths work
                        stdout=subprocess.DEVNULL,
                        stderr=subprocess.DEVNULL,
                    )
                except Exception as e:
                    messagebox.showerror("Flask Launch Error", str(e))
                    return

                # brief wait so first-time startup has a moment to bind
                for _ in range(10):
                    if _is_port_open(FLASK_HOST, FLASK_PORT):
                        break
                    self.update_idletasks()
                    self.after(100)

            # 4) Open in browser and notify
            webbrowser.open(FLASK_URL)
            messagebox.showinfo("Server Started", f"Flask server launched at {FLASK_URL}")

        except Exception as e:
            messagebox.showerror("Flask Launch Error", str(e))
""".rstrip("\n")

# 4) Insert before _save_binary_as_text if present, else append at end of class
anchor = re.search(r'(?m)^\s{4}def\s+_save_binary_as_text\s*\(', class_block_clean)
if anchor:
    insert_at = anchor.start()
    new_class_block = class_block_clean[:insert_at] + method + "\n\n" + class_block_clean[insert_at:]
else:
    new_class_block = class_block_clean.rstrip() + "\n\n" + method + "\n"

# 5) Reassemble file
new_src = src[:m.end()] + new_class_block + src[cls_end:]
p.write_text(new_src, encoding="utf-8")
print("Patched modules/gui_tkinter.py successfully. Backup at", backup)

