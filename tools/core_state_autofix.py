#!/usr/bin/env python3
"""tools/core_state_autofix.py — restarts stale Echo workers (safe allowlist only)."""
import json
import subprocess
from datetime import datetime
from pathlib import Path

BASE = Path(__file__).resolve().parents[1]
LOG = BASE / "logs/core_state_autofix.log"
STATE_FILE = BASE / "memory/core_state_system.json"

RESTARTABLE = {
    "echo-heartbeat.service",
    "echo-disk-monitor.service",
    "echo-ollama-watchdog.service",
}


def log(msg):
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    LOG.parent.mkdir(exist_ok=True)
    with open(LOG, "a") as f:
        f.write(f"[{ts}] {msg}\n")
    print(msg, flush=True)


def restart(unit):
    try:
        r = subprocess.run(
            ["systemctl", "--user", "restart", unit],
            capture_output=True, text=True, timeout=15
        )
        if r.returncode == 0:
            log(f"restarted {unit}")
        else:
            log(f"restart failed {unit}: {r.stderr.strip()}")
    except Exception as e:
        log(f"restart error {unit}: {e}")


def run():
    if not STATE_FILE.exists():
        log("no state file — skipping")
        return

    try:
        state = json.loads(STATE_FILE.read_text())
    except Exception as e:
        log(f"state load error: {e}")
        return

    workers = state.get("workers", {})
    fixed = 0
    for name, info in workers.items():
        if info.get("stale") and info.get("service") in RESTARTABLE:
            log(f"stale worker: {name} — restarting")
            restart(info["service"])
            fixed += 1

    log(f"autofix done — {fixed} workers restarted")


if __name__ == "__main__":
    run()
