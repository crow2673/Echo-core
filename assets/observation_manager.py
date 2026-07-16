#!/usr/bin/env python3
"""Single orchestration layer for Echo asset observation intake."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

BASE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BASE))

from assets.asset_database import AssetDatabase
from assets.asset_manager import AssetManager
from assets.image_intake import ingest_image
from assets.observation_engine import OBS_DIR, ObservationEngine
from assets.telemetry_engine import TelemetryEngine
from assets.voice_intake import ingest_voice


class ObservationManager:
    """Route observation intake to existing specialized modules with one shared backend."""

    def __init__(
        self,
        database: AssetDatabase | None = None,
        observations_dir: Path | None = None,
        mirror_events: bool = True,
    ):
        self.db = database or AssetDatabase()
        self.asset_manager = AssetManager(self.db)
        self.observation_engine = ObservationEngine(
            self.asset_manager,
            observations_dir=observations_dir or OBS_DIR,
            mirror_events=mirror_events,
        )
        self.telemetry_engine = TelemetryEngine(
            database=self.db,
            observations_dir=observations_dir or OBS_DIR,
            mirror_events=mirror_events,
        )

    def ingest(self, data: dict[str, Any]) -> dict[str, Any]:
        kind = str(data.get("kind") or data.get("source") or "manual").lower()
        explicit_asset_observation = (
            data.get("schema") == "echo.asset_observation"
            and int(data.get("schema_version", 0)) == 1
        )
        compatibility_asset_observation = (
            not explicit_asset_observation
            and (data.get("asset_intelligence_version") or data.get("extracted_facts") or data.get("recommended_next_action"))
        )
        if explicit_asset_observation or compatibility_asset_observation:
            structured = dict(data)
            structured.setdefault("source", kind if kind in {"manual", "system"} else data.get("source", "manual"))
            if "asset_id" not in structured:
                structured["asset_id"] = structured.get("asset")
            result = self.asset_manager.ingest_structured_observation(structured)
            response = {"manager": "assets.observation_manager", "kind": kind, "structured": True, **result}
            if compatibility_asset_observation:
                response["compatibility_path"] = True
                response["compatibility_warning"] = (
                    "structured asset observation routed without explicit schema; "
                    "use schema='echo.asset_observation', schema_version=1"
                )
            return response
        if kind in {"manual", "observation", "system"}:
            result = self.observation_engine.receive_dict(data)
        elif kind == "image":
            result = ingest_image(
                asset=data["asset"],
                path=data["path"],
                summary=data.get("summary", ""),
                tags=data.get("tags"),
                observation_engine=self.observation_engine,
            )
        elif kind == "voice":
            result = ingest_voice(
                asset=data["asset"],
                transcript=data.get("transcript", data.get("raw_text", "")),
                speaker=data.get("speaker", "andrew"),
                tags=data.get("tags"),
                observation_engine=self.observation_engine,
            )
        elif kind in {"telemetry", "sensor", "obd"}:
            result = self.telemetry_engine.record(
                asset=data["asset"],
                sensor=data["sensor"],
                value=float(data["value"]),
                units=data.get("units", ""),
                timestamp=data.get("timestamp"),
                source=kind,
            )
        else:
            raise RuntimeError(f"unsupported observation kind: {kind}")
        return {"manager": "assets.observation_manager", "kind": kind, **result}

    def summary(self) -> dict[str, Any]:
        return {
            "manager": "assets.observation_manager",
            "asset_summary": self.asset_manager.summary(),
        }


def _self_test() -> dict[str, Any]:
    db_path = Path("/tmp/echo_observation_manager_selftest.sqlite")
    if db_path.exists():
        db_path.unlink()
    obs_dir = Path("/tmp/echo_observation_manager_observations")
    obs_dir.mkdir(parents=True, exist_ok=True)
    manager = ObservationManager(AssetDatabase(db_path), observations_dir=obs_dir, mirror_events=False)
    image_path = obs_dir / "fixture_image.txt"
    image_path.write_text("synthetic local image placeholder\n")
    results = [
        manager.ingest({
            "kind": "manual",
            "asset": "OBS-MANAGER-FIXTURE",
            "summary": "Manual observation fixture",
            "raw_text": "Manual observation fixture",
            "tags": ["manual"],
        }),
        manager.ingest({
            "kind": "voice",
            "asset": "OBS-MANAGER-FIXTURE",
            "transcript": "Voice note fixture",
            "speaker": "FixtureReviewer",
        }),
        manager.ingest({
            "kind": "image",
            "asset": "OBS-MANAGER-FIXTURE",
            "path": str(image_path),
            "summary": "Image fixture",
        }),
        manager.ingest({
            "kind": "telemetry",
            "asset": "OBS-MANAGER-FIXTURE",
            "sensor": "temperature",
            "value": 72.5,
            "units": "F",
        }),
    ]
    return {
        "ok": True,
        "results": results,
        "summary": manager.summary(),
        "recent_observations": manager.db.recent_observations(asset_id="OBS-MANAGER-FIXTURE", limit=10),
        "telemetry": manager.db.telemetry_recent("OBS-MANAGER-FIXTURE", limit=10),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--json", help="Observation JSON object")
    parser.add_argument("--summary", action="store_true")
    parser.add_argument("--self-test", action="store_true")
    parser.add_argument("--db", type=Path)
    parser.add_argument("--observations-dir", type=Path)
    args = parser.parse_args()

    if args.self_test:
        print(json.dumps(_self_test(), indent=2, sort_keys=True, default=str))
        return 0
    manager = ObservationManager(
        AssetDatabase(args.db) if args.db else None,
        observations_dir=args.observations_dir,
    )
    if args.summary:
        print(json.dumps(manager.summary(), indent=2, sort_keys=True, default=str))
        return 0
    if not args.json:
        parser.error("--json, --summary, or --self-test is required")
    print(json.dumps(manager.ingest(json.loads(args.json)), indent=2, sort_keys=True, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
