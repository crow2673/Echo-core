#!/usr/bin/env python3
"""Promote Echo growth proposals into reviewed build requests."""
import sys
from pathlib import Path

BASE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BASE))

from core.growth_bridge import main


if __name__ == "__main__":
    raise SystemExit(main())
