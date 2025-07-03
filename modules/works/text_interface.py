# File: modules/text_interface.py
import readline

def run_text_loop(store, ai, processor):
    print("Entering text-only mode. Commands: get <id>, ask <id> <prompt>, exit")
    while True:
        try:
            cmd = input("> ")
        except (EOFError, KeyboardInterrupt):
            print()
            break
        parts = cmd.strip().split(maxsplit=2)
        if not parts:
            continue
        action = parts[0].lower()
        if action in ("exit", "quit"):
            break
        elif action == "get" and len(parts) >= 2:
            doc = store.get_document(int(parts[1]))
            print(doc.get("body", ""))
        elif action == "ask" and len(parts) == 3:
            doc_id = int(parts[1])
            reply = processor.ask_question(parts[2])
            if reply:
                new_id = store.add_document("AI Response", reply)
                print(f"Response saved as document {new_id}")
        else:
            print("Usage: get <id>, ask <id> <prompt>, exit")
