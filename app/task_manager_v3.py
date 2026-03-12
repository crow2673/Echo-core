import json
from pathlib import Path
from collections import defaultdict
from datetime import date, datetime
from dateutil.parser import parse as date_parse

TASKS_FILE = Path("echo_tasks.ndjson")

class TaskManager:
    def __init__(self):
        self.events = []
        self.tasks = defaultdict(lambda: defaultdict(list))
        self.load_all()

    def load_ndjson(self):
        self.events = []
        if TASKS_FILE.exists():
            with open(TASKS_FILE, 'r') as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        self.events.append(json.loads(line))
                    except json.JSONDecodeError:
                        pass
        # no print here (keeps chat clean)

    def parse_tasks(self):
        self.tasks.clear()
        for event in self.events:
            if isinstance(event, dict) and "tasks" in event:
                wf_id = event.get("wf_id", "default")
                for date_str, task_list in event["tasks"].items():
                    try:
                        due = date_parse(date_str).date()
                        self.tasks[wf_id][due].extend(task_list)
                    except ValueError:
                        pass
        return dict(self.tasks)

    def add_task(self, wf_id="default", due_date=None, description="New task", priority="medium"):
        if due_date is None:
            due_date = date.today()
        task = {
            "desc": description,
            "priority": priority,
            "status": "pending",
            "created": datetime.now().isoformat()
        }
        if wf_id not in self.tasks:
            self.tasks[wf_id] = defaultdict(list)
        self.tasks[wf_id][due_date].append(task)

        new_event = {
            "wf_id": wf_id,
            "tasks": {due_date.isoformat(): self.tasks[wf_id][due_date]},
            "type": "task_update"
        }
        with open(TASKS_FILE, 'a') as f:
            f.write(json.dumps(new_event) + '\n')

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
