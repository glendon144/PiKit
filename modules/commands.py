import pandas as pd
import os
import re
from modules import logger, ai_interface

valid_commands = ["NEW", "LIST", "VIEW", "EDIT", "SAVE", "LOAD", "FOLLOW", "LINKS", "ASK", "SUMMARIZE", "SETOPENAI", "HELP", "AUTOLINK", "LOGS"]

class CommandProcessor:
    def __init__(self, doc_store):
        self.doc_store = doc_store
        self.logger = logger.Logger()
        self.ai = ai_interface.AIInterface()

    def parse_links(self, body):
        engel_links = re.findall(r'\[\[(.*?)\|(.*?)\]\]', body)
        md_links = re.findall(r'\[(.*?)\]\((.*?)\)', body)
        combined = [('E', text.strip(), target.strip()) for text, target in engel_links]
        combined += [('M', text.strip(), target.strip()) for text, target in md_links]
        return combined

    def process(self, user_input):
        parts = user_input.split()
        if not parts:
            return

        cmd = parts[0].upper()

        if cmd == 'NEW':
            title = ' '.join(parts[1:])
            doc_id = self.doc_store.new_document(title)
            print(f"Document {doc_id} created.")
            self.logger.log("user", "NEW", doc_id, title)

        elif cmd == 'LIST':
            print(self.doc_store.list_documents())

        elif cmd == 'VIEW':
            if len(parts) < 2:
                print("Usage: VIEW <doc_id>")
                return
            doc_id = int(parts[1])
            doc = self.doc_store.get_document(doc_id)
            if doc.empty:
                print("Document not found.")
            else:
                print(doc.iloc[0]['body'])

        elif cmd == 'EDIT':
            if len(parts) < 2:
                print("Usage: EDIT <doc_id>")
                return
            doc_id = int(parts[1])
            new_body = input("Enter text to append:\n")
            self.doc_store.edit_document(doc_id, new_body)
            print(f"Document {doc_id} updated.")
            self.logger.log("user", "EDIT", doc_id, f"{len(new_body)} chars appended")

        elif cmd == 'SAVE':
            if len(parts) < 3:
                print("Usage: SAVE <doc_id> <filename>")
                return
            doc_id = int(parts[1])
            filename = parts[2]
            doc = self.doc_store.get_document(doc_id)
            if doc.empty:
                print("Document not found.")
            else:
                with open(filename, "w") as f:
                    f.write(doc.iloc[0]['body'])
                print(f"Document {doc_id} saved to {filename}.")
                self.logger.log("user", "SAVE", doc_id, filename)

        elif cmd == 'LOAD':
            if len(parts) < 3:
                print("Usage: LOAD <doc_id> <filename>")
                return
            doc_id = int(parts[1])
            filename = parts[2]
            if not os.path.exists(filename):
                print("File not found.")
                return
            with open(filename, "r") as f:
                content = f.read()
            self.doc_store.edit_document(doc_id, content)
            print(f"Loaded content from {filename} into document {doc_id}.")
            self.logger.log("user", "LOAD", doc_id, filename)

        elif cmd == 'LINKS':
            if len(parts) < 2:
                print("Usage: LINKS <doc_id>")
                return
            doc_id = int(parts[1])
            doc = self.doc_store.get_document(doc_id)
            if doc.empty:
                print("Document not found.")
            else:
                body = doc.iloc[0]['body']
                links = self.parse_links(body)
                for idx, (kind, text, target) in enumerate(links, 1):
                    print(f"{kind}{idx}) Text: '{text}' --> Target: '{target}'")

        elif cmd == 'FOLLOW':
            if len(parts) < 3:
                print("Usage: FOLLOW <doc_id> <link_number>")
                return
            doc_id = int(parts[1])
            link_id = int(parts[2])
            doc = self.doc_store.get_document(doc_id)
            if doc.empty:
                print("Document not found.")
                return
            body = doc.iloc[0]['body']
            links = self.parse_links(body)
            if link_id > len(links):
                print("Invalid link ID.")
            else:
                _, text, target = links[link_id - 1]
                print(f"Following link: {target}")

        elif cmd == 'ASK':
            prompt = ' '.join(parts[1:])
            reply = self.ai.ask(prompt)
            print("AI Response:\n", reply)
            self.logger.log("user", "ASK", details=prompt)

        elif cmd == 'SUMMARIZE':
            if len(parts) < 2:
                print("Usage: SUMMARIZE <doc_id>")
                return
            doc_id = int(parts[1])
            doc = self.doc_store.get_document(doc_id)
            if doc.empty:
                print("Document not found.")
                return
            text = doc.iloc[0]['body']
            reply = self.ai.ask(f"Please summarize the following document:\n{text}")
            print("Summary:\n", reply)
            self.logger.log("user", "SUMMARIZE", doc_id)

        elif cmd == 'AUTOLINK':
            if len(parts) < 2:
                print("Usage: AUTOLINK <doc_id>")
                return
            doc_id = int(parts[1])
            doc = self.doc_store.get_document(doc_id)
            if doc.empty:
                print("Document not found.")
                return
            text = doc.iloc[0]['body']
            suggestion = self.ai.ask(f"Analyze this text and suggest hypertext links using Engelbart [[Text | Target]] syntax:\n{text}")
            self.doc_store.edit_document(doc_id, "\n" + suggestion)
            print("AI link suggestions appended.")
            self.logger.log("user", "AUTOLINK", doc_id)

        elif cmd == 'SETOPENAI':
            key = input("Enter OpenAI API Key: ").strip()
            os.makedirs("credentials", exist_ok=True)
            with open("credentials/openai_key.txt", "w") as f:
                f.write(key)
            print("OpenAI API key saved.")

        elif cmd == 'LOGS':
            with open("logs/command_log.txt", "r") as f:
                print(f.read())

        elif cmd == 'HELP':
            print("Available commands:", ", ".join(valid_commands))

        else:
            print(f"Unknown command: {cmd}")
            print("Valid commands are:", ", ".join(valid_commands))
