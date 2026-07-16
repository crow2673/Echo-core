#!/usr/bin/env python3
"""Telemetry intake for OBD-II and sensor values."""
from __future__ import annotations

from datetime import datetime
from pathlib import Path

from assets.asset_manager import AssetManager
from assets.asset_database import AssetDatabase
from assets.asset_types import Observation
from assets.config import module_enabled
from assets.observation_engine import ObservationEngine


class TelemetryEngine:
    def __init__(
        self,
        database: AssetDatabase | None = None,
        observations_dir: Path | None = None,
        mirror_events: bool = True,
    ):
        if not module_enabled("telemetry"):
            raise RuntimeError("telemetry disabled by assets/config.json")
        self.db = database or AssetDatabase()
        self.observations = ObservationEngine(
            AssetManager(self.db),
            observations_dir=observations_dir,
            mirror_events=mirror_events,
        )

    def record(self, *, asset: str, sensor: str, value: float, units: str = "",
               timestamp: str | None = None, source: str = "telemetry") -> dict:
        ts = timestamp or datetime.now().isoformat()
        telemetry_id = self.db.add_telemetry(
            asset_id=asset,
            timestamp=ts,
            sensor=sensor,
            value=value,
            units=units,
        )
        obs = Observation(
            asset=asset,
            timestamp=ts,
            source=source,
            summary=f"{sensor}: {value} {units}".strip(),
            raw_text=f"{sensor}={value} {units}".strip(),
            tags=["telemetry", sensor],
            confidence=1.0,
            payload={"telemetry_id": telemetry_id, "sensor": sensor, "value": value, "units": units},
        )
        result = self.observations.receive(obs)
        return {"telemetry_id": telemetry_id, **result}
