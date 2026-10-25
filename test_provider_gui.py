from types import SimpleNamespace
import tkinter as tk
from modules.ai_interface import AIInterface
from modules.provider_dropdown import ProviderDropdown
from modules.provider_registry import ProviderRegistry


def test_gui_save_replaces_active_client_and_persists(tmp_path):
    registry = ProviderRegistry(tmp_path / "providers.json")
    processor = SimpleNamespace(ai=AIInterface(registry=registry))
    root = tk.Tk()
    root.withdraw()
    root.status = tk.StringVar()
    try:
        dialog = ProviderDropdown(root, processor)
        dialog.var.set("Local")
        dialog.load()
        dialog.fields["base_url"].set("http://localhost:9876/v1")
        dialog.fields["model"].set("gui-model")
        dialog.fields["api_key"].set("")
        dialog.save()
        assert processor.ai.provider == "local"
        assert str(processor.ai.client.base_url) == "http://localhost:9876/v1/"
        assert ProviderRegistry(registry.path).read_selected() == "local"
        assert "Local" in root.status.get()
    finally:
        root.destroy()
