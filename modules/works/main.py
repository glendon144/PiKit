# File: main.py
import sys
import argparse
import tkinter as tk
from modules.document_store import DocumentStore
from modules.ai_interface import AIInterface
from modules.command_processor import CommandProcessor
from modules.gui_tkinter import DemoKitGUI


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--text",
        action="store_true",
        help="Run in text-only mode (CLI REPL)"
    )
    args = parser.parse_args()

    store = DocumentStore()
    ai = AIInterface()
    processor = CommandProcessor(store, ai)

    if args.text:
        from modules.text_interface import run_text_loop
        run_text_loop(store, ai, processor)
        return

    root = tk.Tk()
    root.title("DemoKit")
    app = DemoKitGUI(root, store, processor)
    root.mainloop()


if __name__ == "__main__":
    main()

