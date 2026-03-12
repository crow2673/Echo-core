#!/usr/bin/env python3
"""
echo_watchdog.py
Echo monitors her own health and notifies Andrew when something needs attention.
Runs every 10 minutes via systemd timer.
"""
import subprocess
import json
from pathlib import Path
from datetime import datetime, timezone
import sys
BASE = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE))
from core.notifier import notify
SERVICES = ["echo-core.service", "golem-provider.service", "yagna.service"]
STATE_FILE = BASE / "memory/core_state_system.json"
WATCHDOG_LOG = BASE / "logs/watchdog.log"
LAST_EARNINGS_FILE = BASE / "memory/last_golem_earnings.json"
def check_services():
    down = []
    for svc in SERVICES:
        result = subprocess.run(["systemctl", "--user", "is-active", svc], capture_output=True, text=True)
        if result.stdout.strip() != "active":
            down.append(svc)
    return down
def check_golem_earnings():
    try:
        result = subprocess.run(["yagna", "payment", "status", "--json"], capture_output=True, text=True, timeout=10)
        data = json.loads(result.stdout)
        incoming = float(data.get("incoming", {}).get("accepted", {}).get("totalAmount", 0))
        last = {}
        if LAST_EARNINGS_FILE.exists():
            last = json.loads(LAST_EARNINGS_FILE.read_text())
        last_amount = float(last.get("amount", 0))
        LAST_EARNINGS_FILE.write_text(json.dumps({"amount": incoming, "checked": datetime.now().isoformat()}))
        if incoming > last_amount and incoming > 0:
            return incoming - last_amount
    except Exception:
        pass
    return 0
def log(msg):
    WATCHDOG_LOG.parent.mkdir(exist_ok=True)
    with open(WATCHDOG_LOG, "a") as f:
        f.write(f"{datetime.now().isoformat()} {msg}\n")
    print(msg)
def inject_recovery(still_down):
    try:
        fb = BASE / "memory/feedback_log.json"
        data = json.loads(fb.read_text()) if fb.exists() else []
        for svc in still_down:
            data.append({"id": f"watchdog_{svc.replace('.','_')}_{datetime.now().strftime('%Y%m%d_%H%M%S')}", "suggestion": f"restart {svc.replace('.service','')} service", "status": "pending", "source": "watchdog", "category": "service_management", "created_at": datetime.now().isoformat()})
        fb.write_text(json.dumps(data, indent=2))
        log(f"injected recovery suggestions for: {still_down}")
    except Exception as e:
        log(f"feedback inject error: {e}")
def run():
    down = check_services()
    if down:
        for svc in down:
            subprocess.run(["systemctl", "--user", "restart", svc], capture_output=True)
            log(f"restarted {svc}")
        import time
        time.sleep(15)
        still_down = check_services()
        print(f"post-restart check: {still_down}")
        if still_down:
            msg = f"Service down and restart failed: {', '.join(still_down)}"
            notify("Service Alert", msg, urgent=True)
            log(msg)
            inject_recovery(still_down)
        else:
            msg = f"Auto-restarted: {', '.join(down)}"
            notify("Self-Healed", msg, urgent=False)
            log(msg)
    earned = check_golem_earnings()
    if earned > 0:
        msg = f"First Golem earnings: +{earned:.4f} GLM"
        notify("Income", msg, urgent=False)
        log(msg)
    final_down = check_services()
    log(f"watchdog OK — services:{len(SERVICES)-len(final_down)}/{len(SERVICES)} up")
if __name__ == "__main__":
    run()
