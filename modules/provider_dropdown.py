"""Provider editor adapted from FunKit's ProviderDropdown (Dream Communicator)."""
import tkinter as tk
from tkinter import ttk, messagebox
from modules.ai_interface import AIInterface


class ProviderDropdown(tk.Toplevel):
    def __init__(self, parent, processor):
        super().__init__(parent)
        self.title("Inference Provider")
        self.processor = processor
        self.registry = processor.ai.registry
        self._labels = dict(self.registry.list_labels())
        self._key_by_label = {v: k for k, v in self._labels.items()}
        self.var = tk.StringVar(value=self._labels.get(self.registry.read_selected(), ""))
        ttk.Label(self, text="Provider").grid(row=0, column=0, padx=8, pady=8)
        self.cbo = ttk.Combobox(self, state="readonly", values=list(self._labels.values()), textvariable=self.var)
        self.cbo.grid(row=0, column=1, sticky="ew", padx=8)
        self.fields = {}
        for row, (key, label) in enumerate((("base_url", "Base URL (including /v1)"),
                                            ("model", "Model name"), ("api_key", "API key")), 1):
            ttk.Label(self, text=label).grid(row=row, column=0, padx=8, pady=6, sticky="w")
            var = self.fields[key] = tk.StringVar()
            ttk.Entry(self, textvariable=var, width=52, show="*" if key == "api_key" else "").grid(row=row, column=1, padx=8, sticky="ew")
        ttk.Label(self, text="Save applies this provider. Keys are stored in a private user file.\nLocal servers may use an empty key. Requests never fall back to another provider.").grid(row=4, column=0, columnspan=2, padx=8, pady=8)
        ttk.Button(self, text="Save and select", command=self.save).grid(row=5, column=1, sticky="e", padx=8, pady=8)
        self.cbo.bind("<<ComboboxSelected>>", self.load)
        self.columnconfigure(1, weight=1)
        self.load()

    def load(self, event=None):
        key = self._key_by_label.get(self.var.get())
        if key:
            config = self.registry.get(key)
            for name, var in self.fields.items():
                var.set(config[name])

    def save(self):
        key = self._key_by_label.get(self.var.get())
        config = {name: var.get().strip() for name, var in self.fields.items()}
        try:
            if key not in self._labels:
                raise ValueError("Choose an inference provider.")
            candidate = AIInterface(provider=key, registry=self.registry, **config)
            candidate._require_client()
            self.registry.save(key, config)
        except (ValueError, RuntimeError) as error:
            messagebox.showerror("Inference Provider", str(error), parent=self)
            return
        except OSError:
            messagebox.showerror("Inference Provider", "Could not save private provider settings. Check user-directory permissions.", parent=self)
            return
        self.processor.ai = candidate
        self.master.status.set(f"Provider: {self._labels[key]} · {candidate.model}")
        self.destroy()
