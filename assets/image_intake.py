#!/usr/bin/env python3
"""Photo/image intake for assets."""
from __future__ import annotations

import sys
from pathlib import Path

BASE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BASE))

from assets.asset_types import Observation
from assets.observation_engine import ObservationEngine


def ingest_image(*, asset: str, path: str | Path, summary: str = "",
                 tags: list[str] | None = None,
                 observation_engine: ObservationEngine | None = None) -> dict:
    p = Path(path)
    payload = {"path": str(p)}
    if p.exists():
        payload["bytes"] = p.stat().st_size
    obs = Observation(
        asset=asset,
        source="image",
        summary=summary or f"Photo observed for {asset}: {p.name}",
        raw_text=str(p),
        tags=tags or ["image"],
        payload=payload,
    )
    engine = observation_engine or ObservationEngine()
    return engine.receive(obs)
