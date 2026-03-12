#!/usr/bin/env python3
import json
from pathlib import Path

MEMORY_FILE = Path(__file__).parent / "echo_memory.json"

def load_memory():
    if MEMORY_FILE.exists():
        with open(MEMORY_FILE, "r") as f:
            return json.load(f)
    return []

def audit_echo():
    memory = load_memory()
    completed = []
    pending = []
    queued = []

    for capsule in memory:
        purpose = capsule.get("purpose", "Unknown")
        verified = capsule.get("verified", False)
        timestamp = capsule.get("timestamp", "N/A")

        if verified:
            completed.append((purpose, capsule.get("capsule_id"), timestamp))
        else:
            pending.append((purpose, capsule.get("capsule_id"), timestamp))
        
        if "WORKFLOW" in purpose or "COMMAND" in purpose:
            queued.append((purpose, capsule.get("capsule_id"), verified))

    print("\n=== Echo Audit Report ===\n")
    print(f"Total capsules: {len(memory)}\n")

    print("--- Completed ---")
    for c in completed:
        print(f"{c[0]} | ID: {c[1]} | Timestamp: {c[2]}")

    print("\n--- Pending ---")
    for p in pending:
        print(f"{p[0]} | ID: {p[1]} | Timestamp: {p[2]}")

    print("\n--- Queued Workflows/Commands ---")
    for q in queued:
        status = "Verified" if q[2] else "Pending"
        print(f"{q[0]} | ID: {q[1]} | Status: {status}")

if __name__ == "__main__":
    audit_echo()
