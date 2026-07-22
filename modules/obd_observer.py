#!/usr/bin/env python3
"""Compatibility wrapper for OBD asset observations."""
from __future__ import annotations

from assets.asset_types import Observation


def observe_obd(reading: dict, summary: str = "", asset: str = "TACOMA-01") -> Observation:
    tags = ["obd", "telemetry"]
    tags.extend(str(key).lower() for key in reading.keys())
    return Observation(
        asset=asset,
        source="obd",
        summary=summary or "OBD reading observed",
        raw_text=str(reading),
        tags=tags,
        payload=reading,
        confidence=0.95,
    )
