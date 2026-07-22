#!/usr/bin/env python3
"""Run Echo's evidence-based growth queue builder."""
import sys
from pathlib import Path

BASE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BASE))

from core.growth_engine import main


if __name__ == "__main__":
    raise SystemExit(main())
