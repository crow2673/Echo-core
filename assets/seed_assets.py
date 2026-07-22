#!/usr/bin/env python3
"""Seed Echo Asset System v1 with Andrew's first assets."""
from __future__ import annotations

import sys
from pathlib import Path

BASE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BASE))

from assets.asset_manager import AssetManager
from assets.asset_types import Asset, AssetType


SEED_ASSETS = [
    Asset(
        asset_id="TACOMA-01",
        name="2003 Toyota Tacoma",
        type=AssetType.VEHICLE,
        manufacturer="Toyota",
        model="Tacoma 4WD 3.4L",
        metadata={"drive": "4WD", "engine": "3.4L"},
    ),
    Asset(asset_id="ECHO-CORE", name="Main AI System", type=AssetType.AI_SYSTEM),
    Asset(
        asset_id="WORKSHOP-01",
        name="Garage / Workbench / Storage",
        type=AssetType.WORKSHOP,
        metadata={"areas": ["Garage", "Workbench", "Storage"]},
    ),
    Asset(
        asset_id="FURNACE-01",
        name="Propane Furnace",
        type=AssetType.FURNACE,
        model="6kg Crucible",
        metadata={"capacity": "6kg crucible"},
    ),
    Asset(
        asset_id="HOUSE-01",
        name="Home",
        type=AssetType.HOME,
        metadata={"topics": ["Mortgage", "Solar"]},
    ),
]


def seed() -> list[str]:
    manager = AssetManager()
    return [manager.register_asset(asset) for asset in SEED_ASSETS]


if __name__ == "__main__":
    for asset_id in seed():
        print(asset_id)
