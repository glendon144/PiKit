import pandas as pd
import re
import networkx as nx
import matplotlib.pyplot as plt

class HypertextVisualizer:
    def __init__(self, document_store):
        self.document_store = document_store

    def extract_links(self):
        df = self.document_store.df
        links = []
        for _, row in df.iterrows():
            doc_id = row['doc_id']
            body = row['body'] if pd.notnull(row['body']) else ""
            found = re.findall(r'doc:(\d+)', body)
            for target in found:
                links.append((doc_id, int(target)))
        return links

    def build_graph(self):
        df = self.document_store.df
        G = nx.DiGraph()
        for _, row in df.iterrows():
            G.add_node(row['doc_id'], label=row['title'])
        for src, tgt in self.extract_links():
            G.add_edge(src, tgt)
        return G

    def visualize(self, filename="hypertext_graph.png"):
        G = self.build_graph()
        pos = nx.spring_layout(G)
        labels = nx.get_node_attributes(G, 'label')
        plt.figure(figsize=(10, 8))
        nx.draw(G, pos, with_labels=False, node_color='skyblue', node_size=1500, arrowsize=20)
        nx.draw_networkx_labels(G, pos, labels, font_size=10)
        plt.title("Hypertext Network")
        plt.savefig(filename)
        plt.close()
        return filename
