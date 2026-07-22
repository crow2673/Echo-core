#!/usr/bin/env python3
"""Initialize Echo Asset System v1."""
from __future__ import annotations

import json
import sys
from pathlib import Path

BASE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BASE))

from assets.asset_database import AssetDatabase
from assets.seed_assets import seed


def init() -> dict:
    db = AssetDatabase()
    seeded = seed()
    return {
        "database": str(db.path),
        "seeded_assets": seeded,
        "summary": db.asset_summary(),
    }


if __name__ == "__main__":
    print(json.dumps(init(), indent=2))
