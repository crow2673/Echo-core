#!/usr/bin/env python3
"""
core/vast_monitor.py
Checks Vast.ai machine status and earnings via CLI.
Logs to event ledger and feedback if action needed.
"""
import subprocess, json
from pathlib import Path
from datetime import datetime

BASE = Path(__file__).resolve().parents[1]
LOG = BASE / "logs/income.log"

def log(msg):
    ts = datetime.now().strftime("%Y-%m-%d %H:%M")
    line = f"[{ts}] [vast] {msg}"
    print(line)
    with open(LOG, "a") as f:
        f.write(line + "\n")

def check_vast():
    try:
        result = subprocess.run(
            ["vastai", "show", "machines", "--raw"],
            capture_output=True, text=True, timeout=30
        )
        if result.returncode != 0:
            log(f"CLI error: {result.stderr.strip()}")
            return
        data = json.loads(result.stdout)
        for m in data:
            mid = m.get("id")
            listed = m.get("listed", False)
            earnings = m.get("total_flops_hr", 0)
            reliability = m.get("reliability2", 0)
            running = m.get("num_running", 0)
            log(f"machine {mid}: listed={listed} running={running} reliability={reliability:.1%} earnings_hr={earnings}")
            try:
                import sys; sys.path.insert(0, str(BASE))
                from core.event_ledger import log_event
                log_event("income", "vast_monitor",
                    f"machine {mid}: listed={listed} running={running} reliability={reliability:.1%}",
                    score=1.0 if running > 0 else 0.0)
            except Exception:
                pass
    except Exception as e:
        log(f"check failed: {e}")

if __name__ == "__main__":
    check_vast()
