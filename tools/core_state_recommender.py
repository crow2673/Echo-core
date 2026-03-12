#!/usr/bin/env python3
import json
from pathlib import Path

STATE = Path.home()/"Echo/memory/core_state_system.json"

def main():
    s = json.loads(STATE.read_text())
    workers = s.get("workers", {})

    problems = []
    for name, w in workers.items():
        if not isinstance(w, dict):
            continue
        if w.get("stale") is True:
            problems.append(name)

    if problems:
        print("RECOMMEND:", "restart timers for:", ", ".join(problems))
    else:
        print("RECOMMEND: no action (all workers ok)")

if __name__ == "__main__":
    main()
