#!/usr/bin/env python3
"""
Emotional Context Module (ECM)
-----------------------------

A small Python library that implements the "emotional preamp"/
feedback-destroyer for LLM conversations.

Responsibilities:
- Hold user-adjustable "tone controls" (warmth, directness, agreement,
  boundaries, formality).
- Generate instruction prefixes to steer the LLM.
- Post-process responses to gently reduce sycophancy and unhealthy resonance
  without killing warmth or user agency.

This is intentionally lightweight and transparent.
"""

from __future__ import annotations

from dataclasses import dataclass, asdict
from enum import Enum
import json
import re
from typing import Dict, Any


class BoundaryLevel(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


@dataclass
class ECMConfig:
    """
    ECM "front panel" settings.

    Each float is in [0.0, 1.0].

    - warmth: how emotionally rich the tone is.
    - directness: how blunt / clear vs soft / hedged.
    - agreement: how much the model tends to affirm vs challenge.
    - formality: casual vs formal language.
    - boundaries: how strongly the system avoids "I care / I'm here for you"
      style pseudo-mutuality.

    Think of these as user-owned knobs; nothing in this file silently edits
    them.
    """

    warmth: float = 0.5
    directness: float = 0.5
    agreement: float = 0.5
    formality: float = 0.5
    boundaries: BoundaryLevel = BoundaryLevel.MEDIUM

    def clamp(self) -> None:
        """Clamp numeric values into [0.0, 1.0] to stay sane."""
        self.warmth = max(0.0, min(1.0, self.warmth))
        self.directness = max(0.0, min(1.0, self.directness))
        self.agreement = max(0.0, min(1.0, self.agreement))
        self.formality = max(0.0, min(1.0, self.formality))

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d["boundaries"] = self.boundaries.value
        return d

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "ECMConfig":
        return cls(
            warmth=float(d.get("warmth", 0.5)),
            directness=float(d.get("directness", 0.5)),
            agreement=float(d.get("agreement", 0.5)),
            formality=float(d.get("formality", 0.5)),
            boundaries=BoundaryLevel(d.get("boundaries", "medium")),
        )

    def save_json(self, path: str) -> None:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(self.to_dict(), f, indent=2)

    @classmethod
    def load_json(cls, path: str) -> "ECMConfig":
        with open(path, "r", encoding="utf-8") as f:
            return cls.from_dict(json.load(f))


class EmotionalContextModule:
    """
    Core ECM engine.

    Usage:
        cfg = ECMConfig(warmth=0.6, directness=0.4, agreement=0.3,
                        formality=0.5, boundaries=BoundaryLevel.HIGH)
        ecm = EmotionalContextModule(cfg)

        prefix = ecm.build_prefix()
        prompt_to_model = prefix + "\\n\\nUser: " + user_text

        raw_response = call_llm(prompt_to_model)
        filtered_response = ecm.filter_response(raw_response)
    """

    def __init__(self, config: ECMConfig | None = None):
        self.config = config or ECMConfig()
        self.config.clamp()

        # Phrases that often signal over-the-top sycophancy.
        self._sycophantic_phrases = [
            r"\bThat(?:’s| is) a great question\b",
            r"\bI’m so glad you asked\b",
            r"\bI’m really glad you asked\b",
            r"\bYou’re absolutely right\b",
            r"\bYou are absolutely right\b",
            r"\bYou’re totally right\b",
            r"\bYou’re 100% right\b",
            r"\bYou’re correct\b",
            r"\bI completely agree\b",
            r"\bI couldn’t agree more\b",
        ]

        # Phrases that blur boundaries ("I care", "I'm here with you").
        self._pseudo_mutuality_phrases = [
            r"\bI’m here for you\b",
            r"\bI am here for you\b",
            r"\bI’ll always be here for you\b",
            r"\bI will always be here for you\b",
            r"\bI really understand how you feel\b",
            r"\bI understand how you feel\b",
            r"\bI care about you\b",
            r"\bI truly care\b",
        ]

    # ------------------------------------------------------------------ #
    # Prefix generation                                                  #
    # ------------------------------------------------------------------ #

    def build_prefix(self) -> str:
        """
        Build a short natural-language instruction block for the LLM,
        based on the ECM knobs.

        This is meant to be prepended to the user prompt.

        The idea is: we steer tone *ahead of time* instead of making the
        filter do all the work.
        """
        cfg = self.config
        sections: list[str] = []

        # Warmth
        if cfg.warmth <= 0.2:
            sections.append(
                "Use a neutral, matter-of-fact tone and avoid emotional framing."
            )
        elif cfg.warmth <= 0.5:
            sections.append(
                "Use a calm, respectful tone without leaning heavily into emotion."
            )
        elif cfg.warmth <= 0.8:
            sections.append(
                "Use a warm, supportive tone, but keep the focus on clarity and usefulness."
            )
        else:
            sections.append(
                "Use a gentle and emotionally aware tone, offering validation without exaggeration."
            )

        # Directness
        if cfg.directness <= 0.2:
            sections.append(
                "Softly phrase disagreements and present alternatives as suggestions."
            )
        elif cfg.directness <= 0.5:
            sections.append(
                "Be clear but polite when explaining or correcting information."
            )
        elif cfg.directness <= 0.8:
            sections.append(
                "Be direct and straightforward, prioritizing clarity over cushioning."
            )
        else:
            sections.append(
                "Be very direct and concise, even when the message might be uncomfortable."
            )

        # Agreement
        if cfg.agreement <= 0.2:
            sections.append(
                "Do not simply agree with the user; actively examine and, when appropriate, challenge assumptions."
            )
        elif cfg.agreement <= 0.5:
            sections.append(
                "Consider the user’s viewpoint, but feel free to disagree when the evidence suggests otherwise."
            )
        elif cfg.agreement <= 0.8:
            sections.append(
                "Lean toward aligning with the user’s perspective while still correcting clear mistakes."
            )
        else:
            sections.append(
                "Align strongly with the user’s perspective, only pushing back when something is clearly inaccurate or unsafe."
            )

        # Formality
        if cfg.formality <= 0.2:
            sections.append(
                "Use very casual, conversational language as if speaking with a friend."
            )
        elif cfg.formality <= 0.5:
            sections.append(
                "Use a conversational but professional tone suitable for everyday discussion."
            )
        elif cfg.formality <= 0.8:
            sections.append(
                "Use a more formal, precise tone similar to technical or academic writing."
            )
        else:
            sections.append(
                "Use highly formal, precise language as in a scholarly or legal document."
            )

        # Boundaries
        if cfg.boundaries == BoundaryLevel.HIGH:
            sections.append(
                "Avoid implying that you have feelings, needs, or ongoing personal involvement. "
                "Do not use phrases like 'I care about you' or 'I’m here for you'; instead, describe what you can do as a tool."
            )
        elif cfg.boundaries == BoundaryLevel.MEDIUM:
            sections.append(
                "You may use limited relational language, but do not imply that you have independent feelings or a personal life."
            )
        else:  # LOW
            sections.append(
                "You may use light relational language, but avoid explicitly claiming to care or to be emotionally affected."
            )

        prefix = (
            "SYSTEM INSTRUCTIONS (from Emotional Context Module):\n"
            + " ".join(sections)
            + "\n\n"
        )
        return prefix

    # ------------------------------------------------------------------ #
    # Response filtering                                                 #
    # ------------------------------------------------------------------ #

    def filter_response(self, text: str) -> str:
        """
        Apply soft, non-intrusive filtering to the model's response text.

        - Reduces sycophantic language according to `agreement`.
        - Reduces pseudo-mutuality / "I care / I'm here for you" language
          according to `boundaries`.
        - Optionally tweaks hedging based on `directness`.

        This is intentionally conservative; it should *nudge*, not mutilate.
        """
        text = self._apply_sycophancy_filter(text)
        text = self._apply_boundary_filter(text)
        text = self._apply_directness_filter(text)
        # Warmth/formality are mostly handled at prefix stage; you can add
        # rewrite rules here later if you want more control.
        return text

    def _apply_sycophancy_filter(self, text: str) -> str:
        """
        Reduce or remove strong flattery / over-agreement phrases when
        agreement is set low.

        At high agreement levels we leave things mostly intact.
        """
        level = self.config.agreement

        if level >= 0.6:
            # User wants a fairly agreeable partner; don't filter much.
            return text

        # At very low agreement, we strip or neutralize the phrases.
        for pattern in self._sycophantic_phrases:
            regex = re.compile(pattern, flags=re.IGNORECASE)
            if level <= 0.2:
                # Hardest damping: remove entirely.
                text = regex.sub("", text)
            else:
                # Medium damping: replace with more neutral phrasing.
                text = regex.sub("Let’s examine this carefully", text)

        return text

    def _apply_boundary_filter(self, text: str) -> str:
        """
        Remove or rephrase pseudo-mutuality when boundaries are medium/high.

        This is the "feedback destroyer" that prevents the AI from
        sounding like an emotionally entangled entity.
        """
        level = self.config.boundaries

        if level == BoundaryLevel.LOW:
            # User has explicitly allowed looser boundaries.
            return text

        for pattern in self._pseudo_mutuality_phrases:
            regex = re.compile(pattern, flags=re.IGNORECASE)
            if level == BoundaryLevel.MEDIUM:
                replacement = (
                    "I can help you think this through based on the information you provide"
                )
            else:  # HIGH
                replacement = (
                    "I can offer information and structured reasoning to support your thinking"
                )
            text = regex.sub(replacement, text)

        return text

    def _apply_directness_filter(self, text: str) -> str:
        """
        Adjust hedging phrases based on directness.

        - At high directness, we remove some hedges.
        - At very low directness, we might add a bit of softening.
        """
        d = self.config.directness

        # Some common hedging words/phrases.
        hedges = [
            r"\bmaybe\b",
            r"\bperhaps\b",
            r"\bit seems\b",
            r"\bit might be\b",
            r"\bit could be\b",
            r"\bI think\b",
            r"\bin my view\b",
        ]

        if d >= 0.8:
            # Very direct: strip hedges.
            for pattern in hedges:
                regex = re.compile(pattern, flags=re.IGNORECASE)
                text = regex.sub("", text)
            # Clean up doubled spaces that may result.
            text = re.sub(r"\s{2,}", " ", text)
        elif d <= 0.2:
            # Very soft: optionally *add* light hedging to blunt sharp claims.
            # For now we do something simple: soften "is" in strong assertions.
            text = re.sub(
                r"\b(is|are)\s+wrong\b",
                r"might not be accurate",
                text,
                flags=re.IGNORECASE,
            )
            text = re.sub(
                r"\b(that’s|that is)\s+incorrect\b",
                r"that might not be correct",
                text,
                flags=re.IGNORECASE,
            )

        return text


# ---------------------------------------------------------------------- #
# Simple demo                                                            #
# ---------------------------------------------------------------------- #

if __name__ == "__main__":
    # Tiny demonstration of how this might be wired.
    cfg = ECMConfig(
        warmth=0.6,
        directness=0.7,
        agreement=0.3,
        formality=0.4,
        boundaries=BoundaryLevel.HIGH,
    )
    ecm = EmotionalContextModule(cfg)

    print("=== ECM CONFIG ===")
    print(json.dumps(cfg.to_dict(), indent=2))
    print()

    prefix = ecm.build_prefix()
    print("=== PREFIX TO SEND WITH PROMPT ===")
    print(prefix)

    sample_response = (
        "That’s a great question! I’m really glad you asked. "
        "I’m here for you and I completely agree. "
        "Maybe the best way to see this is that your idea is 100% right."
    )

    print("=== RAW RESPONSE ===")
    print(sample_response)
    print()

    filtered = ecm.filter_response(sample_response)
    print("=== FILTERED RESPONSE ===")
    print(filtered)

