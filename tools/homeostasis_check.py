#!/usr/bin/env python3
"""Run Echo's conservative reliability homeostasis check."""
import sys
from pathlib import Path

BASE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BASE))

from core.homeostasis import main


if __name__ == "__main__":
    raise SystemExit(main())
