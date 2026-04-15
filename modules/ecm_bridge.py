#!/usr/bin/env python3
"""
ECM Bridge: Connects Detection ECM (text-based) with Preamp ECM (tone-based).
"""

from __future__ import annotations
import os
import sys
from pathlib import Path

# Ensure we can import from current directory
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

# Import Detection ECM (The one ChatGPT implemented based on my design)
# We assume the file is copied or symlinked into modules/ or available in path.
try:
    from ecm_detector import EmotionalContextModule as Detector
except ImportError:
    # Fallback if it's named ecm.py in the src directory
    # For this bridge to work, we'll assume the user has placed the detection ecm 
    # as 'ecm_detector.py' to avoid name collision with 'ecm.py' (the preamp).
    # Since we have /home/gross/src/ecm/ecm.py, let's assume we can import it.
    sys.path.append("/home/gross/src/ecm")
    try:
        from ecm import EmotionalContextModule as Detector
    except ImportError:
        # Last resort: mock if not found during dev
        class Detector:
            def update(self, msg, ts=None): return {}

# Import Preamp ECM (The existing one in PiKit)
from ecm import EmotionalContextModule as Preamp, ECMConfig, BoundaryLevel

class ECMBridge:
    def __init__(self, settings_path: str | None = None):
        self.settings_path = Path(settings_path) if settings_path else (
            Path(__file__).resolve().parent.parent / "storage" / "ecm_settings.json"
        )
        self.detector = Detector()
        self.base_config = self._load_base_config()
        self.config = ECMConfig.from_dict(self.base_config.to_dict())
        self.preamp = Preamp(self.config)
        self.last_metadata = {}

    def _load_base_config(self) -> ECMConfig:
        try:
            if self.settings_path.exists():
                return ECMConfig.load_json(str(self.settings_path))
        except Exception:
            pass

        cfg = ECMConfig()
        try:
            self.settings_path.parent.mkdir(parents=True, exist_ok=True)
            cfg.save_json(str(self.settings_path))
        except Exception:
            pass
        return cfg

    def process_user_input(self, text: str) -> str:
        """
        1. Detect emotion from text.
        2. Update Preamp config based on detection.
        3. Return a system prefix.
        """
        self.base_config = self._load_base_config()
        self.config = ECMConfig.from_dict(self.base_config.to_dict())

        # Update Detector
        self.last_metadata = self.detector.update(text)
        
        # Extract signals
        friction = self.last_metadata.get("trajectory", {}).get("friction_index", 0.5)
        needs = self.last_metadata.get("interaction_needs", {})
        affect = self.last_metadata.get("affect", {})
        valence = affect.get("valence", 0.0)
        arousal = affect.get("arousal", 0.0)

        # --- Adaptive Logic: Mapping Detection to Preamp Knobs ---

        # 1. Warmth: High friction or high reassurance need -> More warmth
        if friction > 0.6 or needs.get("reassurance", 0) > 0.7:
            self.config.warmth = max(self.config.warmth, 0.8)
        elif valence > 0.4: # User is happy
            self.config.warmth = max(self.config.warmth, 0.6)

        # 2. Directness: High confusion or high clarity need -> High directness
        # But if friction is very high, soften it slightly.
        if needs.get("clarity", 0) > 0.7:
            self.config.directness = max(self.config.directness, 0.8)
        elif friction > 0.8:
            self.config.directness = min(self.config.directness, 0.3)

        # 3. Agreement: High confrontational signal -> Lower agreement (stay firm but calm)
        if "confrontational" in affect.get("labels", []):
            self.config.agreement = min(self.config.agreement, 0.2)
        elif valence < -0.4: # High frustration
            self.config.agreement = max(self.config.agreement, 0.7) # Be more agreeable to de-escalate

        # 4. Formality: High clarity need -> High formality
        if needs.get("clarity", 0) > 0.8:
            self.config.formality = max(self.config.formality, 0.8)
        elif valence > 0.5 and arousal < 0.4: # Relaxed happy user
            self.config.formality = min(self.config.formality, 0.3)

        # 5. Boundaries: High friction or high arousal -> High boundaries
        if friction > 0.7 or arousal > 0.8:
            self.config.boundaries = BoundaryLevel.HIGH
        elif self.config.boundaries == BoundaryLevel.HIGH:
            self.config.boundaries = BoundaryLevel.HIGH

        self.config.clamp()
        
        # Update preamp with new config
        self.preamp.config = self.config
        
        return self.preamp.build_prefix()

    def filter_response(self, response_text: str) -> str:
        """Pass the LLM response through the preamp filter."""
        return self.preamp.filter_response(response_text)

    def get_debug_info(self) -> dict:
        return {
            "detection": self.last_metadata,
            "base_config": self.base_config.to_dict(),
            "preamp_config": self.config.to_dict(),
            "settings_path": str(self.settings_path),
        }
