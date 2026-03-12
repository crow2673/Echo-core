#!/usr/bin/env python3
"""
core/log_rotator.py
Keeps Echo's logs from growing unbounded.
Runs nightly via backup timer.
"""
from pathlib import Path
from datetime import datetime

BASE = Path.home() / "Echo"

# (file, max_lines, max_kb)
ROTATION_RULES = [
    ("memory/experience_log.jsonl", 2000, None),
    ("memory/echo_events.ndjson", 2000, None),
    ("memory/reachability_watch.log", 500, None),
    ("memory/core_state.log", 500, None),
    ("logs/core_state_autofix.log", 500, None),
    ("logs/daemon.log", 500, None),
    ("logs/self_act_worker.log", 500, None),
    ("logs/watchdog.log", 500, None),
    ("logs/income.log", 200, None),
    ("logs/auto_act.log", 200, None),
]

def rotate(rel_path, max_lines):
    f = BASE / rel_path
    if not f.exists():
        return 0, 0
    lines = f.read_text(errors="replace").splitlines()
    before = len(lines)
    if before <= max_lines:
        return before, 0
    kept = lines[-max_lines:]
    f.write_text("\n".join(kept) + "\n")
    trimmed = before - len(kept)
    return before, trimmed

if __name__ == "__main__":
    print(f"[log_rotator] {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    total_trimmed = 0
    for rel_path, max_lines, _ in ROTATION_RULES:
        before, trimmed = rotate(rel_path, max_lines)
        if trimmed > 0:
            print(f"  trimmed {trimmed} lines from {rel_path} ({before} → {before-trimmed})")
        total_trimmed += trimmed
    print(f"[log_rotator] done — {total_trimmed} lines removed")
