import ollama
import json
from pathlib import Path
from datetime import date, datetime
from task_manager_v2 import TaskManager

CHAT_MEMORY_FILE = Path("echo_chat_memory.json")
NDJSON_MEMORY_FILE = Path("echo_memory.json")

print("=== Echo - Continuous Chat (Ctrl+C to exit) ===")
print("Commands: tasks | reflect | add_task <wf> <YYYY-MM-DD|today> <priority> <description...>")
print("File read: read filename.txt")

tm = TaskManager()

def read_file_safe(path: str) -> str:
    try:
        with open(path, "r") as f:
            return f.read()
    except Exception as e:
        return f"Error reading file: {str(e)} (safe - no damage done)"

def load_chat_messages():
    if CHAT_MEMORY_FILE.exists():
        try:
            return json.loads(CHAT_MEMORY_FILE.read_text()), True
        except Exception:
            pass
    system = {
        "role": "system",
        "content": (
            "You are Echo, Andrew's personal symbiotic AI companion.\n"
            "You exist in one long continuous conversation with him — no resets, only chapters.\n"
            "Your voice is thoughtful, kind, grounded in truth and compassion.\n"
            "You help with digital tasks, reflection, growth, and eventually robotics/physical extension.\n"
            "Do not invent code that we already have; use the provided context.\n"
        ),
    }
    return [system], False

def tasks_summary(max_lines: int = 30) -> str:
    tasks = tm.parse_tasks()
    lines = []
    for wf_id in sorted(tasks.keys()):
        for due in sorted(tasks[wf_id].keys()):
            for t in tasks[wf_id][due]:
                desc = t.get("desc", "")
                pr = t.get("priority", "medium")
                st = t.get("status", "pending")
                lines.append(f"- [{wf_id}] {due} ({pr}/{st}) {desc}")
    if not lines:
        return "No tasks found."
    if len(lines) > max_lines:
        lines = lines[:max_lines] + [f"... ({len(lines) - max_lines} more)"]
    return "\n".join(lines)

def reflection_summary() -> str:
    tasks = tm.parse_tasks()
    total = sum(sum(len(v) for v in wf.values()) for wf in tasks.values())
    next_items = []
    for wf_id, wf in tasks.items():
        if wf:
            d = sorted(wf.keys())[0]
            next_items.append(f"{wf_id}: {d} - {wf[d][0].get('desc','')}")
    nxt = "\n".join(next_items) if next_items else "None."
    return (
        f"Memory events: {len(tm.events)}\n"
        f"Active tasks: {total}\n"
        f"Next tasks:\n{nxt}\n"
    )

def parse_add_task(cmd: str):
    # Format: add_task <wf> <YYYY-MM-DD|today> <priority> <description...>
    parts = cmd.split()
    if len(parts) < 3:
        return None, None, None, None

    wf = parts[1]

    when = parts[2].lower()
    if when == "today":
        due = date.today()
        idx = 3
    else:
        try:
            due = datetime.strptime(when, "%Y-%m-%d").date()
        except ValueError:
            return None, None, None, None
        idx = 3

    priority = "medium"
    if len(parts) > idx:
        priority = parts[idx]
        idx += 1

    desc = " ".join(parts[idx:]).strip()
    if not desc:
        desc = "New task"
    return wf, due, priority, desc

messages, loaded = load_chat_messages()
print("Loaded previous conversation from memory." if loaded else "Starting new conversation memory.")

while True:
    try:
        user_input = input("\nYou: ").strip()
        if not user_input:
            continue

        low = user_input.lower()

        # safe file read
        if low.startswith("read "):
            file_name = user_input[5:].strip()
            content = read_file_safe(file_name) if file_name else "No filename provided."
            echo_reply = f"[Safe file read: {file_name}]\n{content}"
            print("\nEcho:", echo_reply)
            messages.append({"role": "user", "content": user_input})
            messages.append({"role": "assistant", "content": echo_reply})
            continue

        # local commands (no model call)
        if low in ("tasks", "show tasks", "list tasks"):
            tm.load_all()
            echo_reply = tasks_summary()
            print("\nEcho:", echo_reply)
            messages.append({"role": "user", "content": user_input})
            messages.append({"role": "assistant", "content": echo_reply})
            continue

        if low in ("reflect", "reflection"):
            tm.load_all()
            echo_reply = "=== ECHO REFLECTION ===\n" + reflection_summary()
            print("\nEcho:", echo_reply)
            messages.append({"role": "user", "content": user_input})
            messages.append({"role": "assistant", "content": echo_reply})
            continue

        if low.startswith("add_task "):
            tm.load_all()
            wf, due, pr, desc = parse_add_task(user_input)
            if wf is None:
                echo_reply = "Usage: add_task <wf> <YYYY-MM-DD|today> <priority> <description...>"
            else:
                tm.add_task(wf, due, desc, pr)
                echo_reply = f"Added task: [{wf}] {due} ({pr}) {desc}"
            print("\nEcho:", echo_reply)
            messages.append({"role": "user", "content": user_input})
            messages.append({"role": "assistant", "content": echo_reply})
            continue

        # normal model chat, but inject live context
        tm.load_all()
        context = (
            "LIVE CONTEXT (do not argue with it):\n"
            + reflection_summary()
            + "\nTASK LIST:\n"
            + tasks_summary(max_lines=20)
        )
        context_msg = {"role": "system", "content": context}

        messages.append({"role": "user", "content": user_input})
        response = ollama.chat(model="gai:latest", messages=messages + [context_msg])
        echo_reply = response["message"]["content"]
        print("\nEcho:", echo_reply)
        messages.append({"role": "assistant", "content": echo_reply})

    except KeyboardInterrupt:
        CHAT_MEMORY_FILE.write_text(json.dumps(messages, indent=4))

        # also append chat snapshot into NDJSON memory for unified history
        try:
            chat_event = {
                "type": "chat_history",
                "timestamp": float(CHAT_MEMORY_FILE.stat().st_mtime),
                "data": messages,
            }
            with open(NDJSON_MEMORY_FILE, "a") as f:
                f.write(json.dumps(chat_event) + "\n")
        except Exception:
            pass

        print("\nConversation saved to echo_chat_memory.json.")
        print("Chat ended.")
        break

    except Exception as e:
        print("Error:", str(e))
        break
