#!/usr/bin/env python3
"""golem_monitor.py — Golem provider monitor (deprecated, Golem no longer active).
Service kept to avoid systemd errors; exits cleanly with no-op.
"""
from datetime import datetime
from pathlib import Path

LOG = Path.home() / "Echo/memory/golem_cron.log"
LOG.parent.mkdir(exist_ok=True)
ts = datetime.now().strftime("%Y-%m-%d %H:%M")
with open(LOG, "a") as f:
    f.write(f"[{ts}] golem_monitor: Golem provider deactivated — no-op\n")
print("golem_monitor: no-op (Golem deactivated)", flush=True)
