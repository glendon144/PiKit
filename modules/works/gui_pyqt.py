from PySide2 import QtWidgets, QtCore
from PySide2.QtWidgets import QMainWindow, QListWidget, QTextEdit, QPushButton, QVBoxLayout, QWidget, QMessageBox

class DemoKitGUI(QMainWindow):
    def __init__(self, processor):
        super().__init__()
        self.processor = processor
        self.setWindowTitle("DemoKit Phase 6.1 — PySide2 Compatible")
        self.resize(1000, 600)
        self.initUI()
        self.load_documents()

    def initUI(self):
        self.doc_list = QListWidget()
        self.text_edit = QTextEdit()
        self.save_button = QPushButton("Save Changes")

        layout = QVBoxLayout()
        layout.addWidget(self.doc_list)
        layout.addWidget(self.text_edit)
        layout.addWidget(self.save_button)

        container = QWidget()
        container.setLayout(layout)
        self.setCentralWidget(container)

        self.doc_list.itemClicked.connect(self.load_selected_document)
        self.save_button.clicked.connect(self.save_document)

    def load_documents(self):
        self.doc_list.clear()
        df = self.processor.list_documents()
        for _, row in df.iterrows():
            self.doc_list.addItem(f"{row['doc_id']}: {row['title']}")

    def load_selected_document(self, item):
        doc_id = int(item.text().split(":")[0])
        self.current_doc_id = doc_id
        body = self.processor.view_document(doc_id)
        self.text_edit.setPlainText(body)

    def save_document(self):
        new_body = self.text_edit.toPlainText()
        self.processor.edit_document(self.current_doc_id, new_body)
        QMessageBox.information(self, "Saved", "Document updated successfully.")
