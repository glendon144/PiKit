# PiKit Command Processor (updated with memory preamble + truncation + adaptive length)
from __future__ import annotations

import os
import time
from pathlib import Path
from typing import Any, Tuple

from modules.logger import Logger
from modules.document_store import DocumentStore
from modules.directory_import import import_text_files_from_directory
from modules.ai_memory import get_memory, set_memory
from modules.text_sanitizer import sanitize_ai_reply
from modules.ecm_bridge import ECMBridge

# ------------ Config (env-tunable) ------------
SHORT_THRESHOLD_TOKENS = int(os.getenv("PIKIT_SHORT_THRESHOLD_TOKENS", "200"))
SHORT_MAX_TOKENS = int(os.getenv("PIKIT_SHORT_MAX_TOKENS", "220"))  # quick replies
LONG_MAX_TOKENS = int(os.getenv("PIKIT_LONG_MAX_TOKENS", "900"))    # detailed replies
# If you simply want to "double tokens", bump LONG_MAX_TOKENS and/or SHORT_MAX_TOKENS above.
# Timeout was already made env-configurable in ai_interface/local_ai_interface earlier.


class CommandProcessor:
    def __init__(
        self,
        store: DocumentStore | None = None,
        ai_interface=None,
        logger: Logger | None = None,
    ):
        """
        CommandProcessor wiring:
        - store: DocumentStore instance (optional; default = new DocumentStore())
        - ai_interface: object with .query(prompt, **kwargs) (optional; best-effort default)
        - logger: Logger instance (optional; default = new Logger())
        """
        self.doc_store = store if store is not None else DocumentStore()
        self.ai = ai_interface if ai_interface is not None else self._init_default_ai()
        self.logger = logger if logger is not None else Logger()
        self.ecm_bridge = ECMBridge()
        self.ecm_engine = self._init_ecm_engine()

    def _init_default_ai(self):
        """
        Best-effort default AI interface loader.
        This keeps older PiKit setups working without requiring explicit wiring.
        """
        try:
            from modules import ai_interface as ai_mod  # type: ignore[attr-defined]

            # Common patterns we've used in past builds:
            if hasattr(ai_mod, "get_ai"):
                return ai_mod.get_ai()
            if hasattr(ai_mod, "AIInterface"):
                return ai_mod.AIInterface()
            # Fallback: treat module itself as the interface if it has .query
            if hasattr(ai_mod, "query"):
                return ai_mod
            raise RuntimeError("modules.ai_interface has no usable entrypoint")
        except Exception as e:
            # Fail loud so the user sees a clear error instead of silent no-op AI
            raise RuntimeError(
                "No ai_interface provided and automatic AI init failed."
            ) from e

    def _init_ecm_engine(self):
        """
        Best-effort ECM2 loader.
        If optional deps are missing, PiKit still works with the text preamp.
        """
        try:
            from modules.ecm2 import ECMEngine

            storage_dir = Path(__file__).resolve().parent.parent / "storage"
            storage_dir.mkdir(parents=True, exist_ok=True)
            engine = ECMEngine(db_path=str(storage_dir / "ecm_labels.db"))
            engine.start()
            return engine
        except Exception as e:
            self.logger.info(f"ECM2 unavailable; continuing with preamp only: {e}")
            return None

    def shutdown(self) -> None:
        engine = getattr(self, "ecm_engine", None)
        if not engine:
            return
        try:
            engine.stop()
        except Exception as e:
            self.logger.info(f"Non-fatal: failed to stop ECM2 engine: {e}")

    def _event_to_key_id(self, event) -> tuple[str | None, bool]:
        keysym = getattr(event, "keysym", "") or ""
        char = getattr(event, "char", "") or ""

        if keysym == "BackSpace":
            return "<BS>", True
        if keysym in {"Return", "KP_Enter"}:
            return "<ENT>", False
        if keysym == "space":
            return "<SP>", False
        if keysym == "Tab":
            return "<TAB>", False
        if keysym in {"Shift_L", "Shift_R"}:
            return "<SHIFT>", False
        if keysym in {"Control_L", "Control_R"}:
            return "<CTRL>", False
        if keysym in {"Alt_L", "Alt_R"}:
            return "<ALT>", False
        if char:
            if char.isalpha():
                return "<A>", False
            if char.isdigit():
                return "<D>", False
            if char.isspace():
                return "<SP>", False
            return "<P>", False
        return None, False

    def ingest_tk_keypress(self, event) -> None:
        engine = getattr(self, "ecm_engine", None)
        if not engine:
            return
        key_id, is_backspace = self._event_to_key_id(event)
        if not key_id:
            return
        try:
            engine.add_key_event(ts=time.time(), key_id=key_id, is_backspace=is_backspace)
        except Exception as e:
            self.logger.info(f"Non-fatal: failed to capture ECM2 key event: {e}")

    def get_ecm_snapshot(self) -> dict[str, Any]:
        engine = getattr(self, "ecm_engine", None)
        if not engine:
            return {}
        try:
            return engine.now().model_dump()
        except Exception:
            return {}

    def _build_ecm2_preamble(self, snapshot: dict[str, Any]) -> str:
        if not snapshot:
            return ""

        mode = snapshot.get("tempo_mode", "normal")
        valence = float(snapshot.get("valence", 0.0) or 0.0)
        confidence = float(snapshot.get("confidence", 0.0) or 0.0)
        tokens_per_minute = int(snapshot.get("tokens_per_minute", 0) or 0)

        lines = ["[ECM2 Temporal Signals]"]
        lines.append(
            f"- tempo_mode={mode}; valence={valence:.2f}; confidence={confidence:.2f}; advisory_tpm={tokens_per_minute}"
        )

        if mode == "rest":
            lines.append("- Keep the reply compact, calm, and low-pressure.")
        elif mode == "slow":
            lines.append("- Use measured pacing and shorter paragraphs.")
        else:
            lines.append("- Normal pacing is fine; stay responsive and clear.")

        if valence < -0.25:
            lines.append("- Favor grounding and clarity over exuberance.")
        elif valence > 0.35:
            lines.append("- A lightly upbeat tone is acceptable, but avoid hype.")

        return "\n".join(lines)

    # -------------------------------------
    # Helper: memory prefix (legacy, still usable elsewhere)
    # -------------------------------------
    def build_memory_prefix(self) -> str:
        """
        Build a short "context preamble" from PiKit's AI memory.
        """
        conn = self._get_conn()
        if not conn:
            return ""

        try:
            mem = get_memory(conn, key="global")
        except Exception as e:
            self.logger.error(f"build_memory_prefix: failed to load memory: {e}")
            return ""

        if not mem:
            return ""

        # Very small, human-readable preamble
        lines = ["[PiKit Memory Snapshot]"]
        notes = mem.get("notes") or []
        for note in notes[-5:]:
            lines.append(f"- {note}")
        return "\n".join(lines)

    def _get_conn(self):
        """
        If DocumentStore has a connection getter, use it.
        Otherwise return None (memory preamble becomes empty).
        """
        if hasattr(self.doc_store, "get_connection"):
            try:
                return self.doc_store.get_connection()
            except Exception as e:
                self.logger.error(f"_get_conn failed: {e}")
        return None

    # -------------------------------------
    # Helper: pick length policy from prompt
    # -------------------------------------
    def _choose_length_policy(self, prompt: str) -> Tuple[int | None, str]:
        """
        Inspect the user's prefix/instruction to decide how long the answer should be.

        Returns:
            (max_tokens, steering_suffix)
        """
        text = prompt.lower()

        # Explicit user overrides first
        if "bullet points" in text or "bullet-point" in text:
            return SHORT_MAX_TOKENS, "Please answer in concise bullet points."
        if "short answer" in text or "keep it brief" in text or "short version" in text:
            return SHORT_MAX_TOKENS, "Please keep the answer brief but complete."
        if "long answer" in text or "go into detail" in text or "deep dive" in text:
            return LONG_MAX_TOKENS, "You may answer in more detail, but keep it coherent."

        # Heuristic based on length of prefix
        approx_prompt_tokens = max(1, len(prompt) // 4)  # crude char→token guess

        if approx_prompt_tokens < SHORT_THRESHOLD_TOKENS // 4:
            # Very small selection / prefix → short answer
            return SHORT_MAX_TOKENS, "Please answer succinctly, focusing on the key idea."
        elif approx_prompt_tokens < SHORT_THRESHOLD_TOKENS:
            # Medium → medium-ish but within short budget
            return SHORT_MAX_TOKENS, (
                "Please answer clearly but do not exceed a moderate length."
            )
        else:
            # Large prompt → we assume user can handle more detail
            return LONG_MAX_TOKENS, (
                "Please provide a detailed but well-structured answer. "
                "Avoid digressions and stay on-topic."
            )

    # -------------------------------------
    # Helper: apply per-call overrides
    # -------------------------------------
    def _apply_overrides(self, prompt: str, max_tokens: int | None) -> dict:
        """
        Prepare kwargs for self.ai.query, including token limit.
        """
        kwargs: dict[str, Any] = {}
        if max_tokens is not None:
            kwargs["max_tokens"] = max_tokens
        return kwargs

    # -------------------------------------
    # Helper: update memory breadcrumbs
    # -------------------------------------
    def _update_memory_breadcrumbs(self, text: str) -> None:
        """
        Append a short breadcrumb about what we just asked.
        """
        conn = self._get_conn()
        if not conn:
            return

        try:
            mem = get_memory(conn, key="global") or {}
        except Exception:
            mem = {}

        notes = mem.get("notes") or []
        snippet = text.strip().replace("\n", " ")
        if len(snippet) > 120:
            snippet = snippet[:117] + "..."
        notes.append(f"ASK: {snippet}")
        mem["notes"] = notes[-100:]  # keep last 100
        try:
            import json
            set_memory(conn, mem, key="global")

        except Exception as e:
            self.logger.error(f"_update_memory_breadcrumbs failed: {e}")

    # -------------------------------------
    # Core AI call (CAP-aware + ECM-capable)
    # -------------------------------------
    def query_ai(
        self,
        selected_text: str,
        current_doc_id: int,
        on_success,
        on_link_created,
        prefix: str | None = None,
        sel_start: int | None = None,
        sel_end: int | None = None,
        full_prompt: str | None = None,  # optional ECM-supplied full prompt
    ) -> str:
        """
        Send the selection (or full_prompt) to AI, create a new doc with the response,
        and update the original doc by embedding a green-link-style reference.

        Returns:
            The raw AI reply string (or "" on failure).
        """

        # Ensure prefix always exists
        if prefix is None:
            prefix = ""

        # If the GUI / ECM client has provided a full_prompt (already containing
        # memory, ECM metrics, etc.), we trust it and skip preamble rebuild.
        if full_prompt is not None:
            prompt = full_prompt
            base_prompt = prefix + " " + selected_text if prefix else selected_text
            max_toks = None
            self.logger.info("Received external full_prompt (ECM-enabled caller).")
        else:
            # --- ECM Adaptive Prefix ---
            ecm_prefix = self.ecm_bridge.process_user_input(selected_text)
            ecm2_snapshot = self.get_ecm_snapshot()
            ecm2_preamble = self._build_ecm2_preamble(ecm2_snapshot)
            
            # Build base instruction from prefix + selected text
            base_prompt = (
                f"{prefix} {selected_text}"
                if prefix
                else f"Please expand on this: {selected_text}"
            )

            # Memory preamble
            conn = self._get_conn()
            mem = get_memory(conn, key="global") if conn else {}
            preamble = self._build_memory_preamble(mem, current_doc_id=current_doc_id)
            sections = [part for part in (preamble, ecm2_preamble, ecm_prefix, base_prompt) if part]
            prompt_core = "\n\n".join(sections)

            # Token budget + steering
            max_toks, steer = self._choose_length_policy(base_prompt)
            prompt = f"{prompt_core}\n\n{steer}"

        # ---- AI CALL ----
        try:
            kwargs = self._apply_overrides(prompt, max_toks)
            self.logger.info(
                f"Sending AI prompt (max_tokens={kwargs.get('max_tokens')}): "
                f"{prompt[:200]}..."
            )
            try:
                response = self.ai.query(prompt, **kwargs)
            except TypeError:
                # Fallback if local AI wrapper doesn't accept kwargs
                response = self.ai.query(prompt)
            
            # Filter response through ECM
            filtered_response = self.ecm_bridge.filter_response(response)
            reply = sanitize_ai_reply(filtered_response)
        except Exception as e:
            self.logger.error(f"AI query failed: {e}")
            return ""

        # ---- Create new doc ----
        new_doc_id = self.doc_store.add_document("AI Response", reply)
        self.logger.info(f"Created new document {new_doc_id}")

        # ---- Update original doc with a green-link-style reference ----
        link_offset = -1  # where we inserted the link, if applicable

        try:
            original = self.doc_store.get_document(current_doc_id)
        except Exception:
            original = None

        if original is not None:
            try:
                _id, title, body = original
            except Exception:
                body = ""

            if isinstance(body, str) and selected_text:
                try:
                    # Simple, robust "green link" text:
                    # replace first occurrence of the selection with a linked version.
                    link_text = f"[{selected_text}](doc:{new_doc_id})"
                    idx = body.find(selected_text)
                    if idx != -1:
                        updated = (
                            body[:idx]
                            + link_text
                            + body[idx + len(selected_text) :]
                        )
                        link_offset = idx
                    else:
                        # Selection not found; append a reference at the end.
                        updated = body + f"\n\n[Link to AI response ({new_doc_id})]"
                        link_offset = len(body)

                    if hasattr(self.doc_store, "update_document_body"):
                        self.doc_store.update_document_body(current_doc_id, updated)
                    else:
                        # Legacy signature: update_document(id, new_body)
                        self.doc_store.update_document(current_doc_id, updated)

                    self.logger.info(
                        f"Embedded green-link reference into doc {current_doc_id}"
                    )
                except Exception as e:
                    self.logger.error(
                        f"Failed updating original doc {current_doc_id}: {e}"
                    )

        # Memory breadcrumbs (non-critical)
        try:
            self._update_memory_breadcrumbs(base_prompt)
        except Exception:
            pass

        # Fire callbacks
        try:
            # To preserve compatibility with existing GUIs, we only use the
            # simple signature by default: on_link_created(new_doc_id).
            # The offset-aware form can be enabled later if needed.
            try:
                on_link_created(new_doc_id)
            except TypeError:
                # Older signature: on_link_created(text)
                on_link_created(selected_text)
        except Exception as e:
            self.logger.info(f"on_link_created callback failed (non-fatal): {e}")

        try:
            on_success(new_doc_id)
        except Exception as e:
            self.logger.info(f"on_success callback failed (non-fatal): {e}")

        return reply

    # -------------------------------------
    # File import/export
    # -------------------------------------

    def import_document_from_path(self, path: str) -> int:
        """
        Import a single text file as a new document.
        """
        p = Path(path)
        if not p.exists():
            raise FileNotFoundError(path)
        text = p.read_text(encoding="utf-8", errors="replace")
        title = p.name
        return self.doc_store.add_document(title, text)

    def import_directory(self, dir_path: str) -> int:
        """
        Import all text files from a directory using directory_import helper.
        """
        directory = Path(dir_path)
        if not directory.is_dir():
            raise NotADirectoryError(dir_path)

        count = 0
        for file_path in import_text_files_from_directory(directory):
            try:
                self.import_document_from_path(str(file_path))
                count += 1
            except Exception as e:
                self.logger.error(f"Failed importing {file_path}: {e}")
        return count

    # -------------------------------------
    # Memory preamble builder (inner)
    # -------------------------------------
    def _build_memory_preamble(self, mem: dict, current_doc_id: int | None) -> str:
        """
        Convert the AI memory dict plus current_doc_id into a compact text preamble.
        """
        if not mem:
            return ""
        lines = []
        lines.append("[PiKit Memory]")
        if current_doc_id is not None:
            lines.append(f"- You are currently working in document #{current_doc_id}.")
        notes = mem.get("notes") or []
        if notes:
            lines.append("- Recent notes:")
            for note in notes[-5:]:
                lines.append(f"  * {note}")
        return "\n".join(lines)
