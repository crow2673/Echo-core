#!/usr/bin/env python3
"""Compatibility wrapper for image asset observations."""
from __future__ import annotations

from pathlib import Path

from assets.asset_types import Observation


def observe_image(path: str | Path, summary: str = "", metadata: dict | None = None,
                  asset: str = "ECHO-CORE") -> Observation:
    image_path = Path(path)
    payload = {"path": str(image_path), **(metadata or {})}
    if image_path.exists():
        payload["bytes"] = image_path.stat().st_size
    return Observation(
        asset=asset,
        source="image",
        summary=summary or f"Image observed: {image_path.name}",
        raw_text=str(image_path),
        tags=["image"],
        payload=payload,
    )
