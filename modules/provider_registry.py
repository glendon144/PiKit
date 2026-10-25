"""Adapted from Dream Communicator Deluxe's FunKit provider registry.

Private, atomic persistence; unknown providers never fall back.
"""
import json
import os
import tempfile
from pathlib import Path
from urllib.parse import urlsplit

LABELS = {"baseten": "Baseten", "local": "Local", "custom": "Third-party"}
ENV = {"baseten": "BASETEN", "local": "PIKIT_OPENAI", "custom": "PIKIT_CUSTOM"}


def validate(config):
    url = urlsplit(config["base_url"])
    if (url.scheme not in ("http", "https") or not url.hostname or
            url.username or url.password or url.query or url.fragment):
        raise ValueError("Use an http(s) base URL without credentials, query, or fragment.")
    if not config["model"].strip():
        raise ValueError("Enter a model name for this provider.")


class ProviderRegistry:
    def __init__(self, path=None):
        self.path = Path(path) if path else Path.home() / ".config" / "pikit" / "providers.json"
        self.providers = {
            "baseten": {"base_url": os.getenv("BASETEN_BASE_URL", "https://inference.baseten.co/v1"),
                        "model": os.getenv("BASETEN_MODEL", "openai/gpt-oss-120b")},
            "local": {"base_url": os.getenv("PIKIT_OPENAI_BASE_URL", "http://localhost:8081/v1"),
                      "model": os.getenv("PIKIT_MODEL_NAME", "local-model")},
            "custom": {"base_url": os.getenv("PIKIT_CUSTOM_BASE_URL", ""),
                       "model": os.getenv("PIKIT_CUSTOM_MODEL", "")},
        }
        self.selected = "baseten"
        self.error = None
        if self.path.exists():
            try:
                data = json.loads(self.path.read_text())
                if not isinstance(data, dict) or not isinstance(data.get("providers"), dict):
                    raise ValueError()
                selected = data["selected_provider"]
                if selected not in LABELS:
                    raise ValueError()
                for key, cfg in data["providers"].items():
                    if key not in LABELS or not isinstance(cfg, dict):
                        raise ValueError()
                    if any(k not in ("base_url", "model", "api_key") or not isinstance(v, str)
                           for k, v in cfg.items()):
                        raise ValueError()
                    self.providers[key].update(cfg)
                self.selected = selected
            except (ValueError, KeyError, TypeError, OSError):
                self.selected = None
                self.error = "Provider settings could not be read. Choose and save a provider in Tools → Inference Provider. No request was sent."

    def list_labels(self):
        return list(LABELS.items())

    def get(self, key):
        if key not in LABELS:
            raise ValueError(self.error or "Choose a valid inference provider.")
        cfg = dict(self.providers[key])
        cfg.setdefault("api_key", os.getenv(ENV[key] + "_API_KEY", ""))
        return cfg

    def read_selected(self):
        return self.selected

    def save(self, key, config):
        if key not in LABELS:
            raise ValueError("Unknown inference provider.")
        validate(config)
        providers = {k: dict(v) for k, v in self.providers.items()}
        providers[key] = {k: config[k] for k in ("base_url", "model", "api_key")}
        self.path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        fd, name = tempfile.mkstemp(dir=self.path.parent, prefix=".providers-")
        try:
            with os.fdopen(fd, "w") as handle:
                json.dump({"selected_provider": key, "providers": providers}, handle, indent=2)
            os.replace(name, self.path)
        finally:
            if os.path.exists(name):
                os.unlink(name)
        self.providers, self.selected, self.error = providers, key, None
