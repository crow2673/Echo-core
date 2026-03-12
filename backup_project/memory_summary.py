#!/usr/bin/env python3
import json
from pathlib import Path

MEMORY_FILE = Path("echo_memory.json")

with open(MEMORY_FILE, "r") as f:
    memory = json.load(f)

# Group by parent_root
grouped = {}
for cap in memory:
    parent = cap.get("parent_root", "UNGROUPED")
    grouped.setdefault(parent, []).append(cap)

print("\n--- Echo Memory Summary by ROOT ---")
for parent, capsules in grouped.items():
    print(f"\nParent: {parent}")
    for c in capsules:
        print(f"  - {c['capsule_id']} | Purpose: {c.get('purpose', '')} | Sensitivity: {c.get('sensitivity', '')}")
