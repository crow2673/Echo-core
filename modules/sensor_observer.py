#!/usr/bin/env python3
"""Compatibility wrapper for generic sensor asset observations."""
from __future__ import annotations

from assets.asset_types import Observation


def observe_sensor(sensor_id: str, reading: dict, summary: str = "",
                   asset: str = "ECHO-CORE") -> Observation:
    return Observation(
        asset=asset,
        source="sensor",
        summary=summary or f"Sensor reading observed: {sensor_id}",
        raw_text=str(reading),
        tags=["sensor", sensor_id],
        payload={"sensor_id": sensor_id, "reading": reading},
        confidence=0.9,
    )
