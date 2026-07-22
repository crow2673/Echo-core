#!/usr/bin/env python3
"""Compatibility wrapper for assets.observation_engine."""
from __future__ import annotations

import sys
from pathlib import Path

BASE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BASE))

from assets.observation_engine import ObservationEngine, main


if __name__ == "__main__":
    raise SystemExit(main())
