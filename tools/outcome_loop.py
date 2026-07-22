#!/usr/bin/env python3
"""CLI wrapper for Echo's general outcome loop."""
from pathlib import Path
import sys

BASE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BASE))

from core.outcome_loop import main


if __name__ == "__main__":
    raise SystemExit(main())
