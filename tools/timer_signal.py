#!/usr/bin/env python3
"""Thin shim called by systemd timers — forwards to core.dispatcher."""
import sys
import subprocess
from pathlib import Path

if len(sys.argv) < 2:
    print("Usage: timer_signal.py <worker_name>")
    sys.exit(1)

worker = sys.argv[1]
base = Path(__file__).resolve().parents[1]

result = subprocess.run(
    [sys.executable, "-m", "core.dispatcher", worker],
    cwd=str(base)
)
sys.exit(result.returncode)
