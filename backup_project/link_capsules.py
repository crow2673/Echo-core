#!/usr/bin/env python3
import json
from pathlib import Path

MEMORY_FILE = Path("echo_memory.json")
ROOT_CAPSULE_ID = "ROOT:Workspace"

# Load memory
with open(MEMORY_FILE, "r") as f:
    memory = json.load(f)

# Add parent link if missing
for capsule in memory:
    if "parent_root" not in capsule:
        capsule["parent_root"] = ROOT_CAPSULE_ID

# Save memory
with open(MEMORY_FILE, "w") as f:
    json.dump(memory, f, indent=2)

print("All capsules linked to ROOT:Workspace.")
for cap in memory:
    print(f"{cap['capsule_id']} -> parent: {cap['parent_root']}")
