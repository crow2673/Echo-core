import time
import json
from gpt_reasoner import gpt_reasoner
import resource_tracker  # updates core_state["resources"]

CORE_STATE_PATH = "../memory/core_state.json"

# --- Load or initialize core_state ---
try:
    with open(CORE_STATE_PATH, "r") as f:
        core_state = json.load(f)
except FileNotFoundError:
    core_state = {
        "reasoning_history": [],
        "knowledge": {},
        "X_flags": [],
        "resources": {},
        "income_sources": {},  # track potential income per task
        "skills_needed": {}    # skills needed to unlock tasks
    }

def dynamic_x_flag_injection():
    """
    Inject new X_flags based on knowledge gaps, skill requirements, and income potential.
    """
    for skill, info in core_state.get("skills_needed", {}).items():
        if skill not in core_state["knowledge"]:
            income_potential = info.get("income", 0)
            if income_potential > 0 and skill not in core_state["X_flags"]:
                core_state["X_flags"].append(skill)
                print(f"Added X_flag dynamically: {skill}")

def prune_x_flags():
    """
    Remove X_flags that are already learned or low-value.
    """
    pruned_flags = []
    for x_flag in core_state.get("X_flags", []):
        if x_flag in core_state.get("knowledge", {}):
            pruned_flags.append(x_flag)
        elif core_state.get("income_sources", {}).get(x_flag, 0) == 0:
            pruned_flags.append(x_flag)
    for flag in pruned_flags:
        core_state["X_flags"].remove(flag)
        print(f"Pruned X_flag: {flag}")

def weighted_reasoning_cycle():
    # Update live resources
    resource_tracker  # updates core_state["resources"]

    cpu_limit = 80.0
    mem_limit = 80.0
    disk_limit = 90.0
    resources = core_state.get("resources", {})
    cpu = resources.get("cpu_percent", 0)
    mem = resources.get("memory_percent", 0)
    disk = resources.get("disk_percent", 0)

    if cpu > cpu_limit or mem > mem_limit or disk > disk_limit:
        print("Resources high, delaying reasoning cycle.")
        return

    # Inject and prune X_flags
    dynamic_x_flag_injection()
    prune_x_flags()

    # Weighted processing of X_flags
    sorted_flags = sorted(
        core_state.get("X_flags", []),
        key=lambda f: core_state.get("skills_needed", {}).get(f, {}).get("income", 0),
        reverse=True
    )

    for x_flag in sorted_flags:
        if x_flag in core_state.get("knowledge", {}):
            continue
        result = gpt_reasoner(x_flag, core_state)
        core_state["reasoning_history"].append(result)
        core_state["knowledge"][x_flag] = result
        print(f"Processed {x_flag}: {result}")

    # Save updated state
    with open(CORE_STATE_PATH, "w") as f:
        json.dump(core_state, f, indent=2)

if __name__ == "__main__":
    while True:
        print("Echo alive - Starting pruned dynamic reasoning cycle.")
        weighted_reasoning_cycle()
        time.sleep(10)
