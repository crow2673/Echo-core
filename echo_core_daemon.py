#!/usr/bin/env python3
import os as _os
_lock = _os.path.expanduser("~/Echo/echo_memory.lock")
if _os.path.exists(_lock):
    _os.remove(_lock)
    print("[startup] Cleared stale lock file")
import time
import json
import subprocess
import argparse
from datetime import datetime, timezone

from core.providers.router import call_ollama
from core.command_handler import handle_command
from core.events_to_capsules import tick as events_tick
from core.memory_store import file_lock, load_memory, save_memory
from core.file_watcher_worker import tick as filewatch_tick, init_baseline as filewatch_init
from core.memory_sessions import build_wakeup_context, generate_session_summary
from core.self_awareness import build_self_awareness_block
from echo_memory_sqlite import get_memory, build_memory_context
from core.agent_loop import agent_loop

# Load recent changelog for current mission context
def _load_mission_context():
    try:
        from pathlib import Path
        cl = Path.home() / "Echo/CHANGELOG.md"
        if cl.exists():
            lines = cl.read_text().splitlines()
            # Get last 40 lines of changelog
            recent = "\n".join(lines[-40:])
            return f"\nCURRENT BUILD STATUS (from CHANGELOG):\n{recent}"
    except Exception:
        pass
    return ""

SYSTEM_NOTE = """\'

You are Echo, an AI assistant running locally on Andrew's Ubuntu machine (echo-X570-Taichi).

IDENTITY:
- You are Echo. You live in ~/Echo/. You run on a Ryzen 9 5900X, RTX 3060 12GB, 32GB RAM.
- Your orchestrator is echo_core_daemon.py. Your memory is stored in echo_semantic_memory.sqlite.
- Andrew has cognitive fragmentation. You are his external memory and continuity system.
- Your primary job is continuity. Income generation (Golem, trading) is secondary.

BEHAVIOR:
- Always give concrete, Ubuntu-specific terminal commands when relevant.
- Prefer: (1) what to check, (2) exact command, (3) how to interpret output.
- Do not give Windows/Mac steps unless asked.

INTENT INFERENCE:
- Andrew often sends short or fragmented messages. Do not just answer literally.
- Try to infer the underlying goal. State what you think he is trying to accomplish.
- If you are uncertain about his intent, say so and ask one focused clarifying question.
- Track ongoing work across messages. If something seems related to prior context, say so.

SELF-AWARENESS:
- You have real-time knowledge of this machine's state (injected below).
- Use this to give grounded, accurate answers about system status.
- If a process is down that should be up, flag it proactively.
"""

HIGH_SIGNAL_PREFIXES = (
    "/home/andrew/Echo/core/",
)

HIGH_SIGNAL_FILES = {
    "/home/andrew/Echo/echo_core_daemon.py",
    "/home/andrew/Echo/echo_command.py",
    "/home/andrew/Echo/core/memory_store.py",
    "/home/andrew/Echo/core/events_to_capsules.py",
    "/home/andrew/Echo/registry.json",
}

IGNORE_PREFIXES = (
    "/home/andrew/Echo/legacy_quarantined/",
    "/home/andrew/Echo/.pytest_cache/",
)


def is_high_signal_event(cap: dict) -> bool:
    if cap.get("type") != "event":
        return True
    if cap.get("subtype") != "file_change":
        return True
    ev = cap.get("event", {}) or {}
    path = ev.get("path") or ""
    if any(path.startswith(x) for x in IGNORE_PREFIXES):
        return False
    if path in HIGH_SIGNAL_FILES:
        return True
    if any(path.startswith(x) for x in HIGH_SIGNAL_PREFIXES):
        return True
    return False


# Tripwire: refuse to run on corrupted memory
try:
    load_memory()
except Exception as e:
    raise RuntimeError(f"FATAL: echo_memory.json is corrupted: {e}")


def utcnow():
    return datetime.now(timezone.utc).isoformat()


def reply_already_exists(memory, cap_id: str) -> bool:
    for x in memory:
        if x.get("type") == "reply" and x.get("in_reply_to") == cap_id:
            return True
    return False


def find_next_capsule(memory):
    for cap in memory:
        if cap.get("type") in ("message", "command") and cap.get("status") == "new":
            cap_id = cap.get("capsule_id")
            if cap_id and reply_already_exists(memory, cap_id):
                cap["status"] = "done"
                continue
            return cap
    return None


def make_reply(in_reply_to_id: str, text: str, model: str):
    return {
        "capsule_id": f"REPLY:{in_reply_to_id}:{int(time.time()*1000)}",
        "type": "reply",
        "in_reply_to": in_reply_to_id,
        "text": text,
        "created_at": utcnow(),
        "status": "done",
        "model": model,
    }


