#!/usr/bin/env python3
"""tools/heartbeat.py — appends a heartbeat entry to experience_log.jsonl."""
import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path

BASE = Path(__file__).resolve().parents[1]
LOG = BASE / "memory/experience_log.jsonl"


def get_service_status(svc):
    try:
        r = subprocess.run(
            ["systemctl", "--user", "is-active", svc],
            capture_output=True, text=True, timeout=5
        )
        return r.stdout.strip()
    except Exception:
        return "unknown"


def run():
    ts = datetime.now(timezone.utc).isoformat()
    entry = {
        "ts": ts,
        "type": "heartbeat",
        "core": get_service_status("echo-core.service"),
        "ntfy": get_service_status("echo-ntfy-bridge.service"),
    }
    LOG.parent.mkdir(parents=True, exist_ok=True)
    with open(LOG, "a") as f:
        f.write(json.dumps(entry) + "\n")
    print(f"heartbeat {ts}", flush=True)


if __name__ == "__main__":
    run()
