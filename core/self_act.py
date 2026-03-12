
import time
import json
import sys
import os
from pathlib import Path

# Package-relative import (requires running as: python3 -m core.self_act)
from .gpt_reasoner import gpt_reasoner
from .event_ledger import log_event
from .agent_loop import agent_loop
from .providers.router import call_ollama as _call_ollama

BASE = Path(__file__).resolve().parents[1]         # ~/Echo
MEM  = BASE / "memory"
STATE_FILE = MEM / "core_state_reasoning.json"
SYS_STATE_FILE = MEM / "core_state_system.json"

def load_state():
    if STATE_FILE.exists():
        return json.loads(STATE_FILE.read_text())
    return {"reasoning_history": [], "knowledge": {}, "X_flags": []}

def save_state(state):
    # Cap history and knowledge to last 50 entries to prevent unbounded growth
    if len(state.get("reasoning_history", [])) > 50:
        state["reasoning_history"] = state["reasoning_history"][-50:]
    if len(state.get("knowledge", {})) > 50:
        keys = list(state["knowledge"].keys())
        state["knowledge"] = {k: state["knowledge"][k] for k in keys[-50:]}
    STATE_FILE.write_text(json.dumps(state, indent=2) + "\n")

def load_system_state():
    if SYS_STATE_FILE.exists():
        try:
            return json.loads(SYS_STATE_FILE.read_text())
        except Exception:
            return {}
    return {}
def update_income_status():
    import re as _re
    from datetime import datetime
    doc_path = Path(__file__).resolve().parents[1] / "memory" / "income_knowledge.md"
    if not doc_path.exists():
        return
    doc = doc_path.read_text()
    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    changed = False
    golem_tasks = 0
    try:
        regret_path = Path(__file__).resolve().parents[1] / "memory" / "regret_index.json"
        if regret_path.exists():
            ri = json.loads(regret_path.read_text())
            golem_tasks = sum(1 for e in ri.get("actions", []) if "golem" in e.get("action", "").lower() and e.get("outcome_score", 0) > 0)
    except Exception:
        pass
    if golem_tasks == 0:
        new_golem = f"**Echo's current status:** ACTIVE — node running, 0 tasks completed (new node penalty phase) | _checked {now}_"
    else:
        new_golem = f"**Echo's current status:** ACTIVE — node running, {golem_tasks} tasks completed | _checked {now}_"
    doc, n = _re.subn(r"\*\*Echo.s current status:\*\* ACTIVE — node running.*", new_golem, doc)
    if n: changed = True
    devto_count = 1
    try:
        log_path = Path(__file__).resolve().parents[1] / "logs" / "devto_publish.log"
        if log_path.exists():
            devto_count = max(1, log_path.read_text().lower().count("published"))
    except Exception:
        pass
    scheduled_note = ""
    try:
        import subprocess
        r = subprocess.run(["systemctl", "--user", "is-active", "echo-devto-publish.timer"], capture_output=True, text=True)
        if r.stdout.strip() == "active":
            scheduled_note = ", 1 scheduled Tuesday 2026-03-17"
    except Exception:
        pass
    s = "s" if devto_count != 1 else ""
    new_devto = f"**Echo's current status:** ACTIVE — {devto_count} article{s} published{scheduled_note} | _checked {now}_"
    doc, n = _re.subn(r"\*\*Echo.s current status:\*\* ACTIVE — \d+ article.*", new_devto, doc)
    if n: changed = True
    doc, n = _re.subn(r"_Last updated: [\d\- :]+_", f"_Last updated: {now}_", doc)
    if n: changed = True
    if changed:
        doc_path.write_text(doc)
        print(f"[income_status] Updated income_knowledge.md at {now}")