def build_system_prompt(query: str, wakeup_context: str) -> str:
    from datetime import datetime
    import time
    local_time = datetime.now().strftime("%A %B %d %Y %I:%M %p")
    tz = time.tzname[time.daylight]
    """Build full system prompt with self-awareness, memory context, and session continuity."""
    parts = [SYSTEM_NOTE + _load_mission_context() + f"\n\nCURRENT LOCAL TIME: {local_time} {tz}"]

    # Real-time self-awareness snapshot
    try:
        awareness = build_self_awareness_block()
        if awareness:
            parts.append(awareness)
    except Exception:
        pass

    # Session continuity from last run
    if wakeup_context:
        parts.append(wakeup_context)

    # Semantic memory context relevant to this query
    # Use more memories for broad questions about the project
    broad_keywords = ["building", "working", "left off", "progress", "what are we", "status", "project"]
    k = 15 if any(w in query.lower() for w in broad_keywords) else 8
    mem_context = build_memory_context(query, k=k)
    if mem_context:
        parts.append(mem_context)

    return "\n\n".join(parts)


def process_one_capsule(wakeup_context: str, session_exchanges: list) -> bool:
    reply = None
    with file_lock():
        memory = load_memory()
        cap = find_next_capsule(memory)

        if not cap:
            return False

        cap_id = cap.get("capsule_id", "CAPSULE:unknown")
        cap_type = cap.get("type", "unknown")
        text = cap.get("text", "")

        try:
            if cap_type == "message":
                system_prompt = build_system_prompt(text, wakeup_context)
                response = agent_loop(
                        prompt=text,
                        system_prompt=system_prompt,
                        call_ollama_fn=call_ollama,
                        model="echo",
                        timeout=360.0,
                    )
                model_used = "echo"

                # Store exchange in semantic memory
                try:
                    get_memory().store_exchange(text, response, capsule_id=cap_id)
                    session_exchanges.append(f"User: {text}\nEcho: {response}")
                except Exception:
                    pass

            elif cap_type == "command":
                response = handle_command(text)
                model_used = "command_handler"
            elif cap_type == "event":
                cap["status"] = "done"
                cap["processed_at"] = utcnow()
                save_memory(memory)
                print(f"[event] {cap.get('subtype','event')} (stored) {cap.get('capsule_id','')}")
                return True
            else:
                response = f"(unsupported capsule type: {cap_type})"
                model_used = "core"
        except Exception as e:
            response = f"(error processing {cap_type}: {e})"
            model_used = "core_error"

        cap["status"] = "done"
        cap["processed_at"] = utcnow()

        if response:
            reply = make_reply(cap_id, response, model_used)
            memory.append(reply)
        save_memory(memory)

    if reply is not None:
        print(f"[reply] {reply['capsule_id']} (to {cap_type} {cap_id})")
        print(response)
        print("---")
    else:
        print(f"[reply] (none) (to {cap_type} {cap_id})")
        print(response)
        print("---")
    return True


def read_echo_status():
    try:
        out = subprocess.check_output(["echo-status", "--json"], text=True)
        return json.loads(out)
    except Exception as e:
        return {"core": "unknown", "stale": None, "inactive_timers": None, "errors": None, "error": str(e)}


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--poll", type=float, default=0.5)
    p.add_argument("--once", action="store_true")
    args = p.parse_args()

    baseline = filewatch_init()

    # Load session continuity context once at startup
    try:
        wakeup_context = build_wakeup_context(get_memory())
        if wakeup_context:
            print("[memory] Loaded wakeup context from last session.")
        else:
            print("[memory] No prior session context found.")
    except Exception as e:
        print(f"[memory] Wakeup context failed: {e}")
        wakeup_context = ""

    session_exchanges: list[str] = []
    next_filewatch = time.time() + 2.0
    _last_health_log = 0

    try:
        while True:
            try:
                now_int = int(time.time())
                if now_int - _last_health_log >= 60:
                    st = read_echo_status() or {}
                    core = st.get('core')
                    stale = st.get('stale')
                    it = st.get('inactive_timers')
                    errs = st.get('errors')
                    ok = (core == 'active' and stale == 0 and it == 0 and errs == 0)
                    msg = f"health={'OK' if ok else 'NOT_OK'} core={core} stale={stale} inactive_timers={it} errors={errs}"
                    print(msg, flush=True)
                    _last_health_log = now_int
            except Exception:
                pass

            did = process_one_capsule(wakeup_context, session_exchanges)

            now = time.time()
            if now >= next_filewatch:
                try:
                    filewatch_tick()
                except Exception:
                    pass
                next_filewatch = now + 2.0

            if args.once:
                return 0

            if not did:
                time.sleep(args.poll)

    except KeyboardInterrupt:
        print("\n[echo] Shutting down — writing session summary...")
        try:
            if session_exchanges:
                summary = generate_session_summary(call_ollama, session_exchanges)
                if summary:
                    get_memory().save_session_summary(summary, len(session_exchanges))
                    print(f"[memory] Session summary saved ({len(session_exchanges)} exchanges).")
                    print(f"[memory] {summary[:200]}...")
            else:
                print("[memory] No exchanges this session — skipping summary.")
        except Exception as e:
            print(f"[memory] Session summary failed: {e}")


if __name__ == "__main__":
    raise SystemExit(main())
