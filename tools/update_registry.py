#!/usr/bin/env python3
"""tools/update_registry.py — updates registry.json with current service states."""
import json
import subprocess
from datetime import datetime
from pathlib import Path

BASE = Path(__file__).resolve().parents[1]
REGISTRY = BASE / "registry.json"
LOG = BASE / "logs/registry_update.log"

SERVICES_TO_TRACK = [
    "echo-core.service",
    "echo-ntfy-bridge.service",
    "echo-auto-act.timer",
    "echo-governor.timer",
    "echo-crypto-trader.timer",
    "echo-trader.timer",
    "echo-demand-scanner.timer",
    "echo-session-checkpoint.timer",
    "echo-daily-summary.timer",
    "echo-offsite-backup.timer",
    "echo-ollama-watchdog.timer",
]


def log(msg):
    ts = datetime.now().strftime("%Y-%m-%d %H:%M")
    LOG.parent.mkdir(exist_ok=True)
    with open(LOG, "a") as f:
        f.write(f"[{ts}] {msg}\n")
    print(msg, flush=True)


def is_active(unit):
    try:
        r = subprocess.run(
            ["systemctl", "--user", "is-active", unit],
            capture_output=True, text=True, timeout=5
        )
        return r.stdout.strip()
    except Exception:
        return "unknown"


def run():
    log("registry update starting")

    try:
        existing = json.loads(REGISTRY.read_text()) if REGISTRY.exists() else {}
    except Exception:
        existing = {}

    services = {}
    for unit in SERVICES_TO_TRACK:
        services[unit] = is_active(unit)

    existing["services"] = services
    existing["updated_at"] = datetime.now().isoformat()

    tmp = REGISTRY.with_suffix(".tmp")
    tmp.write_text(json.dumps(existing, indent=2))
    tmp.rename(REGISTRY)

    active = sum(1 for s in services.values() if s == "active")
    log(f"registry updated — {active}/{len(services)} active")


if __name__ == "__main__":
    run()
