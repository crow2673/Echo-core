import json
from pathlib import Path

memory_file = Path.home() / "Echo/echo_memory.json"

if memory_file.exists():
    with open(memory_file) as f:
        memory = json.load(f)
else:
    memory = []

pending_workflows = [capsule for capsule in memory if capsule.get("verified") is not True]

task_summary = {
    "total_capsules": len(memory),
    "pending_workflows": len(pending_workflows),
    "timestamp": __import__('datetime').datetime.now().isoformat()
}

log_file = Path.home() / "Echo/always_on_task_log.json"
if not log_file.exists():
    log_file.write_text("[]")

with open(log_file, "r+") as f:
    try:
        data = json.load(f)
    except json.JSONDecodeError:
        data = []
    data.append(task_summary)
    f.seek(0)
    json.dump(data, f, indent=2)
    f.truncate()
