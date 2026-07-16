#!/usr/bin/env python3
"""Voice/transcript intake for assets."""
from __future__ import annotations

import sys
from pathlib import Path

BASE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BASE))

from assets.asset_types import Observation
from assets.observation_engine import ObservationEngine


def ingest_voice(*, asset: str, transcript: str, speaker: str = "andrew",
                 tags: list[str] | None = None,
                 observation_engine: ObservationEngine | None = None) -> dict:
    clean = " ".join(str(transcript or "").split())
    obs = Observation(
        asset=asset,
        source="voice",
        summary=clean[:200] or "Voice note",
        raw_text=transcript,
        tags=tags or ["voice"],
        confidence=0.85 if clean else 0.3,
        payload={"speaker": speaker},
    )
    engine = observation_engine or ObservationEngine()
    return engine.receive(obs)
