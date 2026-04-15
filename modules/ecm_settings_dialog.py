"""
ECM settings dialog for PiKit.
"""

from __future__ import annotations

import json
from pathlib import Path
import tkinter as tk
from tkinter import ttk, messagebox

from modules.ecm import ECMConfig, BoundaryLevel


def open_ecm_settings_dialog(app) -> None:
    processor = getattr(app, "processor", None)
    bridge = getattr(processor, "ecm_bridge", None)
    if bridge is None:
        messagebox.showerror("PiKit", "ECM bridge is not available.")
        return

    settings_path = Path(bridge.settings_path)
    base_cfg = ECMConfig.from_dict(bridge.base_config.to_dict())

    win = tk.Toplevel(app)
    win.title("ECM Settings")
    win.geometry("700x620")
    win.transient(app)
    win.grab_set()

    slider_vars = {
        "warmth": tk.DoubleVar(value=base_cfg.warmth),
        "directness": tk.DoubleVar(value=base_cfg.directness),
        "agreement": tk.DoubleVar(value=base_cfg.agreement),
        "formality": tk.DoubleVar(value=base_cfg.formality),
    }
    boundary_var = tk.StringVar(value=base_cfg.boundaries.value)
    status_var = tk.StringVar(value=f"Settings file: {settings_path}")

    frm = ttk.Frame(win, padding=12)
    frm.pack(fill="both", expand=True)

    ttk.Label(
        frm,
        text="Base ECM Settings",
        font=("TkDefaultFont", 11, "bold"),
    ).pack(anchor="w")
    ttk.Label(
        frm,
        text="These values persist to storage/ecm_settings.json and act as the baseline before adaptive overrides.",
        wraplength=640,
        justify="left",
    ).pack(anchor="w", pady=(4, 10))

    for key, label in (
        ("warmth", "Warmth"),
        ("directness", "Directness"),
        ("agreement", "Agreement"),
        ("formality", "Formality"),
    ):
        row = ttk.Frame(frm)
        row.pack(fill="x", pady=6)
        ttk.Label(row, text=label, width=14).pack(side="left")
        scale = ttk.Scale(row, from_=0.0, to=1.0, variable=slider_vars[key])
        scale.pack(side="left", fill="x", expand=True, padx=(0, 10))
        ttk.Label(
            row,
            textvariable=tk.StringVar(
                value=f"{slider_vars[key].get():.2f}"
            ),
            width=6,
        )

        value_label = ttk.Label(row, width=6)
        value_label.pack(side="left")

        def _sync_label(var=slider_vars[key], lbl=value_label):
            lbl.config(text=f"{var.get():.2f}")

        slider_vars[key].trace_add("write", lambda *args, fn=_sync_label: fn())
        _sync_label()

    boundary_frame = ttk.LabelFrame(frm, text="Boundaries", padding=10)
    boundary_frame.pack(fill="x", pady=(12, 10))
    for level in BoundaryLevel:
        ttk.Radiobutton(
            boundary_frame,
            text=level.value.title(),
            value=level.value,
            variable=boundary_var,
        ).pack(side="left", padx=(0, 16))

    snapshot_frame = ttk.LabelFrame(frm, text="Current ECM Snapshot", padding=10)
    snapshot_frame.pack(fill="both", expand=True, pady=(8, 10))

    snapshot = tk.Text(snapshot_frame, wrap="none", height=14, font=("Courier", 10))
    snapshot.pack(fill="both", expand=True)

    def refresh_snapshot():
        payload = {
            "preamp": bridge.get_debug_info(),
            "ecm2": processor.get_ecm_snapshot() if hasattr(processor, "get_ecm_snapshot") else {},
        }
        snapshot.config(state="normal")
        snapshot.delete("1.0", "end")
        snapshot.insert("1.0", json.dumps(payload, indent=2))
        snapshot.config(state="disabled")

    def build_config() -> ECMConfig:
        cfg = ECMConfig(
            warmth=slider_vars["warmth"].get(),
            directness=slider_vars["directness"].get(),
            agreement=slider_vars["agreement"].get(),
            formality=slider_vars["formality"].get(),
            boundaries=BoundaryLevel(boundary_var.get()),
        )
        cfg.clamp()
        return cfg

    def save():
        cfg = build_config()
        try:
            settings_path.parent.mkdir(parents=True, exist_ok=True)
            cfg.save_json(str(settings_path))
            bridge.base_config = cfg
            bridge.config = ECMConfig.from_dict(cfg.to_dict())
            bridge.preamp.config = bridge.config
            status_var.set(f"Saved ECM settings to {settings_path}")
            refresh_snapshot()
        except Exception as e:
            messagebox.showerror("PiKit", f"Failed saving ECM settings: {e}")

    btns = ttk.Frame(frm)
    btns.pack(fill="x")
    ttk.Button(btns, text="Refresh Snapshot", command=refresh_snapshot).pack(side="left")
    ttk.Button(btns, text="Save", command=save).pack(side="left", padx=8)
    ttk.Button(btns, text="Close", command=win.destroy).pack(side="right")

    ttk.Label(frm, textvariable=status_var, anchor="w").pack(fill="x", pady=(8, 0))

    refresh_snapshot()
    win.protocol("WM_DELETE_WINDOW", win.destroy)
