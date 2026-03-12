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

# Define sub-tasks for the current goal
sub_tasks = [
    {"task": "Check Outlier dashboard for active opportunities", "tool": "Outlier"},
    {"task": "Verify Hubstaff time tracking is running and accurate", "tool": "Hubstaff"},
    {"task": "Open browser for research or market checks", "tool": "browser"},
    {"task": "Log any task progress or blockers in Echo memory", "tool": "Echo"},
]

# Print structured task list
print(f"\n--- Sub-Tasks for {workflow['capsule_id']} ---")
for i, t in enumerate(sub_tasks, start=1):
    print(f"{i}) {t['task']} [Tool: {t['tool']}]")

# Optional: Save sub-tasks as a new capsule in memory
task_capsule = {
    "capsule_id": f"{WORKFLOW_ID}:SubTasks",
    "purpose": "Break down the current goal into immediate actionable steps",
    "key_items": [t["tool"] for t in sub_tasks],
    "entry_points": [t["tool"].lower() + "-app" for t in sub_tasks],
    "sensitivity": "internal",
    "parent_root": "ROOT:Workspace"
}

# Append to memory safely
if not any(c.get("capsule_id") == task_capsule["capsule_id"] for c in memory):
    memory.append(task_capsule)
    with open(MEMORY_FILE, "w") as f:
        json.dump(memory, f, indent=2)
    print("\nSub-tasks capsule stored in Echo memory.")
else:
    print("\nSub-tasks capsule already exists in Echo memory.")
