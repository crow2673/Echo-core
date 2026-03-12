import json, re, time
from pathlib import Path
from datetime import date, datetime

import ollama
from task_manager_v3 import TaskManager
from events_reader import summarize_events

CHAT_MEMORY_FILE = Path("echo_chat_memory_v2.json")
EVENTS_FILE = Path("echo_events.ndjson")
STATE_FILE = Path("router_state.json")

BASE_SYSTEM = """You are Echo, Andrew's personal symbiotic AI companion.
- The user is Andrew. Do NOT address him as "Grok".
- Be grounded and practical.
You will receive LIVE CONTEXT (tasks + recent events). Treat it as authoritative.
"""

ROUTER_SYSTEM = """Output ONLY strict JSON.
Route user message into:
- chat
- task (wf_id, due[today|YYYY-MM-DD], priority[low|medium|high|daily], desc)
- event (event_type, summary)
Return JSON only.
"""

def load_json(path, default):
    try:
        if path.exists():
            return json.loads(path.read_text())
    except Exception:
        pass
    return default

def save_json(path, obj):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, indent=2))

def append_event(event_type: str, summary: str, raw: str = ""):
    evt = {"ts": time.time(), "type": event_type, "summary": summary}
    if raw:
        evt["raw"] = raw[:2000]
    with open(EVENTS_FILE, "a") as f:
        f.write(json.dumps(evt) + "\n")

def parse_due(s: str) -> date:
    s = (s or "today").strip().lower()
    if s == "today":
        return date.today()
    return datetime.strptime(s, "%Y-%m-%d").date()

def tasks_summary(tm: TaskManager, max_lines=25):
    tasks = tm.parse_tasks()
    lines = []
    for wf_id in sorted(tasks.keys()):
        for due in sorted(tasks[wf_id].keys()):
            for t in tasks[wf_id][due]:
                lines.append(f"- [{wf_id}] {due} ({t.get('priority','medium')}/{t.get('status','pending')}) {t.get('desc','')}")
    return "\n".join(lines[:max_lines]) if lines else "No tasks found."

def reflection_summary(tm: TaskManager):
    tasks = tm.parse_tasks()
    total = sum(sum(len(v) for v in wf.values()) for wf in tasks.values())
    next_items = []
    for wf_id, wf in tasks.items():
        if wf:
            d = sorted(wf.keys())[0]
            next_items.append(f"{wf_id}: {d} - {wf[d][0].get('desc','')}")
    nxt = "\n".join(next_items) if next_items else "None."
    return f"Active tasks: {total}\nNext tasks:\n{nxt}\n"

def route_with_llm(user_text: str, live_context: str) -> dict:
    msgs = [
        {"role": "system", "content": ROUTER_SYSTEM},
        {"role": "system", "content": "LIVE CONTEXT:\n" + live_context},
        {"role": "user", "content": user_text},
    ]
    r = ollama.chat(model="gai:latest", messages=msgs)
    content = r["message"]["content"].strip()
    m = re.search(r"\{.*\}", content, re.S)
    if not m:
        return {"route": "chat"}
    try:
        obj = json.loads(m.group(0))
    except Exception:
        return {"route": "chat"}
    if obj.get("route") not in ("chat", "task", "event"):
        return {"route": "chat"}
    return obj

print("=== Echo - Main Chat (modes) (Ctrl+C to exit) ===")
print("Commands: tasks | reflect | mode chat | mode agent")
print("Prefixes: task: <desc> | note: <summary> (explicit routing)\n")

tm = TaskManager()
messages = load_json(CHAT_MEMORY_FILE, [{"role": "system", "content": BASE_SYSTEM}])
state = load_json(STATE_FILE, {"mode": "chat"})  # default chat mode
pending = None  # pending task confirm

