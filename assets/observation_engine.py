#!/usr/bin/env python3
"""Central intake for every Echo Asset System observation."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

BASE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BASE))

from assets.asset_manager import AssetManager
from assets.asset_types import Observation
from assets.config import module_enabled

OBS_DIR = BASE / "memory/observations"


class ObservationEngine:
    def __init__(
        self,
        asset_manager: AssetManager | None = None,
        observations_dir: Path | None = None,
        mirror_events: bool = True,
    ):
        if not module_enabled("assets"):
            raise RuntimeError("asset system disabled by assets/config.json")
        self.assets = asset_manager or AssetManager()
        self.observations_dir = observations_dir or OBS_DIR
        self.mirror_events = mirror_events
        self.observations_dir.mkdir(parents=True, exist_ok=True)

    def receive(self, observation: Observation) -> dict[str, Any]:
        result = self.assets.observe(observation)
        self._write_memory(observation, result, self.observations_dir)
        if self.mirror_events:
            self._log_event(observation, result)
        return {"ok": True, **result}

    def receive_dict(self, data: dict[str, Any]) -> dict[str, Any]:
        observation = Observation(
            asset=data["asset"],
            timestamp=data.get("timestamp") or data.get("observed_at") or Observation(asset=data["asset"], summary="").timestamp,
            source=data.get("source", "manual"),
            summary=data.get("summary", ""),
            raw_text=data.get("raw_text", ""),
            tags=list(data.get("tags", [])),
            confidence=float(data.get("confidence", 1.0)),
            payload=data.get("payload", {}),
        )
        return self.receive(observation)

    def summary(self) -> dict[str, Any]:
        return self.assets.summary()

    @staticmethod
    def _write_memory(observation: Observation, result: dict[str, Any], observations_dir: Path) -> None:
        record = {
            "observation_id": result.get("observation_id"),
            "asset": observation.asset,
            "timestamp": observation.timestamp,
            "source": str(observation.source),
            "summary": observation.summary,
            "raw_text": observation.raw_text,
            "tags": observation.tags,
            "confidence": observation.confidence,
            "payload": observation.payload,
        }
        safe_asset = "".join(c if c.isalnum() or c in "-_" else "_" for c in observation.asset)
        path = observations_dir / f"{safe_asset}.jsonl"
        with path.open("a") as f:
            f.write(json.dumps(record, sort_keys=True, default=str) + "\n")

    @staticmethod
    def _log_event(observation: Observation, result: dict[str, Any]) -> None:
        try:
            from core.event_ledger import log_event

            log_event(
                event_type="observation",
                source=str(observation.source),
                summary=observation.summary,
                score=observation.confidence,
                data={
                    "observation_id": result.get("observation_id"),
                    "asset_id": observation.asset,
                    "tags": observation.tags,
                },
            )
        except Exception as exc:
            print(f"[asset_observation_engine] event mirror failed: {exc}")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--json", help="Observation JSON object")
    parser.add_argument("--summary", action="store_true")
    args = parser.parse_args()

    engine = ObservationEngine()
    if args.summary:
        print(json.dumps(engine.summary(), indent=2))
        return 0
    if not args.json:
        parser.error("--json or --summary is required")
    print(json.dumps(engine.receive_dict(json.loads(args.json)), indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
