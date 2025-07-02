#!/usr/bin/env python3
"""
Command-line interface for DemoKit using the existing SQLite-backed DocumentStore and AIInterface.
Supports import/export of CSV, listing, viewing, and invoking the AI.
"""
import argparse
import sys
from modules.document_store import DocumentStore
from modules.ai_interface import AIInterface
from modules.command_processor import CommandProcessor

def main():
    parser = argparse.ArgumentParser(
        prog="demokit-cli",
        description="Manage documents and interact with AI via the command line"
    )
    subparsers = parser.add_subparsers(dest='command', required=True)

    # Import CSV -> SQLite
    imp = subparsers.add_parser('import', help='Import documents from a CSV file into the database')
    imp.add_argument('csvfile', help='Path to input CSV (title,body rows)')

    # Export SQLite -> CSV
    exp = subparsers.add_parser('export', help='Export all documents from the database to a CSV file')
    exp.add_argument('csvfile', help='Path to output CSV')

    # List documents
    subparsers.add_parser('list', help='List document IDs and summaries')

    # View a document
    view = subparsers.add_parser('view', help='View a document by ID')
    view.add_argument('id', type=int, help='Document ID to view')

    # Ask AI
    ask = subparsers.add_parser('ask', help='Ask the AI to expand on a prompt or existing document')
    ask.add_argument('doc_id', nargs='?', type=int, help='Optional source document ID to link from')
    ask.add_argument('prompt', nargs='+', help='Prompt text for the AI')

    args = parser.parse_args()

    store = DocumentStore()
    ai = AIInterface()
    processor = CommandProcessor(store, ai)

    if args.command == 'import':
        try:
            store.import_csv(args.csvfile)
            print(f"Imported CSV into database from '{args.csvfile}'")
        except Exception as e:
            print(f"Error importing CSV: {e}", file=sys.stderr)
            sys.exit(1)

    elif args.command == 'export':
        try:
            store.export_csv(args.csvfile)
            print(f"Exported database documents to CSV '{args.csvfile}'")
        except Exception as e:
            print(f"Error exporting CSV: {e}", file=sys.stderr)
            sys.exit(1)

    elif args.command == 'list':
        docs = store.list_documents()
        for doc_id, summary in docs:
            print(f"{doc_id}: {summary}")

    elif args.command == 'view':
        doc = store.get_document(args.id)
        if not doc:
            print(f"No document found with ID {args.id}", file=sys.stderr)
            sys.exit(2)
        print(f"Document {doc['id']} - {doc['title']} (created {doc['created_at']})\n")
        print(doc['body'])

    elif args.command == 'ask':
        prompt_text = ' '.join(args.prompt)
        if args.doc_id:
            # Use the interactive query flow: insert link back to source doc
            processor.query_ai(
                prompt_text,
                args.doc_id,
                lambda new_id: print(f"AI response saved as document {new_id}"),
                lambda: None
            )
        else:
            # Simple ask without linking
            reply = processor.ask_question(prompt_text)
            if reply:
                new_id = store.add_document("AI Response", reply)
                print(f"AI response saved as document {new_id}")
            else:
                print("No reply from AI.")

if __name__ == '__main__':
    main()
