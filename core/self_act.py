
import time
import json
import sys
import os
from pathlib import Path

# Package-relative import (requires running as: python3 -m core.self_act)
from .gpt_reasoner import gpt_reasoner

BASE = Path(__file__).resolve().parents[1]         # ~/Echo
MEM  = BASE / "memory"
STATE_FILE = MEM / "core_state_reasoning.json"
SYS_STATE_FILE = MEM / "core_state_system.json"

def load_state():
    if STATE_FILE.exists():
        return json.loads(STATE_FILE.read_text())
    return {"reasoning_history": [], "knowledge": {}, "X_flags": []}

def save_state(state):
    STATE_FILE.write_text(json.dumps(state, indent=2) + "\n")

def load_system_state():
    if SYS_STATE_FILE.exists():
        try:
            return json.loads(SYS_STATE_FILE.read_text())
        except Exception:
            return {}
    return {}

def reasoning_cycle():
    core_state = load_state()
    system_state = load_system_state()
    core_state["system_state"] = system_state

    # ---- deterministic queue behavior ----
    flags = list(core_state.get("X_flags", []))
    core_state["X_flags"] = []  # clear immediately so it cannot “stick” if we crash mid-run

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

        result = gpt_reasoner(prompt_flag, core_state)
        core_state["reasoning_history"].append(result)
        core_state["knowledge"][x_flag] = result
        print(f"Processed {x_flag}: {result}")

    save_state(core_state)

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
