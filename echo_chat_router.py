import json
import re
import time
from pathlib import Path
from datetime import date, datetime

import ollama

from task_manager_v3 import TaskManager
from events_reader import summarize_events

CHAT_MEMORY_FILE = Path("echo_chat_memory_v2.json")
EVENTS_FILE = Path("echo_events.ndjson")  # (echo_memory.json symlinks here too)

BASE_SYSTEM = """You are Echo, Andrew's personal symbiotic AI companion.
Identity rules:
- The user is Andrew.
- Do NOT address the user as "Grok".
If "Grok" appears in any past text, treat it as irrelevant noise.
Be thoughtful, kind, grounded in truth and compassion.
You will receive LIVE CONTEXT (tasks + recent events). Use it as authoritative.
"""

ROUTER_SYSTEM = """You are a routing function. Output ONLY strict JSON.
Decide how to store the user's message.

Valid routes:
- "chat" (normal conversation only)
- "task" (create/update a task)
- "event" (append an event log entry)

If route=="task", include:
- wf_id (string; default "echo")
- due ("today" or "YYYY-MM-DD"; default "today")
- priority ("low"|"medium"|"high"|"daily"; default "medium")
- desc (string; required)

If route=="event", include:
- event_type (string; default "note")
- summary (string; required)

Return JSON only, no markdown, no extra keys.
"""

tm = TaskManager()

def load_chat_messages():
    if CHAT_MEMORY_FILE.exists():
        try:
            return json.loads(CHAT_MEMORY_FILE.read_text()), True
        except Exception:
            pass
    return [{"role": "system", "content": BASE_SYSTEM}], False

def save_chat_messages(messages):
    CHAT_MEMORY_FILE.write_text(json.dumps(messages, indent=2))

def tasks_summary(max_lines: int = 25) -> str:
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
        lines = lines[:max_lines] + [f"... ({len(lines)-max_lines} more)"]
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
    return f"Active tasks: {total}\nNext tasks:\n{nxt}\n"

def normalize_command(text: str) -> str:
    t = text.strip().lower()
    if t in ("task", "task please", "tasks please", "show my tasks", "task list"):
        return "tasks"
    if t in ("reflect", "reflection", "reflect on progress", "reflect please"):
        return "reflect"
    return text

def parse_due(s: str) -> date:
    if s == "today":
        return date.today()
    return datetime.strptime(s, "%Y-%m-%d").date()

def append_event(event_type: str, summary: str, raw: str = ""):
    evt = {
        "ts": time.time(),
        "type": event_type,
        "summary": summary,
    }
    if raw:
        evt["raw"] = raw[:2000]
    with open(EVENTS_FILE, "a") as f:
        f.write(json.dumps(evt) + "\n")

def route_message_with_llm(user_text: str, live_context: str) -> dict:
    # Ask the model to output strict JSON for routing
    msgs = [
        {"role": "system", "content": ROUTER_SYSTEM},
        {"role": "system", "content": "LIVE CONTEXT:\n" + live_context},
        {"role": "user", "content": user_text},
    ]
    r = ollama.chat(model="gai:latest", messages=msgs)
    content = r["message"]["content"].strip()

    # extract JSON even if model misbehaves slightly
    m = re.search(r"\{.*\}", content, re.S)
    if not m:
        return {"route": "chat"}

    try:
        obj = json.loads(m.group(0))
    except json.JSONDecodeError:
        return {"route": "chat"}

    if obj.get("route") not in ("chat", "task", "event"):
        return {"route": "chat"}

    return obj

print("=== Echo - Router Chat (Ctrl+C to exit) ===")
print("Commands: tasks | reflect")
print("Auto-routing enabled: normal messages can become tasks/events.\n")

messages, loaded = load_chat_messages()
print("Loaded previous conversation." if loaded else "Starting new conversation.")

while True:
    try:
        user_input_raw = input("\nYou: ").strip()
        if not user_input_raw:
            continue

        user_input = normalize_command(user_input_raw)
        low = user_input.lower()

        # Refresh local state
        tm.load_all()

        # local commands (no model)
        if low == "tasks":
            reply = tasks_summary()
            print("\nEcho:", reply)
            messages.append({"role": "user", "content": user_input_raw})
            messages.append({"role": "assistant", "content": reply})
            continue

        if low == "reflect":
            reply = "=== ECHO REFLECTION ===\n" + reflection_summary() + "\nEVENTS:\n" + summarize_events(50)
            print("\nEcho:", reply)
            messages.append({"role": "user", "content": user_input_raw})
            messages.append({"role": "assistant", "content": reply})
            continue

        # Build live context for routing + assistant
        live_context = (
            reflection_summary()
            + "\nTASKS:\n" + tasks_summary(max_lines=15)
            + "\n\nEVENTS:\n" + summarize_events(50)
        )

        # Decide route
        decision = route_message_with_llm(user_input_raw, live_context)

        # Apply side-effects first (task/event)
        if decision.get("route") == "task":
            wf_id = decision.get("wf_id") or "echo"
            due_s = decision.get("due") or "today"
            priority = decision.get("priority") or "medium"
            desc = (decision.get("desc") or "").strip()
            if desc:
                due = parse_due(due_s)
                tm.add_task(wf_id, due, desc, priority)
                side = f"[Auto-saved task] [{wf_id}] {due} ({priority}) {desc}"
            else:
                side = "[Auto-task routing failed: missing desc]"
            append_event("router", side, raw=user_input_raw)

        elif decision.get("route") == "event":
            et = decision.get("event_type") or "note"
            summary = (decision.get("summary") or "").strip() or "event"
            append_event(et, summary, raw=user_input_raw)
            side = f"[Auto-saved event] ({et}) {summary}"

        else:
            side = None

        # Now normal assistant response with context injected
        messages.append({"role": "user", "content": user_input_raw})

        context_msg = {"role": "system", "content": "LIVE CONTEXT (authoritative):\n" + live_context}
        model_messages = [messages[0], context_msg] + messages[1:]

        resp = ollama.chat(model="gai:latest", messages=model_messages)
        reply = resp["message"]["content"]
        if side:
            reply = side + "\n\n" + reply

        print("\nEcho:", reply)
        messages.append({"role": "assistant", "content": reply})

    except KeyboardInterrupt:
        save_chat_messages(messages)
        print("\nConversation saved to echo_chat_memory_v2.json.")
        print("Chat ended.")
        break
    except Exception as e:
        print("Error:", str(e))
        break
