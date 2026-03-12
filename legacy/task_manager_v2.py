import json
from pathlib import Path
from collections import defaultdict
from datetime import date, datetime
from dateutil.parser import parse as date_parse

MEMORY_FILE = Path("echo_memory.json")
FIXED_FILE = Path("echo_memory_fixed.json")  # Optional clean version

class TaskManager:
    def __init__(self):
        self.events = []
        self.tasks = defaultdict(lambda: defaultdict(list))
        self.load_all()

    def load_ndjson(self):
        self.events = []
        if MEMORY_FILE.exists():
            with open(MEMORY_FILE, 'r') as f:
                for line_num, line in enumerate(f, 1):
                    line = line.strip()
                    if line:
                        try:
                            self.events.append(json.loads(line))
                        except json.JSONDecodeError:
                            pass  # Silent skip
        print(f"Loaded {len(self.events)} events")

    def parse_tasks(self):
        self.tasks.clear()
        for event in self.events:
            if isinstance(event, dict) and "tasks" in event:
                wf_id = event.get("wf_id", "default")
                for date_str, task_list in event["tasks"].items():
                    try:
                        due = date_parse(date_str).date()
                        self.tasks[wf_id][due].extend(task_list)
                    except ValueError: pass
        return dict(self.tasks)

    def add_task(self, wf_id="default", due_date=None, description="New task", priority="medium"):
        if due_date is None:
            due_date = date.today()
        task = {"desc": description, "priority": priority, "status": "pending", "created": datetime.now().isoformat()}
        if wf_id not in self.tasks:
            self.tasks[wf_id] = defaultdict(list)
        self.tasks[wf_id][due_date].append(task)
        # Append as new event line to NDJSON
        new_event = {"wf_id": wf_id, "tasks": {due_date.isoformat(): self.tasks[wf_id][due_date]}, "type": "task_update"}
        with open(MEMORY_FILE, 'a') as f:
            f.write(json.dumps(new_event) + '\n')
        print(f"Added: {description} due {due_date}")

    def list_tasks(self):
        parsed = self.parse_tasks()
        for wf, dates in parsed.items():
            print(f"\n{wf}:")
            for d, ts in dates.items():
                print(f"  {d}: {len(ts)} tasks")

    def load_all(self):
        self.load_ndjson()
        self.parse_tasks()

if __name__ == "__main__":
    tm = TaskManager()
    tm.list_tasks()
    print("\n--- Add sample task? Uncomment below ---")
    # tm.add_task("personal", date(2024,10,1), "Test Echo integration")