while True:
    try:
        user = input("\nYou: ").strip()
        if not user:
            continue

        low = user.lower().strip()

        # pending confirmation handling
        if pending:
            if low in ("yes","y"):
                d = pending
                tm.add_task(d["wf_id"], d["due"], d["desc"], d["priority"])
                append_event("router", "task_confirmed_saved", raw=d["raw"])
                print(f"\nEcho: Saved task: [{d['wf_id']}] {d['due']} ({d['priority']}) {d['desc']}")
                pending = None
                continue
            if low in ("no","n","cancel"):
                print("\nEcho: Okay—won’t save that as a task.")
                append_event("router", "task_confirmed_discarded", raw=pending["raw"])
                pending = None
                continue
            if low.startswith("edit "):
                new_desc = user[5:].strip()
                if new_desc:
                    d = pending
                    tm.add_task(d["wf_id"], d["due"], new_desc, d["priority"])
                    append_event("router", "task_confirmed_saved_edited", raw=d["raw"])
                    print(f"\nEcho: Saved edited task: [{d['wf_id']}] {d['due']} ({d['priority']}) {new_desc}")
                    pending = None
                    continue
            print("\nEcho: Reply with yes / no / edit <new description>")
            continue

        # mode switching
        if low.startswith("mode "):
            mode = low.split(" ", 1)[1].strip()
            if mode in ("chat","agent"):
                state["mode"] = mode
                save_json(STATE_FILE, state)
                print(f"\nEcho: Mode set to {mode.upper()}.")
            else:
                print("\nEcho: Use: mode chat | mode agent")
            continue

        # local commands
        tm.load_all()
        if low in ("tasks","show tasks","list tasks"):
            print("\nEcho:", tasks_summary(tm))
            continue
        if low in ("reflect","reflection"):
            print("\nEcho: === ECHO REFLECTION ===")
            print(reflection_summary(tm) + "\nEVENTS:\n" + summarize_events(50))
            continue

        # explicit routing prefixes (work in any mode)
        if low.startswith("task:"):
            desc = user.split(":",1)[1].strip()
            if not desc:
                print("\nEcho: task: needs a description.")
                continue
            pending = {
                "raw": user,
                "wf_id": "echo",
                "due": date.today(),
                "priority": "medium",
                "desc": desc
            }
            print("\nEcho: Confirm save task? (yes/no/edit ...)")
            print(f"  wf: echo\n  due: today\n  priority: medium\n  desc: {desc}")
            continue

        if low.startswith("note:"):
            summary = user.split(":",1)[1].strip()
            if not summary:
                print("\nEcho: note: needs a summary.")
                continue
            append_event("note", summary, raw=user)
            print("\nEcho: Logged note.")
            continue

        # CHAT mode: do NOT auto-route; just talk
        live_context = (
            reflection_summary(tm)
            + "\nTASKS:\n" + tasks_summary(tm, max_lines=15)
            + "\n\nEVENTS:\n" + summarize_events(50)
        )

        messages.append({"role": "user", "content": user})

        if state.get("mode") == "agent":
            # agent mode: use router, but confirm tasks
            decision = route_with_llm(user, live_context)

            if decision.get("route") == "task":
                desc = (decision.get("desc") or "").strip()
                if not desc:
                    # don't bug you with missing desc
                    decision = {"route":"chat"}
                else:
                    wf_id = decision.get("wf_id") or "echo"
                    due = parse_due(decision.get("due") or "today")
                    pr = decision.get("priority") or "medium"
                    pending = {"raw": user, "wf_id": wf_id, "due": due, "priority": pr, "desc": desc}
                    print("\nEcho: I think this is a NEW task. Confirm save? (yes/no/edit ...)")
                    print(f"  wf: {wf_id}\n  due: {due}\n  priority: {pr}\n  desc: {desc}")
                    continue

            if decision.get("route") == "event":
                summary = (decision.get("summary") or "").strip()
                if summary:
                    append_event(decision.get("event_type") or "note", summary, raw=user)
                # don't interrupt chat with it

        # normal assistant response
        context_msg = {"role": "system", "content": "LIVE CONTEXT (authoritative):\n" + live_context}
        resp = ollama.chat(model="gai:latest", messages=[messages[0], context_msg] + messages[1:])
        reply = resp["message"]["content"]
        print("\nEcho:", reply)
        messages.append({"role": "assistant", "content": reply})

    except KeyboardInterrupt:
        save_json(CHAT_MEMORY_FILE, messages)
        print("\nConversation saved to echo_chat_memory_v2.json.")
        print("Chat ended.")
        break
