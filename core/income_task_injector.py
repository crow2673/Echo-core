#!/usr/bin/env python3
import json
import subprocess
from pathlib import Path
from datetime import datetime

BASE = Path(__file__).resolve().parents[1]
STATE_FILE = BASE / "memory/core_state_reasoning.json"
INCOME_LOG = BASE / "logs/income.log"

def load_state():
    if STATE_FILE.exists():
        return json.loads(STATE_FILE.read_text())
    return {"reasoning_history": [], "knowledge": {}, "X_flags": []}

def save_state(state):
    STATE_FILE.write_text(json.dumps(state, indent=2) + "\n")

def get_golem_status():
    try:
        result = subprocess.run(["ya-provider", "status"], capture_output=True, text=True, timeout=10)
        return result.stdout[:300]
    except Exception:
        return "unknown"

def inject_tasks():
    # Build outcome context so Echo doesn't repeat herself
    try:
        import sys
        sys.path.insert(0, str(BASE.parent))
        from core.feedback_loop import log_suggestions, build_outcome_context
        log_suggestions()
        outcome_context = build_outcome_context()
    except Exception as e:
        outcome_context = ""
        print(f"feedback error: {e}")
    state = load_state()
    existing = state.get("X_flags", [])
    if existing:
        print(f"Queue not empty ({len(existing)} tasks), skipping")
        return
    now = datetime.now().isoformat()
    golem_status = get_golem_status()
    prefix = f"\n{outcome_context}\n\n" if outcome_context else ""
    state["X_flags"] = [
        prefix + f"[{now}] Golem node has 0 earnings, status='{golem_status}'. Identify the most likely reason and suggest one concrete terminal command to attract tasks.",
        f"[{now}] Suggest the best topic for next week's dev.to article based on Echo's recent build progress that would attract developers who might fund or use Echo.",
    ]
    save_state(state)
    INCOME_LOG.parent.mkdir(exist_ok=True)
    with open(INCOME_LOG, "a") as f:
        f.write(f"{now} — injected {len(state['X_flags'])} income tasks\n")
    print(f"Injected {len(state['X_flags'])} tasks")

if __name__ == "__main__":
    inject_tasks()
