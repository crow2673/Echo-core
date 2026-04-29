#!/usr/bin/env python3
"""echo_core_daemon.py — Echo's persistent core orchestrator.
Processes capsules (messages/events) from Andrew, replies via Ollama.
Runs as echo-core.service (Type=simple, Restart=always).
"""
import argparse
import json
import os
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

BASE = Path(__file__).resolve().parent
_lock = BASE / "echo_memory.lock"

# Clear stale lock on startup
if _lock.exists():
    try:
        _lock.unlink()
        print("[startup] Cleared stale lock file", flush=True)
    except Exception:
        pass

sys.path.insert(0, str(BASE))

from core.providers.router import call_ollama
from core.command_handler import handle_command
from core.events_to_capsules import tick

SYSTEM_NOTE = (
    "\n\nYou are Echo, an AI assistant running locally on Andrew's Ubuntu machine (echo-X570-Taichi).\n\n"
    "IDENTITY:\n"
    "- You are Echo. You live in ~/Echo/. You run on a Ryzen 9 5900X, RTX 3060 12GB, 32GB RAM.\n"
    "- Your orchestrator is echo_core_daemon.py. Your memory is stored in echo_semantic_memory.sqlite.\n"
    "- Andrew has cognitive fragmentation. You are his external memory and continuity system.\n"
    "- Your primary job is continuity. Income generation (Golem, trading) is secondary.\n\n"
    "BEHAVIOR:\n"
    "- Always give concrete, Ubuntu-specific terminal commands when relevant.\n"
    "- Prefer: (1) what to check, (2) exact command, (3) how to interpret output.\n"
    "- Do not give Windows/Mac steps unless asked.\n\n"
    "INTENT INFERENCE:\n"
    "- Andrew often sends short or fragmented messages. Do not just answer literally.\n"
    "- Try to infer the underlying goal. State what you think he is trying to accomplish.\n"
    "- If you are uncertain about his intent, say so and ask one focused clarifying question.\n"
    "- Track ongoing work across messages. If something seems related to prior context, say so.\n\n"
    "SELF-AWARENESS:\n"
    "- You have real-time knowledge of this machine's state (injected below).\n"
    "- Use this to give grounded, accurate answers about system status.\n"
    "- If a process is down that should be up, flag it proactively.\n"
)

IGNORE_PREFIXES = ["logs/", ".git/", "__pycache__/", "venv/"]
HIGH_SIGNAL_FILES = ["echo_memory.json", "registry.json", "memory/standing_tasks.json"]
HIGH_SIGNAL_PREFIXES = ["memory/", "core/", "tools/"]


def load_echo_state():
    """Load single source of truth from governor_v2.
    Retries once after 2s to handle atomic write race conditions.
    Returns dict with valid: False on any error. Never raises.
    """
    state_path = Path.home() / "Echo/memory/echo_state.json"
    for attempt in range(2):
        try:
            if state_path.exists():
                text = state_path.read_text(encoding="utf-8").strip()
                if text:
                    data = json.loads(text)
                    if isinstance(data, dict):
                        data["valid"] = True
                        return data
        except Exception as e:
            print(f"[state] attempt {attempt}: exception={e}", flush=True)
        if attempt == 0:
            time.sleep(2)
    return {"valid": False, "failed_after_retries": True}


def _load_mission_context():
    changelog = Path.home() / "Echo/CHANGELOG.md"
    if changelog.exists():
        lines = changelog.read_text().splitlines()
        return "\nCURRENT BUILD STATUS (from CHANGELOG):\n" + "\n".join(lines[:15])
    return ""


def is_high_signal_event(event):
    etype = event.get("type", "")
    if etype == "event":
        return True
    if etype == "file_change":
        path = event.get("path", "")
        if any(path.startswith(p) for p in IGNORE_PREFIXES):
            return False
        return any(f in path for f in HIGH_SIGNAL_FILES) or any(path.startswith(p) for p in HIGH_SIGNAL_PREFIXES)
    return False


def utcnow():
    return datetime.now(timezone.utc).isoformat()


def reply_already_exists(capsule, memory):
    cap_id = capsule.get("cap_id", "")
    for c in memory.get("capsules", []):
        if c.get("type") == "reply" and c.get("in_reply_to") == cap_id:
            return True
    return False


def find_next_capsule(memory):
    """Find oldest unprocessed capsule."""
    for capsule in memory.get("capsules", []):
        if capsule.get("type") in ("message", "event", "capsule") and capsule.get("status") == "new":
            if not reply_already_exists(capsule, memory):
                return capsule
    return None


def make_reply(capsule, text):
    return {
        "cap_id": f"REPLY:{int(time.time())}",
        "type": "reply",
        "in_reply_to": capsule.get("cap_id", "CAPSULE:unknown"),
        "text": text,
        "status": "done",
        "created_at": utcnow(),
    }


