#!/usr/bin/env python3
import json
import time
from pathlib import Path
import argparse

BASE_DIR = Path(__file__).parent.resolve()
MEMORY_FILE = BASE_DIR / "echo_memory.json"
LOG_DIR = BASE_DIR / "memory"
SCAN_LOG = LOG_DIR / "outlier_scans.log"

def load_memory():
    if not MEMORY_FILE.exists() or MEMORY_FILE.stat().st_size == 0:
        return []
    return json.loads(MEMORY_FILE.read_text())

def save_memory(m):
    MEMORY_FILE.write_text(json.dumps(m, indent=2))

def append_log(line: str):
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    with open(SCAN_LOG, "a", encoding="utf-8") as f:
        f.write(line.rstrip() + "\n")

def main():
    p = argparse.ArgumentParser()
    p.add_argument("--capsule-id", default="TASK:MasterFirst:2")
    p.add_argument("--note", default="Manual review pending (stub).")
    args = p.parse_args()

    ts = int(time.time())
    line = f"{ts}\t{args.capsule_id}\t{args.note}"
    append_log(line)

    # Best-effort: also try to update echo_memory.json (may lose to concurrent writers)
    try:
        m = load_memory()
        cap = next((c for c in m if c.get("capsule_id") == args.capsule_id), None)
        if cap:
            cap["last_scan_ts"] = ts
            cap.setdefault("result_notes", [])
            cap["result_notes"].append(f"[outlier_scan_stub] {args.note} (ts={ts})")
            save_memory(m)
    except Exception:
        pass

    print(f"[outlier_scan_stub] logged: {line}")

if __name__ == "__main__":
    main()
