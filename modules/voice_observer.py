#!/usr/bin/env python3
"""Compatibility wrapper for voice asset observations."""
from __future__ import annotations

from assets.asset_types import Observation


def observe_voice(transcript: str, speaker: str = "unknown", audio_uri: str | None = None,
                  asset: str = "ECHO-CORE") -> Observation:
    clean = " ".join(str(transcript or "").split())
    return Observation(
        asset=asset,
        source="voice",
        summary=(clean[:160] if clean else "Voice observation"),
        raw_text=transcript,
        tags=["voice"],
        payload={"speaker": speaker, "audio_uri": audio_uri},
        confidence=0.85 if clean else 0.3,
    )