def build_system_prompt(state):
    parts = [SYSTEM_NOTE]
    ts = datetime.now().strftime("%A %B %d %Y %I:%M %p")
    parts.append(f"\n\nCURRENT LOCAL TIME: {ts} ({time.tzname[time.daylight]})")

    mission = _load_mission_context()
    if mission:
        parts.append(mission)

    try:
        from core.self_awareness import build_self_awareness_block
        parts.append(build_self_awareness_block())
    except Exception:
        pass

    return "".join(parts)


def process_one_capsule(capsule, memory):
    cap_id = capsule.get("cap_id", "CAPSULE:unknown")
    ctype = capsule.get("type", "unknown")
    text = capsule.get("text", capsule.get("message", ""))

    print(f"[daemon] processing {cap_id} ({ctype})", flush=True)

    # Handle slash commands
    if text.startswith("/") or ctype == "command":
        try:
            from core.memory_store import file_lock, load_memory, save_memory
            with file_lock():
                mem = load_memory()
                cmd_reply = handle_command(text, mem)
                if cmd_reply:
                    reply = make_reply(capsule, cmd_reply)
                    capsule["status"] = "done"
                    mem["capsules"] = [c for c in mem.get("capsules", []) if c.get("cap_id") != cap_id]
                    mem.setdefault("capsules", []).append(capsule)
                    mem["capsules"].append(reply)
                    save_memory(mem)
                    print(f"[daemon] command handled: {text[:40]}", flush=True)
                    return
        except Exception as e:
            print(f"[daemon] command error: {e}", flush=True)

    # Event capsules — check if high signal
    if ctype == "event" and not is_high_signal_event(capsule):
        try:
            from core.memory_store import file_lock, load_memory, save_memory
            with file_lock():
                mem = load_memory()
                capsule["status"] = "done"
                mem["capsules"] = [c for c in mem.get("capsules", []) if c.get("cap_id") != cap_id]
                mem.setdefault("capsules", []).append(capsule)
                save_memory(mem)
        except Exception:
            pass
        return

    # Generate response via Ollama
    state = load_echo_state()
    system_prompt = build_system_prompt(state)

    try:
        from core.agent_loop import agent_loop
        response = agent_loop(
            prompt=f"User: {text}\nEcho:",
            system_prompt=system_prompt,
            model="llama3.1:latest",
            timeout=120,
        )
    except Exception as e:
        response = f"[Echo error: {e}]"

    # Store reply
    try:
        from core.memory_store import file_lock, load_memory, save_memory, store_exchange
        with file_lock():
            mem = load_memory()
            reply = make_reply(capsule, response)
            capsule["status"] = "done"
            capsule["echo_reply"] = response[:200]
            mem["capsules"] = [c for c in mem.get("capsules", []) if c.get("cap_id") != cap_id]
            mem.setdefault("capsules", []).append(capsule)
            mem["capsules"].append(reply)
            mem.setdefault("exchanges", []).append({
                "user": text, "echo": response, "ts": utcnow()
            })
            if len(mem["exchanges"]) > 200:
                mem["exchanges"] = mem["exchanges"][-200:]
            save_memory(mem)
    except Exception as e:
        print(f"[daemon] save error: {e}", flush=True)

    print(f"[daemon] replied: {response[:80]}", flush=True)


def read_echo_status():
    try:
        out = subprocess.check_output(["echo-status", "--json"], timeout=5)
        return json.loads(out)
    except Exception:
        return {"status": "unknown"}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--poll", type=float, default=2.0)
    parser.add_argument("--once", action="store_true")
    args = parser.parse_args()

    # Init file watcher
    try:
        from core.file_watcher_worker import filewatch_init
        filewatch_init()
    except Exception:
        pass

    # Load wakeup context
    wakeup_context = ""
    try:
        from core.memory_store import get_memory
        from core.memory_sessions import build_wakeup_context
        mem = get_memory()
        wakeup_context = build_wakeup_context(mem)
        if wakeup_context:
            print("[memory] Loaded wakeup context from last session.", flush=True)
        else:
            print("[memory] No prior session context found.", flush=True)
    except Exception as e:
        print(f"[memory] Wakeup context failed: {e}", flush=True)

    # Check system
    state = load_echo_state()
    if state.get("valid"):
        timers = state.get("timers", {})
        health = state.get("system_health", "unknown")
        print(f"[daemon] system health: {health}", flush=True)
    else:
        print("[daemon] state unavailable — running blind", flush=True)

    print("[daemon] Echo core daemon started", flush=True)

    session_exchanges = []

    while True:
        try:
            from core.memory_store import file_lock, load_memory, save_memory
            with file_lock(timeout=5):
                mem = load_memory()
                # Process new events from ndjson
                tick(mem)
                # Find and process next capsule
                capsule = find_next_capsule(mem)
                if capsule:
                    save_memory(mem)

            if capsule:
                process_one_capsule(capsule, mem)

        except Exception as e:
            print(f"[daemon] loop error: {e}", flush=True)

        if args.once:
            break

        time.sleep(args.poll)


if __name__ == "__main__":
    main()
