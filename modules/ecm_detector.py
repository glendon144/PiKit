#!/usr/bin/env python3
"""
Lightweight local ECM detector for PiKit.

This provides a small, dependency-free emotional signal source so the ECM bridge
can work even when no external detector repo is present.
"""

from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Any


@dataclass
class _Lexicon:
    reassurance: tuple[str, ...] = (
        "help",
        "scared",
        "afraid",
        "worried",
        "anxious",
        "overwhelmed",
        "lonely",
        "upset",
        "sad",
        "panic",
    )
    clarity: tuple[str, ...] = (
        "how",
        "what",
        "why",
        "steps",
        "exactly",
        "specific",
        "clarify",
        "explain",
        "understand",
        "confused",
    )
    negative: tuple[str, ...] = (
        "bad",
        "wrong",
        "angry",
        "frustrated",
        "annoyed",
        "hate",
        "terrible",
        "awful",
        "stuck",
        "broken",
        "problem",
        "issue",
        "fail",
    )
    positive: tuple[str, ...] = (
        "good",
        "great",
        "happy",
        "love",
        "excellent",
        "wonderful",
        "thanks",
        "thank you",
        "glad",
        "excited",
    )
    confrontational: tuple[str, ...] = (
        "you are wrong",
        "that's wrong",
        "that is wrong",
        "ridiculous",
        "stupid",
        "nonsense",
        "wtf",
        "damn",
    )


class EmotionalContextModule:
    def __init__(self):
        self.lexicon = _Lexicon()

    def update(self, msg: str, ts: float | None = None) -> dict[str, Any]:
        text = (msg or "").strip()
        lowered = text.lower()
        tokens = self._tokens(lowered)

        reassurance = self._score_terms(lowered, tokens, self.lexicon.reassurance)
        clarity = self._score_terms(lowered, tokens, self.lexicon.clarity)
        negative = self._score_terms(lowered, tokens, self.lexicon.negative)
        positive = self._score_terms(lowered, tokens, self.lexicon.positive)
        confront = self._score_terms(lowered, tokens, self.lexicon.confrontational)

        punctuation_heat = min(1.0, (lowered.count("!") + lowered.count("?")) / 4.0)
        caps_heat = self._caps_ratio(text)
        arousal = min(1.0, 0.45 * punctuation_heat + 0.55 * caps_heat + 0.35 * negative)

        valence = positive - negative
        valence = max(-1.0, min(1.0, valence))

        friction = min(
            1.0,
            0.45 * negative + 0.35 * arousal + 0.30 * confront,
        )

        labels: list[str] = []
        if reassurance >= 0.45:
            labels.append("needs_reassurance")
        if clarity >= 0.45:
            labels.append("needs_clarity")
        if confront >= 0.35:
            labels.append("confrontational")
        if valence >= 0.35:
            labels.append("positive")
        elif valence <= -0.35:
            labels.append("negative")

        return {
            "trajectory": {
                "friction_index": round(friction, 3),
            },
            "interaction_needs": {
                "reassurance": round(reassurance, 3),
                "clarity": round(clarity, 3),
            },
            "affect": {
                "valence": round(valence, 3),
                "arousal": round(arousal, 3),
                "labels": labels,
            },
            "meta": {
                "token_count": len(tokens),
            },
        }

    def _tokens(self, text: str) -> list[str]:
        return re.findall(r"[a-z']+", text)

    def _score_terms(
        self,
        lowered: str,
        tokens: list[str],
        terms: tuple[str, ...],
    ) -> float:
        hits = 0
        for term in terms:
            if " " in term:
                hits += lowered.count(term)
            else:
                hits += tokens.count(term)
        if not terms:
            return 0.0
        return min(1.0, hits / max(2.0, len(tokens) / 12.0))

    def _caps_ratio(self, text: str) -> float:
        letters = [ch for ch in text if ch.isalpha()]
        if not letters:
            return 0.0
        uppercase = sum(1 for ch in letters if ch.isupper())
        return min(1.0, uppercase / max(1, len(letters)))
