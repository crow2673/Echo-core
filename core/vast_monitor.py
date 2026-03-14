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
            ["vastai", "show", "machines"],
            capture_output=True, text=True, timeout=30
        )
        if result.returncode != 0:
            log(f"CLI error: {result.stderr.strip()}")
            return
        lines = result.stdout.strip().splitlines()
        if len(lines) < 2:
            log("no machines found")
            return
        for line in lines[1:]:  # skip header
            parts = line.split()
            if not parts: continue
            mid = parts[0]
            reliability = parts[6] if len(parts) > 6 else "?"
            verified = parts[7] if len(parts) > 7 else "?"
            price = parts[10] if len(parts) > 10 else "?"
            occup = parts[-1] if parts else "?"
            renting = occup not in ("x_", "x", "")
            log(f"machine {mid}: verified={verified} reliability={reliability} price={price}/hr renting={renting} occupancy={occup}")
            try:
                import sys; sys.path.insert(0, str(BASE))
                from core.event_ledger import log_event
                log_event("income", "vast_monitor",
                    f"machine {mid}: verified={verified} reliability={reliability} price={price}/hr renting={renting}",
                    score=1.0 if renting else 0.0)
                # Mirror to Notion Income Tracker
                from core.notion_bridge import log_income_to_notion
                status = "active" if renting else "pending"
                log_income_to_notion("Vast.ai GPU", status,
                    f"Machine {mid}: reliability={reliability} price={price}/hr renting={renting}")
            except Exception:
                pass
    except Exception as e:
        log(f"check failed: {e}")

if __name__ == "__main__":
    check_vast()
