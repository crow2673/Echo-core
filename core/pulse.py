#!/usr/bin/env python3
"""core/pulse.py — daily heartbeat signal. Confirms Echo is alive."""
from datetime import datetime, timezone
from pathlib import Path
import sys

BASE = Path(__file__).resolve().parents[1]
LOG = BASE / "logs/pulse.log"


def run():
    ts = datetime.now(timezone.utc).isoformat()
    msg = f"pulse_ok {ts}"
    print(msg, flush=True)
    LOG.parent.mkdir(exist_ok=True)
    with open(LOG, "a") as f:
        f.write(f"{msg}\n")
    try:
        from core.event_ledger import log_event
        log_event("system", "pulse", "daily pulse ok", score=1.0)
    except Exception:
        pass


if __name__ == "__main__":
    run()
