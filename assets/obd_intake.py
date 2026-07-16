#!/usr/bin/env python3
"""OBD-II intake for vehicle assets."""
from __future__ import annotations

import sys
from pathlib import Path

BASE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BASE))

from assets.config import module_enabled
from assets.telemetry_engine import TelemetryEngine


def ingest_obd(*, asset: str, readings: dict[str, tuple[float, str] | float]) -> list[dict]:
    if not module_enabled("vehicle_intelligence"):
        raise RuntimeError("vehicle_intelligence disabled by assets/config.json")
    engine = TelemetryEngine()
    results = []
    for sensor, reading in readings.items():
        if isinstance(reading, tuple):
            value, units = reading
        else:
            value, units = reading, ""
        results.append(
            engine.record(asset=asset, sensor=sensor, value=float(value), units=units, source="obd")
        )
    return results
