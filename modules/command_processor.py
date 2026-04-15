# PiKit Command Processor (updated with memory preamble + truncation + adaptive length)
from __future__ import annotations

import base64
import json
import os
import secrets
import time
from pathlib import Path
from typing import Any, Tuple, Callable

from modules.logger import Logger
from modules.document_store import DocumentStore
from modules.document_transfer import DEFAULT_FLASK_PORT
from modules.directory_import import import_text_files_from_directory
from modules.ai_memory import get_memory, set_memory
from modules.ecm_bridge import ECMBridge
from modules.text_sanitizer import sanitize_ai_reply

# ------------ Config (env-tunable) ------------
SHORT_THRESHOLD_TOKENS = int(os.getenv("PIKIT_SHORT_THRESHOLD_TOKENS", "200"))
SHORT_MAX_TOKENS       = int(os.getenv("PIKIT_SHORT_MAX_TOKENS", "220"))   # quick replies
LONG_MAX_TOKENS        = int(os.getenv("PIKIT_LONG_MAX_TOKENS", "900"))    # detailed replies
# If you simply want to "double tokens", bump LONG_MAX_TOKENS and/or SHORT_MAX_TOKENS above.
# Timeout was already made env-configurable in ai_interface/local_ai_interface earlier.

# Try to import a renderer for binary-as-text; provide a fallback shim if unavailable.
try:
    from modules.renderer import render_binary_as_text  # type: ignore
except Exception:  # pragma: no cover
    try:
        from modules.hypertext_parser import render_binary_as_text  # type: ignore
    except Exception:  # pragma: no cover
        def render_binary_as_text(data_or_path: Any, title: str = "Document") -> str:
            try:
                if isinstance(data_or_path, (bytes, bytearray)):
                    return data_or_path.decode("utf-8", errors="replace")
                if isinstance(data_or_path, str) and os.path.exists(data_or_path):
                    with open(data_or_path, "rb") as f:
                        raw = f.read()
                    return raw.decode("utf-8", errors="replace")
            except Exception:
                pass
            return str(data_or_path)


