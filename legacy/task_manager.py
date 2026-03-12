import json
from pathlib import Path
from collections import defaultdict
from datetime import date
from dateutil.parser import parse as date_parse  # Fixed import

MEMORY_FILE = Path("echo_memory.json")

class TaskManager:
    def __init__(self):
        self.tasks = defaultdict(lambda: defaultdict(list))
        self.memory = {}

    def load_memory(self):
        if MEMORY_FILE.exists():
            try:
                with open(MEMORY_FILE, 'r') as f:
                    self.memory = json.load(f)
            except (json.JSONDecodeError, FileNotFoundError) as e:
                print(f"Load error: {e}")
                self.memory = {}
        return self.memory

    def parse_tasks(self):
        tasks = defaultdict(lambda: defaultdict(list))
        for wf_id, data in self.memory.items():
            if isinstance(data, dict) and "tasks" in data:
                for date_str, task_data in data["tasks"].items():
                    if isinstance(task_data, dict):
                        try:
                            due_date = date_parse(date_str).date()
                            tasks[wf_id][due_date].append(task_data)
                        except ValueError:
                            print(f"Invalid date: {date_str}")
        self.tasks = tasks
        return dict(tasks)

    def save_memory(self, new_memory):
        with open(MEMORY_FILE, 'w') as f:
            json.dump(new_memory, f, indent=2)

# Test run
if __name__ == "__main__":
    tm = TaskManager()
    memory = tm.load_memory()
    parsed = tm.parse_tasks()
    print("Parsed tasks:", dict(parsed))  # Short output for tokens
