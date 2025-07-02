import readline

class CommandLineApp:
    def __init__(self, processor):
        self.processor = processor

    def run(self):
        print("Welcome to DemoKit Phase 6.0 — Hybrid Kernel (CLI Mode)")
        while True:
            try:
                user_input = input("> ").strip()
                if user_input.lower() in ['exit', 'quit']:
                    break
                self.process(user_input)
            except EOFError:
                break

    def process(self, user_input):
        parts = user_input.split()
        if not parts:
            return

        cmd = parts[0].upper()
        try:
            if cmd == 'NEW':
                title = ' '.join(parts[1:])
                doc_id = self.processor.new_document(title)
                print(f"Document {doc_id} created.")

            elif cmd == 'LIST':
                print(self.processor.list_documents())

            elif cmd == 'VIEW':
                doc = self.processor.view_document(int(parts[1]))
                print(doc if doc else "Document not found.")

            elif cmd == 'EDIT':
                doc_id = int(parts[1])
                new_body = input("Enter text to append:\n")
                self.processor.edit_document(doc_id, new_body)
                print(f"Document {doc_id} updated.")

            elif cmd == 'SAVE':
                doc_id, filename = int(parts[1]), parts[2]
                if self.processor.save_document(doc_id, filename):
                    print(f"Document {doc_id} saved to {filename}.")
                else:
                    print("Document not found.")

            elif cmd == 'LOAD':
                doc_id, filename = int(parts[1]), parts[2]
                self.processor.load_document(doc_id, filename)
                print(f"Loaded file into document {doc_id}.")

            elif cmd == 'LINKS':
                doc_id = int(parts[1])
                links = self.processor.extract_links(doc_id)
                for idx, (kind, text, target) in enumerate(links, 1):
                    print(f"{kind}{idx}) '{text}' -> '{target}'")

            elif cmd == 'FOLLOW':
                doc_id, link_str = int(parts[1]), parts[2]
                link_id = int(link_str[1:]) if link_str[0] in "EM" else int(link_str)
                target = self.processor.follow_link(doc_id, link_id)
                print(f"Following link: {target}" if target else "Invalid link.")

            elif cmd == 'ASK':
                prompt = ' '.join(parts[1:])
                reply = self.processor.ask_ai(prompt)
                print("AI Response:\n", reply)

            elif cmd == 'SUMMARIZE':
                doc_id = int(parts[1])
                reply = self.processor.summarize(doc_id)
                print("Summary:\n", reply if reply else "Document not found.")

            elif cmd == 'AUTOLINK':
                doc_id = int(parts[1])
                suggestion = self.processor.autolink(doc_id)
                print("AI Links added.")

            elif cmd == 'HELP':
                print("Available commands: NEW, LIST, VIEW, EDIT, SAVE, LOAD, LINKS, FOLLOW, ASK, SUMMARIZE, AUTOLINK, HELP, EXIT")

            else:
                print(f"Unknown command: {cmd}")

        except Exception as e:
            print("Error:", e)
