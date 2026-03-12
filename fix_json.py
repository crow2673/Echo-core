import json
from pathlib import Path
from collections import defaultdict
from datetime import date
from dateutil.parser import parse as date_parse

FILE = Path("echo_memory.json")
TASKS_KEY = "tasks"  # Adjust if tasks in specific entries

def load_ndjson():
    events = []
    if FILE.exists():
        with open(FILE, 'r') as f:
            for line_num, line in enumerate(f, 1):
                line = line.strip()
                if not line: continue
                try:
                    events.append(json.loads(line))
                except json.JSONDecodeError as e:
                    print(f"Line {line_num} skip: {e} | {line[:50]}...")
    return events

def find_tasks(events):
    tasks = defaultdict(lambda: defaultdict(list))
    for event in events:
        if isinstance(event, dict) and TASKS_KEY in event:
            for date_str, task_list in event[TASKS_KEY].items():
                try:
                    due = date_parse(date_str).date()
                    tasks[event.get('wf_id', 'unknown')][due].extend(task_list)
                except: pass
    return dict(tasks)

if __name__ == "__main__":
    events = load_ndjson()
    print(f"Loaded {len(events)} events. Sample:")
    print(json.dumps(events[:2], indent=2))
    tasks = find_tasks(events)
    print("Parsed tasks:", dict(tasks) or "None found (no 'tasks' key yet)")
