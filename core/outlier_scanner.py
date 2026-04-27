#!/usr/bin/env python3
"""
core/outlier_scanner.py — Outlier.ai task availability scanner

Checks Outlier.ai for available expert tasks (data labeling, RLHF, coding tasks).
Since Outlier requires login to see tasks, this scanner:
  1. Checks if the Outlier site is reachable
  2. Fires a timed reminder every N hours to check manually
  3. Runs a basic signal check on the public tasks page for any visible listings

Wired into initiative_engine as trigger #7.
Runs every 4 hours via echo-outlier-scanner.timer.

Income potential: $10-50+ per task (coding tasks, model evaluation, RLHF)
"""
import json
from datetime import datetime, timedelta
from pathlib import Path
import sys

BASE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BASE))
STATE_FILE = BASE / "memory/outlier_state.json"
LOG_FILE = BASE / "logs/outlier_scanner.log"
OUTLIER_URL = "https://app.outlier.ai/en/expert/tasks"
CHECK_INTERVAL = timedelta(hours=4)
REMIND_INTERVAL = timedelta(hours=8)


def log(msg):
    ts = datetime.now().strftime("%H:%M:%S")
    print(f"[{ts}] {msg}", flush=True)
    LOG_FILE.parent.mkdir(exist_ok=True)
    with open(LOG_FILE, "a") as f:
        f.write(f"[{ts}] {msg}\n")


def load_state():
    if STATE_FILE.exists():
        try:
            return json.loads(STATE_FILE.read_text())
        except Exception:
            pass
    return {}


def save_state(state):
    tmp = STATE_FILE.with_suffix(".tmp")
    tmp.write_text(json.dumps(state, indent=2, default=str))
    tmp.rename(STATE_FILE)


def is_cooled_down(state, key, interval):
    last = state.get(key)
    if not last:
        return True
    try:
        return datetime.now() - datetime.fromisoformat(last) >= interval
    except Exception:
        return True


def check_outlier(state):
    """Check Outlier.ai availability and signal for tasks."""
    if not is_cooled_down(state, "last_check", CHECK_INTERVAL):
        log("Cooled down — skipping")
        return state

    try:
        import urllib.request
        req = urllib.request.Request(
            OUTLIER_URL,
            headers={"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"},
        )
        with urllib.request.urlopen(req, timeout=15) as r:
            body = r.read().decode("utf-8", errors="ignore")
            code = r.status
        state["site_reachable"] = True
        state["last_status_code"] = code
        task_signals = ["tasks available", "open tasks", "apply now", "start task"]
        signals = [s for s in task_signals if s in body.lower()]
        state["task_signal_strength"] = len(signals)
        state["signals_found"] = signals
        state["has_no_tasks_message"] = "no tasks" in body.lower() or "check back" in body.lower()
        log(f"Outlier reachable: True | status: {code}")
    except Exception as e:
        state["site_reachable"] = False
        state["task_signal_strength"] = 0
        log(f"Outlier unreachable: {e}")

    state["last_check"] = datetime.now().isoformat()
    return state


def fire_reminder(state):
    """Send ntfy reminder to check Outlier manually."""
    if not is_cooled_down(state, "last_remind", REMIND_INTERVAL):
        return state

    msg = (
        "Outlier.ai unreachable — site may be down"
        if not state.get("site_reachable")
        else "Check Outlier.ai for expert tasks (data labeling, RLHF, coding review)"
    )
    try:
        from core.notifier import notify
        notify("Outlier.ai Check", msg, urgent=False)
        log(f"Reminder sent: {msg[:60]}")
        state["last_remind"] = datetime.now().isoformat()
    except Exception as e:
        log(f"Notify failed: {e}")

    save_state(state)
    return state


def get_status():
    """Return current state for initiative_engine."""
    return load_state()


def run():
    log("[outlier_scanner] starting")
    state = load_state()
    state = check_outlier(state)
    state = fire_reminder(state)
    save_state(state)
    log("[outlier_scanner] done")

    try:
        from core.event_ledger import log_event
        signal = state.get("task_signal_strength", 0)
        log_event("income", "outlier_scanner", f"signal={signal}", score=min(signal / 3, 1.0))
    except Exception:
        pass


if __name__ == "__main__":
    run()