def _approx_tokens(text: str) -> int:
    """Very rough token estimate (~4 chars/token for English)."""
    if not text:
        return 0
    return max(1, len(text) // 4)


def _normalize_row(row: Any) -> Tuple[Any, str, Any]:
    """Normalize a document row to (id, title, body).
    Supports sqlite3.Row (mapping-like), dict, and sequence (tuple/list).
    """
    # sqlite3.Row behaves like a mapping and supports .keys() and index by column name
    try:
        if hasattr(row, "keys"):
            keys = set(row.keys())
            did = row["id"] if "id" in keys else None
            title = row["title"] if "title" in keys else "Document"
            body = row["body"] if "body" in keys else ""
            return did, (title or "Document"), body
    except Exception:
        pass

    # Dict path
    if isinstance(row, dict):
        return row.get("id"), (row.get("title") or "Document"), row.get("body")

    # Sequence path (tuple/list/sqlite3.Row via index access)
    try:
        if not isinstance(row, (str, bytes, bytearray)) and hasattr(row, "__getitem__"):
            did = row[0] if len(row) > 0 else None
            title = row[1] if len(row) > 1 else "Document"
            body = row[2] if len(row) > 2 else ""
            return did, (title or "Document"), body
    except Exception:
        pass

    # Fallback: treat entire row as body
    return None, "Document", row


class CommandProcessor:
    def __init__(self, store: DocumentStore, ai_interface, logger: Logger | None = None):
        self.doc_store = store
        self.ai = ai_interface
        self.logger = logger if logger else Logger()
        self.dream_handler: Callable[..., None] | None = None
        self.ecm_bridge = ECMBridge()
        self.ecm_engine = self._init_ecm_engine()

    def set_dream_handler(self, handler: Callable[..., None] | None) -> None:
        """Register a callback for lightweight Dream-mode event logging."""
        self.dream_handler = handler

    def _emit_dream_event(self, event_type: str, content: str, **metadata) -> None:
        if not self.dream_handler:
            return
        try:
            self.dream_handler(event_type=event_type, content=content, metadata=metadata)
        except TypeError:
            try:
                self.dream_handler(event_type, content, metadata)
            except Exception as e:
                self.logger.info(f"Dream handler failed (non-fatal): {e}")
        except Exception as e:
            self.logger.info(f"Dream handler failed (non-fatal): {e}")

    def _init_ecm_engine(self):
        """Best-effort ECM2 loader; text preamp still works if this fails."""
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

    # --------------- Memory helpers ---------------

    def _get_conn(self):
        """Return the SQLite connection from the document store, if available."""
        return getattr(self.doc_store, "conn", None)

    def _build_memory_preamble(self, mem: dict, current_doc_id: int | None = None) -> str:
        """Construct a small instruction block from memory to steer the model."""
        if not isinstance(mem, dict):
            return ""
        persona = mem.get("persona")
        style = mem.get("style")
        rules = mem.get("rules", [])
        parts: list[str] = []
        if persona:
            parts.append(f"Persona: {persona}")
        if style:
            parts.append(f"Style: {style}")
        if rules:
            parts.append("Rules: " + "; ".join(rules))
        return "\n".join(parts).strip()

    def _update_memory_breadcrumbs(self, prompt: str) -> None:
        """Record last-used time and a short rolling log of prompts."""
        conn = self._get_conn()
        if not conn:
            return
        try:
            mem = get_memory(conn, key="global")
            if not isinstance(mem, dict):
                mem = {}
            mem.setdefault("recent_prompts", [])
            mem["recent_prompts"] = (mem["recent_prompts"] + [prompt])[-20:]
            mem["last_used"] = int(time.time())
            set_memory(conn, mem, key="global")
        except Exception as e:
            # Non-fatal; keep the AI flow working even if memory write fails
            self.logger.info(f"Non-fatal: failed to update ai_memory: {e}")

    # --------------- Public API ---------------

    def set_api_key(self, api_key: str) -> None:
        try:
            self.ai.set_api_key(api_key)
            self.logger.info("API key successfully set in AI interface")
        except Exception as e:
            self.logger.error(f"Failed to set API key: {e}")

    def get_context_menu_actions(self) -> dict:
        return {
            "Import CSV": self.doc_store.import_csv,
            "Export CSV": self.doc_store.export_csv,
        }

    def _share_dir(self) -> Path:
        path = Path("exported_docs") / "_shares"
        path.mkdir(parents=True, exist_ok=True)
        return path

    def _build_shared_payload(self, doc_id: int) -> dict[str, Any]:
        row = self.doc_store.get_document(doc_id)
        if not row:
            raise ValueError(f"Document {doc_id} not found.")

        actual_id, title, body = _normalize_row(row)
        if actual_id is None:
            actual_id = doc_id

        payload: dict[str, Any] = {
            "doc_id": int(actual_id),
            "title": title or f"Document {actual_id}",
            "shared_at": int(time.time()),
        }
        if isinstance(body, (bytes, bytearray)):
            payload["body_encoding"] = "base64"
            payload["body"] = base64.b64encode(bytes(body)).decode("ascii")
        else:
            payload["body_encoding"] = "text"
            payload["body"] = "" if body is None else str(body)
        return payload

    def send_document(
        self,
        doc_id: int,
        recipient_host: str,
        recipient_port: int,
        sender_host: str,
        sender_name: str | None = None,
        flask_port: int = DEFAULT_FLASK_PORT,
        share_scheme: str = "https",
    ) -> dict[str, Any]:
        if not recipient_host.strip():
            raise ValueError("Recipient host is required.")
        if not sender_host.strip():
            raise ValueError("Sender host is required.")

        share_id = secrets.token_urlsafe(18)
        shared_payload = self._build_shared_payload(int(doc_id))
        shared_payload["share_id"] = share_id

        share_file = self._share_dir() / f"{share_id}.json"
        share_file.write_text(
            json.dumps(shared_payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

        sender_label = sender_name or os.getenv("USER") or "PiKit user"
        return {
            "kind": "document_share_invite",
            "share_id": share_id,
            "doc_id": shared_payload["doc_id"],
            "doc_title": shared_payload["title"],
            "sender_name": sender_label,
            "sender_host": sender_host,
            "sender_flask_port": int(flask_port),
            "share_scheme": share_scheme,
            "recipient_host": recipient_host.strip(),
            "recipient_port": int(recipient_port),
            "share_url": f"{share_scheme}://{sender_host}:{int(flask_port)}/share/{share_id}",
            "sent_at": int(time.time()),
        }

    def import_shared_document(self, shared_payload: dict[str, Any]) -> int:
        title = str(shared_payload.get("title") or "Shared Document")
        encoding = str(shared_payload.get("body_encoding") or "text")
        raw_body = shared_payload.get("body")

        if encoding == "base64":
            if not isinstance(raw_body, str):
                raise ValueError("Shared binary document payload is invalid.")
            body = base64.b64decode(raw_body.encode("ascii"))
        else:
            body = "" if raw_body is None else str(raw_body)

        return self.doc_store.add_document(title, body)

    # ----------------- Core prompting -----------------

    def _choose_length_policy(self, prompt_text: str) -> tuple[int, str]:
        """Return (max_tokens, steering_instructions) based on input size."""
        n = _approx_tokens(prompt_text)
        if n < SHORT_THRESHOLD_TOKENS:
            steer = "Output: be thorough and eloquent"
            return SHORT_MAX_TOKENS, steer
        else:
            steer = "Output: thorough and structured; use short sections and examples where useful."
            return LONG_MAX_TOKENS, steer

    def _apply_overrides(self, prompt: str, max_tokens: int):
        """Try to send max_tokens to the AI interface if supported; otherwise return prompt only."""
        # Many of your local interfaces accept overrides= dict
        try:
            return {"overrides": {"max_tokens": max_tokens}}
        except Exception:
            return {}

    def ask_question(self, prompt: str) -> str | None:
        """Send a standalone prompt to AI, applying memory preamble, adaptive length, and truncation."""
        try:
            conn = self._get_conn()
            mem = get_memory(conn, key="global") if conn else {}
            preamble = self._build_memory_preamble(mem)

            # Adaptive length
            max_toks, steer = self._choose_length_policy(prompt)
            full_prompt_core = (preamble + "\n\n" + prompt) if preamble else prompt
            full_prompt = f"{full_prompt_core}\n\n{steer}"

            self.logger.info(f"Sending standalone prompt to AI (max_tokens={max_toks}): {full_prompt}")
            kwargs = self._apply_overrides(full_prompt, max_toks)
            try:
                response = self.ai.query(full_prompt, **kwargs)
            except TypeError:
                # Fallback if interface doesn't accept overrides kwarg
                response = self.ai.query(full_prompt)

            response = sanitize_ai_reply(response)
            self.logger.info("AI response received successfully")
            self._update_memory_breadcrumbs(prompt)
            self._emit_dream_event(
                "ask_question",
                prompt,
                response_preview=response[:240],
            )
            return response
        except Exception as e:
            self.logger.error(f"AI query failed: {e}")
            return None

    def query_ai(
        self,
        selected_text: str,
        current_doc_id: int,
        on_success,
        on_link_created,
        prefix: str | None = None,
        sel_start: int | None = None,
        sel_end: int | None = None,
    ) -> None:
        """
        Send the selection to AI, create a new doc with the response, and optionally embed
        a green link back into the source doc (text bodies only). Also applies memory preamble,
        adaptive length, and truncates likely-incomplete sentences.
        """
        # Compose the base prompt
        base_prompt = f"{prefix} {selected_text}" if prefix else f"Please expand on this: {selected_text}"

        ecm_prefix = self.ecm_bridge.process_user_input(selected_text)
        ecm2_snapshot = self.get_ecm_snapshot()
        ecm2_preamble = self._build_ecm2_preamble(ecm2_snapshot)

        # Memory preamble
        conn = self._get_conn()
        mem = get_memory(conn, key="global") if conn else {}
        preamble = self._build_memory_preamble(mem, current_doc_id=current_doc_id)
        sections = [part for part in (preamble, ecm2_preamble, ecm_prefix, base_prompt) if part]
        prompt_core = "\n\n".join(sections)

        # Adaptive length
        max_toks, steer = self._choose_length_policy(base_prompt)
        prompt = f"{prompt_core}\n\n{steer}"

        self.logger.info(f"Sending prompt: max_tokens={max_toks} | {prompt}")
        self._emit_dream_event(
            "ask_request",
            base_prompt,
            current_doc_id=current_doc_id,
            prefix=prefix or "",
        )

        # Call AI
        try:
            kwargs = self._apply_overrides(prompt, max_toks)
            try:
                reply = self.ai.query(prompt, **kwargs)
            except TypeError:
                reply = self.ai.query(prompt)
            reply = sanitize_ai_reply(self.ecm_bridge.filter_response(reply))
        except Exception as e:
            self.logger.error(f"AI query failed: {e}")
            return

        self.logger.info("AI query successful")

        # Create the AI response document
        new_doc_id = self.doc_store.add_document("AI Response", reply)
        self.logger.info(f"Created new document {new_doc_id}")
        self._emit_dream_event(
            "ask_response",
            reply,
            current_doc_id=current_doc_id,
            new_doc_id=new_doc_id,
        )

        # Try to embed a green link in the original text document
        try:
            original = self.doc_store.get_document(current_doc_id)
        except Exception as e:
            original = None
            self.logger.error(f"Failed to load original doc {current_doc_id}: {e}")

        if original is not None:
            try:
                _, _title, body = _normalize_row(original)
            except Exception:
                body = ""

            if isinstance(body, str) and selected_text:
                link_md = f"[{selected_text}](doc:{new_doc_id})"
                updated: str | None = None

                # If explicit offsets are provided and valid, use them
                if (
                    isinstance(sel_start, int)
                    and isinstance(sel_end, int)
                    and 0 <= sel_start < sel_end <= len(body)
                ):
                    updated = body[:sel_start] + link_md + body[sel_end:]
                    self.logger.info(f"Embedded link at offsets {sel_start}-{sel_end}")
                else:
                    # Fallback: first occurrence replacement
                    if selected_text in body:
                        updated = body.replace(selected_text, link_md, 1)
                        self.logger.info("Embedded link by substring replace")
                    else:
                        self.logger.info("Selected text not found; original unchanged")

                if updated is not None and updated != body:
                    try:
                        if hasattr(self.doc_store, "update_document_body"):
                            self.doc_store.update_document_body(current_doc_id, updated)
                        else:
                            # Some stores expose a generic update_document(id, body)
                            self.doc_store.update_document(current_doc_id, updated)  # type: ignore
                    except Exception as e:
                        self.logger.error(f"Failed updating original doc {current_doc_id}: {e}")
                    else:
                        self._emit_dream_event(
                            "link_embed",
                            selected_text,
                            current_doc_id=current_doc_id,
                            new_doc_id=new_doc_id,
                        )
            else:
                # Skip binary or missing bodies
                if isinstance(body, (bytes, bytearray)):
                    self.logger.info("Original doc is binary; skipping in-place link embed.")
        else:
            self.logger.error(f"Original document {current_doc_id} not found")

        # Update memory breadcrumbs (non-fatal on error)
        try:
            self._update_memory_breadcrumbs(base_prompt)
        except Exception:
            pass

        # Fire UI callbacks
        try:
            on_link_created(new_doc_id)
        except Exception as e:
            self.logger.info(f"on_link_created callback failed (non-fatal): {e}")
        try:
            on_success(new_doc_id)
        except Exception as e:
            self.logger.info(f"on_success callback failed (non-fatal): {e}")

    # --------------- External file operations ---------------

    def import_document_from_path(self, path: str) -> int:
        """Import a file from *path* and return new document ID."""
        p = Path(path)
        title = p.stem
        try:
            text = p.read_text(encoding="utf-8")
            return self.doc_store.add_document(title, text)
        except UnicodeDecodeError:
            data = p.read_bytes()  # store as SQLite BLOB
            return self.doc_store.add_document(title, data)

    def export_document_to_path(self, doc_id: int, path: str) -> None:
        """Export document *doc_id* to filesystem path."""
        row = self.doc_store.get_document(doc_id)

        if hasattr(row, "keys"):  # sqlite3.Row with mapping behavior
            body = row["body"] if row else ""
        elif isinstance(row, dict):
            body = row.get("body")
        else:
            body = row[2] if row and len(row) > 2 else ""

        p = Path(path)
        if isinstance(body, (bytes, bytearray)):
            p.write_bytes(bytes(body))
        else:
            p.write_text("" if body is None else str(body), encoding="utf-8")

    # --------------- Render helpers ---------------

    def get_strings_content(self, doc_id: int) -> str:
        """Return a text rendering of the document suitable for display/export."""
        try:
            row = self.doc_store.get_document(doc_id)
        except Exception:
            row = None

        if not row:
            return "[ERROR] Document not found."

        _id, title, body = _normalize_row(row)

        # If body looks like a filesystem path and exists, prefer that
        if isinstance(body, str) and os.path.exists(body):
            try:
                return render_binary_as_text(body, title)
            except Exception:
                pass

        # If it's bytes/bytearray, convert via renderer
        if isinstance(body, (bytes, bytearray)):
            return render_binary_as_text(body, title)

        # Else, return text as-is
        return str(body or "")


    def distill_text(
        self,
        source_text: str,
        current_doc_id: int | None,
        on_success,
        on_link_created,
        source_title: str | None = None,
        selected_text: str | None = None,
        sel_start: int | None = None,
        sel_end: int | None = None,
    ) -> None:
        """
        Distill source text into a compact execution brief, create a new document,
        and optionally embed a green link back into the source document.
        """
        if not source_text or not str(source_text).strip():
            self.logger.error("distill_text called with empty source_text")
            return

        source_title = source_title or "Untitled"
        selection_label = (selected_text or "").strip()

        distill_prompt = f"""Distill this material into a clean working brief that preserves both technical meaning and creative intention.

Keep:
- the real goal
- important decisions already made
- essential context discovered during exploration
- constraints and exclusions
- style / tone preferences
- unresolved issues that still matter

Discard:
- repetition
- dead ends
- exploratory chatter that no longer affects the task
- redundant explanation

Output exactly in this format:

PROJECT:
GOAL:
ESSENTIAL CONTEXT:
DECISIONS MADE:
CONSTRAINTS:
STYLE / TONE:
OPEN ISSUES:
FINAL EXECUTION PROMPT:
RISKS OF MISREADING:

Source title: {source_title}

Source material:
{source_text}
"""

        conn = self._get_conn()
        mem = get_memory(conn, key="global") if conn else {}
        preamble = self._build_memory_preamble(mem, current_doc_id=current_doc_id)
        prompt_core = (preamble + "\n\n" + distill_prompt) if preamble else distill_prompt

        max_toks, steer = self._choose_length_policy(source_text)
        prompt = f"{prompt_core}\n\nOutput: be concise, concrete, and structured."

        self.logger.info(f"Sending DISTILL prompt: max_tokens={max_toks}")
        self._emit_dream_event(
            "distill_request",
            source_text[:1000],
            current_doc_id=current_doc_id,
            source_title=source_title,
        )

        try:
            kwargs = self._apply_overrides(prompt, max_toks)
            try:
                reply = self.ai.query(prompt, **kwargs)
            except TypeError:
                reply = self.ai.query(prompt)
            reply = sanitize_ai_reply(reply)
        except Exception as e:
            self.logger.error(f"DISTILL AI query failed: {e}")
            return

        new_title = f"Distilled Brief: {source_title}"
        new_body = f"Distilled from: {source_title}\nPurpose: execution bridge\n\n{reply}"
        new_doc_id = self.doc_store.add_document(new_title, new_body)

        self.logger.info(f"Created DISTILL document {new_doc_id}")
        self._emit_dream_event(
            "distill_response",
            reply[:1000],
            current_doc_id=current_doc_id,
            new_doc_id=new_doc_id,
        )

        try:
            original = self.doc_store.get_document(current_doc_id) if current_doc_id is not None else None
        except Exception as e:
            original = None
            self.logger.error(f"Failed to load original doc {current_doc_id}: {e}")

        if original is not None:
            try:
                _, _title, body = _normalize_row(original)
            except Exception:
                body = ""

            if isinstance(body, str):
                anchor = selection_label or f"Distilled Brief ({new_doc_id})"
                link_md = f"[{anchor}](doc:{new_doc_id})"
                updated = None

                if (
                    selection_label
                    and isinstance(sel_start, int)
                    and isinstance(sel_end, int)
                    and 0 <= sel_start < sel_end <= len(body)
                ):
                    updated = body[:sel_start] + link_md + body[sel_end:]
                    self.logger.info(f"Embedded DISTILL link at offsets {sel_start}-{sel_end}")
                elif selection_label and selection_label in body:
                    updated = body.replace(selection_label, link_md, 1)
                    self.logger.info("Embedded DISTILL link by substring replace")
                elif not selection_label:
                    suffix = "\n\n" if body and not body.endswith("\n") else "\n"
                    updated = body + suffix + link_md + "\n"
                    self.logger.info("Appended DISTILL link to end of source document")

                if updated is not None:
                    try:
                        if hasattr(self.doc_store, "update_document_body"):
                            self.doc_store.update_document_body(current_doc_id, updated)
                        else:
                            self.doc_store.update_document(current_doc_id, updated)  # type: ignore[arg-type]
                    except Exception as e:
                        self.logger.error(f"Failed updating original doc {current_doc_id}: {e}")

        try:
            self._update_memory_breadcrumbs(f"DISTILL: {source_title}")
        except Exception:
            pass

        try:
            on_link_created(new_doc_id)
        except Exception as e:
            self.logger.info(f"on_link_created callback failed (non-fatal): {e}")

        try:
            on_success(new_doc_id)
        except Exception as e:
            self.logger.info(f"on_success callback failed (non-fatal): {e}")


    # --------------- Bulk imports ---------------

    def import_opml_from_path(self, path: str) -> int:
        """Import an OPML/XML file from *path* and return new document ID."""
        content = Path(path).read_text(encoding="utf-8", errors="replace")
        title = Path(path).stem
        return self.doc_store.add_document(title, content)
     # --- OPML: helpers for string / URL / crawler -------------------------------
import os
import tempfile

def import_opml_from_string(self, xml_text: str, source: str = "") -> int:
    """
    Import an OPML document provided as a string.
    Bridges to import_opml_from_path by writing to a temp file.
    Returns: new document id.
    """
    # choose a safe temp dir under storage if available
    base_tmp = getattr(self, "storage_dir", None)
    if not base_tmp:
        base_tmp = os.path.join(os.getcwd(), "storage")
    os.makedirs(base_tmp, exist_ok=True)

    with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", prefix="opml_", suffix=".opml",
                                     dir=base_tmp, delete=False) as tf:
        tf.write(xml_text)
        tmp_path = tf.name

    # Optionally you could record 'source' somewhere if your importer supports it
    try:
        new_id = self.import_opml_from_path(tmp_path)
        return new_id
    finally:
        # Keep the temp file if your importer needs it later; otherwise uncomment:
        # try: os.remove(tmp_path)
        # except Exception: pass
        pass


def import_opml_from_url(self, url: str, timeout: int = 15) -> int:
    """
    Fetch an OPML from URL and import it.
    """
    try:
        import requests
        r = requests.get(url, timeout=timeout, headers={"User-Agent": "PiKit/OPML-Importer"})
        r.raise_for_status()
        xml_text = r.text
    except Exception as e:
        raise RuntimeError(f"Failed to fetch OPML from URL: {e}")
    return self.import_opml_from_string(xml_text, source=url)


def crawl_opml_and_import(self, start: str, max_depth: int = 2) -> list[int]:
    """
    Crawl an OPML seed (URL or local path), gather linked OPMLs, and import each.
    Returns the list of new document IDs.
    """
    try:
        from modules.opml_crawler_adapter import crawl_opml
    except Exception as e:
        raise RuntimeError(f"OPML crawler not available: {e}")

    results = crawl_opml(start, max_depth=max_depth)
    new_ids: list[int] = []
    for src, xml_text in results:
        try:
            new_id = self.import_opml_from_string(xml_text, source=src)
            new_ids.append(new_id)
        except Exception as e:
            print(f"[opml] import failed for {src}: {e}")
    return new_ids
 

    def import_directory(self, directory: str) -> None:
        """Bulk-import text files from a directory."""
        import_text_files_from_directory(self.doc_store, directory)