def reasoning_cycle():
    core_state = load_state()
    system_state = load_system_state()
    core_state["system_state"] = system_state

    # ---- deterministic queue behavior ----
    # Generate fresh flags from system state before processing
    fresh = generate_flags(core_state)
    existing = core_state.get("X_flags", [])
    for flag in fresh:
        if flag not in existing:
            existing.append(flag)
    core_state["X_flags"] = []
    flags = list(existing)  # clear immediately so it cannot “stick” if we crash mid-run

    for x_flag in flags:
        prompt_flag = x_flag
        if str(x_flag).lower().startswith("summarize:"):
            ss = system_state or {}
            facts = {
                "updated_at": ss.get("updated_at"),
                "core": ss.get("core", {}),
                "services": ss.get("services", {}),
                "timers": ss.get("timers", {}),
                "last": ss.get("last", {}),
                "errors": ss.get("errors", []),
            }
            prompt_flag = (
                "summarize: current Echo system state in ONE paragraph. "
                "Use ONLY these facts (no guessing): " + json.dumps(facts, default=str)
            )

        # Use agent_loop for tool-capable reasoning; fall back to gpt_reasoner if it fails
        try:
            system_prompt = (
                "You are Echo. You are running an autonomous background reasoning cycle.\n"
                "Complete the task below using your tools if needed.\n"
                "Be concrete and specific. State what you found or did — not what you would do.\n"
                "If you check a tool, summarize what it returned.\n"
                "Do not restart services unless specifically asked to investigate a failure."
            )
            result = agent_loop(
                prompt=str(prompt_flag),
                system_prompt=system_prompt,
                call_ollama_fn=_call_ollama,
                model="echo",
                timeout=240.0,
                max_iterations=3,
                auto_approve_safe=True,
            )
        except Exception as _e:
            result = gpt_reasoner(prompt_flag, core_state)
        core_state["reasoning_history"].append(result)
        core_state["knowledge"][x_flag] = result
        if "income_knowledge" in str(x_flag):
            update_income_status()
        try:
            log_event("reasoning", "self_act", str(x_flag)[:200], data=result if isinstance(result, dict) else str(result))
        except Exception:
            pass
        print(f"Processed {x_flag}: {result}")

    save_state(core_state)


def generate_flags(core_state: dict) -> list:
    """
    Generate X_flags based on current system state.
    Called at the start of every reasoning cycle to ensure queue never runs dry.
    """
    flags = []
    system = core_state.get("system_state", {})
    errors = system.get("errors", [])
    timers = system.get("timers", {})
    workers = system.get("workers", {})

    # Flag any errors
    for err in errors[:2]:
        flag = f"investigate error: {str(err)[:80]}"
        if flag not in core_state.get("knowledge", {}):
            flags.append(flag)

    # Flag stale workers
    for name, info in workers.items():
        if isinstance(info, dict) and info.get("stale"):
            flag = f"investigate stale worker: {name}"
            if flag not in core_state.get("knowledge", {}):
                flags.append(flag)

    # Flag inactive timers
    for name, active in timers.items():
        if not active:
            flag = f"investigate inactive timer: {name}"
            if flag not in core_state.get("knowledge", {}):
                flags.append(flag)

    # Always have at least one standing task
    standing = [
        "summarize: current Echo system state in ONE paragraph",
        "review TODO.md and suggest the single highest-value next action",
        "check Golem node status and suggest pricing adjustment if needed",
        "read memory/income_knowledge.md and reason about which income path to activate next",
        "read registry.json and verify all listed services are actually running",
        "query_ledger: summarize recent wins and losses from the event ledger",
    ]
    existing_knowledge = set(core_state.get("knowledge", {}).keys())
    for task in standing:
        if task not in existing_knowledge and task not in flags:
            flags.append(task)
            break  # one standing task per cycle

    return flags


if __name__ == "__main__":
    # worker mode
    if "--once" in sys.argv:
        print("Echo self_act: once")
        reasoning_cycle()
        sys.exit(0)

    # legacy loop mode (not used by systemd worker)
    while True:
        print("Echo alive")
        reasoning_cycle()
        time.sleep(10)
