#!/usr/bin/env python3
"""Asset system configuration."""
from __future__ import annotations

import json
from pathlib import Path

BASE = Path.home() / "Echo"
CONFIG_FILE = BASE / "assets/config.json"

DEFAULT_CONFIG = {
    "enabled_modules": {
        "assets": True,
        "vehicle_intelligence": True,
        "telemetry": True,
        "maintenance": True,
    }
}


def load_config() -> dict:
    if not CONFIG_FILE.exists():
        return DEFAULT_CONFIG
    try:
        merged = DEFAULT_CONFIG.copy()
        data = json.loads(CONFIG_FILE.read_text())
        merged["enabled_modules"] = {
            **DEFAULT_CONFIG["enabled_modules"],
            **data.get("enabled_modules", {}),
        }
        return merged
    except Exception:
        return DEFAULT_CONFIG


def module_enabled(name: str) -> bool:
    return bool(load_config().get("enabled_modules", {}).get(name, False))
