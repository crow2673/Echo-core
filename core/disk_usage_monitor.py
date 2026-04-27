#!/usr/bin/env python3
"""
core/disk_usage_monitor.py
Monitors disk usage and logs to logs/disk_usage.log
Alerts via Telegram if any mount point exceeds threshold.
"""
import json
import subprocess
from datetime import datetime
from pathlib import Path

BASE = Path(__file__).resolve().parents[1]
LOG = BASE / "logs/disk_usage.log"
THRESHOLD_WARN = 80
THRESHOLD_CRIT = 90


def log(msg):
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    LOG.parent.mkdir(exist_ok=True)
    with open(LOG, "a") as f:
        f.write(f"[{ts}] {msg}\n")
    print(msg, flush=True)


def get_disk_usage():
    result = subprocess.run(["df", "-h", "--output=target,pcent"], capture_output=True, text=True)
    mounts = {}
    for line in result.stdout.splitlines()[1:]:
        parts = line.split()
        if len(parts) == 2:
            mount, pct = parts
            try:
                mounts[mount] = int(pct.strip("%"))
            except ValueError:
                pass
    return mounts


def run():
    mounts = get_disk_usage()
    alerts = []
    for mount, pct in mounts.items():
        if mount.startswith(("/sys", "/proc", "/dev", "/run", "/snap")):
            continue
        log(f"{mount}: {pct}%")
        if pct >= THRESHOLD_CRIT:
            alerts.append(f"CRITICAL: {mount} at {pct}%")
        elif pct >= THRESHOLD_WARN:
            alerts.append(f"⚠ Disk alert: {mount} at {pct}%")

    if alerts:
        msg = " | ".join(alerts)
        log(f"ALERT: {msg}")
        try:
            import sys
            if str(BASE) not in sys.path:
                sys.path.insert(0, str(BASE))
            from core.notifier import notify
            notify("Disk Usage Alert", msg, urgent=True)
        except Exception as e:
            log(f"notify failed: {e}")
    else:
        log("Disk usage OK")


if __name__ == "__main__":
    run()
