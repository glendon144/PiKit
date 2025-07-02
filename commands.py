import importlib.util
import os

class CommandProcessor:
    def __init__(self, doc_store, event_logger):
        self.doc_store = doc_store
        self.event_logger = event_logger
        self.commands = {}
        self.help_texts = {}
        self.context = {}

        self.register_builtin_commands()
        self.load_plugins()

    def register_command(self, name, func, help="No help available."):
        self.commands[name.upper()] = func
        self.help_texts[name.upper()] = help

    def process(self, input_line):
        if not input_line.strip():
            return
        parts = input_line.split(maxsplit=1)
        cmd = parts[0].upper()
        args = parts[1] if len(parts) > 1 else ""
        if cmd in self.commands:
            self.commands[cmd](args, self.context)
        else:
            print("Unknown command:", cmd)
            self.show_help()

    def show_help(self):
        print("\nAvailable commands:")
        for name, help in sorted(self.help_texts.items()):
            print(f"  {name}: {help}")

    def register_builtin_commands(self):
        self.register_command("HELP", lambda a, c: self.show_help(), help="Show this help message.")
        self.register_command("LIST", self.cmd_list, help="List all documents.")
        self.register_command("NEW", self.cmd_new, help="Create a new document.")
        self.register_command("EDIT", self.cmd_edit, help="Append text to a document.")
        self.register_command("VIEW", self.cmd_view, help="View a document.")
        # ... other built-ins as before ...

    def load_plugins(self):
        plugins_dir = "plugins"
        if not os.path.isdir(plugins_dir):
            os.makedirs(plugins_dir)
        for fname in os.listdir(plugins_dir):
            if fname.endswith(".py"):
                fpath = os.path.join(plugins_dir, fname)
                spec = importlib.util.spec_from_file_location(fname[:-3], fpath)
                plugin = importlib.util.module_from_spec(spec)
                try:
                    spec.loader.exec_module(plugin)
                    if hasattr(plugin, "register"):
                        plugin.register(self.register_command)
                        print(f"Loaded plugin: {fname}")
                except Exception as e:
                    print(f"Failed to load plugin {fname}: {e}")

    # Built-in command implementations (simplified for space)
    def cmd_list(self, args, context):
        print(self.doc_store.list_documents())

    def cmd_new(self, args, context):
        doc_id = self.doc_store.new_document(args.strip() or "Untitled")
        print(f"Document {doc_id} created.")

    def cmd_edit(self, args, context):
        parts = args.split(maxsplit=1)
        if not parts:
            print("Usage: EDIT <doc_id> <text>")
            return
        doc_id = int(parts[0])
        text = parts[1] if len(parts) > 1 else ""
        doc = self.doc_store.get_document(doc_id)
        if doc.empty:
            print("Document not found.")
            return
        body = str(doc.iloc[0].get("body", "") or "")
        new_body = body + "\n" + text
        self.doc_store.edit_document(doc_id, new_body)
        print(f"Document {doc_id} updated.")

    def cmd_view(self, args, context):
        try:
            doc_id = int(args)
            doc = self.doc_store.get_document(doc_id)
            if not doc.empty:
                print(doc.iloc[0].get("body", ""))
            else:
                print("Document not found.")
        except Exception:
            print("Usage: VIEW <doc_id>")

