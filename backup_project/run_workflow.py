#!/usr/bin/env python3
import json
from pathlib import Path

MEMORY_FILE = Path("echo_memory.json")
WORKFLOW_ID = "WORKFLOW:CurrentGoal"

# Load memory
with open(MEMORY_FILE, "r") as f:
    memory = json.load(f)

# Find workflow capsule
workflow = next((c for c in memory if c.get("capsule_id") == WORKFLOW_ID), None)

if not workflow:
    print(f"No capsule found with ID {WORKFLOW_ID}")
    exit(1)

# Display structured prompt for immediate action
print("\n--- Echo Workflow Activation ---")
print(f"Capsule: {workflow['capsule_id']}")
print(f"Purpose: {workflow.get('purpose', '')}")
print(f"Key items: {', '.join(workflow.get('key_items', []))}")
print(f"Entry points: {', '.join(workflow.get('entry_points', []))}")
print("\nSuggested Next Step:")
print("  1) Review key items (tools) needed for the goal.")
print("  2) Start executing the workflow with minimal dependencies.")
print("  3) Log your progress back into Echo memory using compressed capsules.")
