#!/usr/bin/env python3
import json, time
from pathlib import Path

BASE_DIR = Path(__file__).parent.resolve()
MEMORY_FILE = BASE_DIR / "echo_memory.json"

def load_memory():
    if not MEMORY_FILE.exists() or MEMORY_FILE.stat().st_size == 0:
        return []
    return json.loads(MEMORY_FILE.read_text())

def save_memory(m):
    MEMORY_FILE.write_text(json.dumps(m, indent=2))

def main():
    m = load_memory()
    master = next((c for c in m if c.get("capsule_id")=="COMMAND:MasterFirst"), None)
    if not master:
        raise SystemExit("No COMMAND:MasterFirst found.")
    tasks = master.get("tasks") or []
    if not tasks:
        raise SystemExit("COMMAND:MasterFirst has no tasks[]")

    existing = {c.get("capsule_id") for c in m}
    created = 0
    for idx, t in enumerate(tasks, start=1):
        cid = f"TASK:MasterFirst:{idx}"
        if cid in existing:
            continue
        m.append({
            "capsule_id": cid,
            "purpose": (t.get("task") or "").strip() or f"MasterFirst task #{idx}",
            "source": "COMMAND:MasterFirst",
            "tool": (t.get("tool") or "Echo").strip(),
            "status": "pending",
            "verified": False,
            "confidence": 30,
            "timestamp": None,
            "created_ts": int(time.time()),
            "entry_points": [],
            "notes": t.get("notes",""),
        })
        created += 1
    save_memory(m)
    print(f"Created {created} TASK capsules from COMMAND:MasterFirst.")

if __name__ == "__main__":
    main()
