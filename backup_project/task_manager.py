#!/usr/bin/env python3
import json
from pathlib import Path

MEMORY_FILE = Path("echo_memory.json")
WORKFLOW_ID = "WORKFLOW:CurrentGoal"

# Load memory
with open(MEMORY_FILE, "r") as f:
    memory = json.load(f)

# Find workflow capsule
capsule = next((c for c in memory if c.get("capsule_id") == WORKFLOW_ID), None)
if not capsule:
    print(f"No capsule found with ID {WORKFLOW_ID}")
    exit(1)

# Initialize tasks safely
if "tasks" not in capsule:
    capsule["tasks"] = []
    # Check if we have sub-tasks stored as dicts
    sub_tasks_capsule = next((c for c in memory if c.get("capsule_id") == WORKFLOW_ID + ":SubTasks"), None)
    if sub_tasks_capsule and "key_items" in sub_tasks_capsule:
        for t in sub_tasks_capsule.get("key_items", []):
            capsule["tasks"].append({"task": f"Use {t}", "tool": t, "status": "pending", "notes": ""})
    else:
        for t in capsule.get("key_items", []):
            if isinstance(t, dict):
                task_name = t.get("task", f"Use {t.get('tool','Unknown')}")
                tool_name = t.get("tool", str(t))
            else:
                task_name = f"Use {t}"
                tool_name = t
            capsule["tasks"].append({"task": task_name, "tool": tool_name, "status": "pending", "notes": ""})

# Print tasks
print(f"\n--- Tasks for {capsule['capsule_id']} ---")
for i, t in enumerate(capsule["tasks"], start=1):
    print(f"{i}) {t['task']} [Tool: {t['tool']}] Status: {t['status']}")

# Save updated memory
with open(MEMORY_FILE, "w") as f:
    json.dump(memory, f, indent=2)

print("\nTasks initialized/updated in Echo memory.")
