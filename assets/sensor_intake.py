#!/usr/bin/env python3
"""Generic sensor intake."""
from __future__ import annotations

import sys
from pathlib import Path

BASE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BASE))

from assets.telemetry_engine import TelemetryEngine


def ingest_sensor(*, asset: str, sensor: str, value: float, units: str = "") -> dict:
    return TelemetryEngine().record(
        asset=asset,
        sensor=sensor,
        value=value,
        units=units,
        source="sensor",
    )
