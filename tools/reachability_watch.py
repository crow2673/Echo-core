#!/usr/bin/env python3
"""tools/reachability_watch.py — watches for reachability constraint wake conditions."""
import json
import time
from pathlib import Path

MEM = Path.home() / "Echo/memory"
LOG = Path.home() / "Echo/memory/reachability_watch.log"
CONSTRAINTS_FILE = MEM / "constraints.jsonl"


def load_constraints():
    if not CONSTRAINTS_FILE.exists():
        return []
    constraints = []
    for line in CONSTRAINTS_FILE.read_text().splitlines():
        line = line.strip()
        if line:
            try:
                constraints.append(json.loads(line))
            except Exception:
                pass
    return constraints


def main():
    constraints = load_constraints()
    active = [c for c in constraints if c.get("status") == "deferred" and c.get("public_reachability")]

    if not active:
        return

    with open(LOG, "a") as f:
        for c in active:
            name = c.get("name", "unnamed")
            f.write(f"[{time.ctime()}] Reachability constraint active. Watching for wake conditions.\n")
            print(f"[reachability] watching: {name}", flush=True)


if __name__ == "__main__":
    main()
