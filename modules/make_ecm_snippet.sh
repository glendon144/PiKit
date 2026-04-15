cat > /tmp/ecm_snippet.py <<'EOF'
        # --- ECM phrase-level instrumentation (non-invasive) ---
        try:
            if hasattr(self, "ecm_engine") and self.ecm_engine:
                now = time.time()
                text_len = len(selected_text or "")
                burst = min(text_len, 40)  # cap synthetic burst size

                for _ in range(burst):
                    self.ecm_engine.add_key_event(
                        ts=now,
                        key_id="<A>",
                        is_backspace=False,
                    )

                # Phrase boundary marker
                self.ecm_engine.add_key_event(
                    ts=now + 0.3,
                    key_id="<ENT>",
                    is_backspace=False,
                )
        except Exception:
            # ECM is advisory only; never interfere with ASK
            pass
EOF

