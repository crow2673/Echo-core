import json
from pathlib import Path

SRC = Path("echo_memory.json")
EVENTS = Path("echo_events.ndjson")
TASKS = Path("echo_tasks.ndjson")
BAD = Path("echo_bad_lines.txt")

events_n = tasks_n = bad_n = 0

EVENTS.write_text("")
TASKS.write_text("")
BAD.write_text("")

with SRC.open("r") as f, EVENTS.open("a") as fe, TASKS.open("a") as ft, BAD.open("a") as fb:
    for i, line in enumerate(f, 1):
        s = line.strip()
        if not s:
            continue
        try:
            obj = json.loads(s)
        except Exception as e:
            bad_n += 1
            fb.write(f"Line {i}: {e} | {s[:200]}\n")
            continue

        is_task = isinstance(obj, dict) and ("tasks" in obj or obj.get("type") == "task_update")
        if is_task:
            ft.write(json.dumps(obj) + "\n")
            tasks_n += 1
        else:
            fe.write(json.dumps(obj) + "\n")
            events_n += 1

print(f"Split complete:")
print(f"  events: {events_n} -> {EVENTS}")
print(f"  tasks:  {tasks_n} -> {TASKS}")
print(f"  bad:    {bad_n} -> {BAD}")
