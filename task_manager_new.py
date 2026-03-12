from pathlib import Path
from collections import defaultdict
from datetime import date
from typing import Dict, Any
import json
from dateutil.parser import parse

MEMORY_FILE = Path("echo_memory.json")

class TaskManager:
    def __init__(self):
        self.tasks = defaultdict(lambda: defaultdict(list))

    def load_memory(self) -> Dict[str, Any]:
        if not MEMORY_FILE.exists():
            return {}
        try:
            return json.loads(MEMORY_FILE.read_text())
        except json.JSONDecodeError as e:
            print(f"JSON Error: {e}")
            return {}

    def parse_tasks(self, memory: Dict[str, Any]) -> Dict[str, Dict[date, list]]:
        tasks = defaultdict(lambda: defaultdict(list))
        for wf_id, data in memory.items():
            if not isinstance(data, dict) or "tasks" not in data:
                continue
            for date_str, task_data in data["tasks"].items():
                if not isinstance(task_data, dict):
                    continue
                try:
                    due_date = parse(date_str).date()
                    tasks[wf_id][due_date].append(task_data)
                except ValueError:
                    pass  # Silent skip
        self.tasks = tasks  # Populate class state
        return dict(tasks)

    def add_task(self, workflow_id: str, due_date: date, task_data: Dict[str, Any]):
        self.tasks[workflow_id][due_date].append(task_data)

if __name__ == "__main__":
    tm = TaskManager()
    print("=== Test with Mock Data ===")
    memory = tm.load_memory()
    parsed = tm.parse_tasks(memory)
    print("Memory loaded:", memory)
    print("Parsed Tasks:", parsed)
    print("self.tasks:", dict(tm.tasks))
    print("=== Test Complete ===")

def to_plain_dict(self) -> Dict:
    def convert(d):
        if isinstance(d, defaultdict):
            return {k: convert(v) for k, v in d.items()}
        return d
    return convert(self.tasks)

def save_tasks(self, memory: Dict[str, Any]):
    # Rebuild memory from tasks (reverse)
    new_memory = {}
    for wf, dates in self.tasks.items():
        new_memory[wf] = {'tasks': {d.isoformat(): t for d, ts in dates.items() for t in ts}}
    MEMORY_FILE.write_text(json.dumps(new_memory, indent=2))

# Demo in __main__
if __name__ == "__main__":
    ...
    print("Plain tasks:", tm.to_plain_dict())
    tm.add_task("Demo", date.today(), {"name": "New Task"})
    print("After add:", tm.to_plain_dict())
    # tm.save_tasks({})  # Uncomment to persist
