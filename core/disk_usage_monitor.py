#!/usr/bin/env python3
"""
core/disk_usage_monitor.py
Monitors disk usage and logs to logs/disk_usage.log
Alerts via ntfy if any mount point exceeds threshold.
"""
import shutil
import json
from pathlib import Path
from datetime import datetime

BASE = Path(__file__).resolve().parents[1]
LOG = BASE / "logs/disk_usage.log"
ALERT_THRESHOLD = 85  # percent

MOUNTS = ["/", str(Path.home())]

def check_disk():
    results = []
    alerts = []
    for mount in MOUNTS:
        try:
            usage = shutil.disk_usage(mount)
            pct = (usage.used / usage.total) * 100
            entry = {
                "mount": mount,
                "total_gb": round(usage.total / 1024**3, 1),
                "used_gb": round(usage.used / 1024**3, 1),
                "free_gb": round(usage.free / 1024**3, 1),
                "percent": round(pct, 1)
            }
            results.append(entry)
            if pct >= ALERT_THRESHOLD:
                alerts.append(f"{mount} at {pct:.1f}%")
        except Exception as e:
            results.append({"mount": mount, "error": str(e)})

    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    line = f"{timestamp} — " + " | ".join(
        f"{r['mount']} {r.get('percent','?')}% ({r.get('free_gb','?')}GB free)"
        for r in results
    )
    LOG.parent.mkdir(parents=True, exist_ok=True)
    with open(LOG, "a") as f:
        f.write(line + "\n")
    print(line)

    if alerts:
        try:
            from core.notifier import notify
            notify(f"⚠ Disk alert: {', '.join(alerts)}")
        except Exception as e:
            print(f"notify failed: {e}")

    return results

if __name__ == "__main__":
    check_disk()
