#!/usr/bin/env python3
import json
import argparse
from pathlib import Path
from datetime import datetime, timezone

MEMORY_FILE = Path("echo_memory.json")

def load_memory():
    if not MEMORY_FILE.exists() or MEMORY_FILE.stat().st_size == 0:
        return []
    try:
        data = json.loads(MEMORY_FILE.read_text())
        return data if isinstance(data, list) else []
    except json.JSONDecodeError:
        return []

def save_memory(memory):
    tmp = MEMORY_FILE.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(memory, indent=2))
    tmp.replace(MEMORY_FILE)

def main():
    p = argparse.ArgumentParser(description="Append a MESSAGE capsule to Echo memory.")
    p.add_argument("--from", dest="sender", default="andrew")
    p.add_argument("--text", required=True)
    args = p.parse_args()

    ts = datetime.now(timezone.utc).isoformat()
    msg_id = f"MESSAGE:{ts}"

    capsule = {
        "capsule_id": msg_id,
        "type": "message",
        "from": args.sender,
        "text": args.text,
        "status": "new",
        "created_at": ts,
    }

    memory = load_memory()
    memory.append(capsule)
    save_memory(memory)
    print(f"[+] queued {msg_id}")

if __name__ == "__main__":
    main()
