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
        "income_sources": {},  # potential or live income per task
        "skills_needed": {}    # skills required for tasks
    }

# --- Configurable mode ---
USE_LIVE_FEEDS = False  # set True to pull actual income feeds

def dynamic_x_flag_injection():
    """Decide which new X_flags to add based on knowledge gaps and income potential."""
    for skill, info in core_state.get("skills_needed", {}).items():
        if skill not in core_state["knowledge"]:
            income_potential = info.get("income", 0)
            if income_potential > 0 and skill not in core_state["X_flags"]:
                core_state["X_flags"].append(skill)
                print(f"Added X_flag dynamically: {skill}")

def weighted_reasoning_cycle():
    # Update live resources
    resource_tracker  # updates core_state["resources"]

    # Use either simulated or live income
    if USE_LIVE_FEEDS:
        # Placeholder: update core_state["income_sources"] from live feed
        pass
    else:
        # Simulate income for testing
        for task in core_state.get("X_flags", []):
            core_state["income_sources"][task] = core_state.get("income_sources", {}).get(task, 10)

    # Resource-aware limits
    resources = core_state.get("resources", {})
    cpu, mem, disk = resources.get("cpu_percent",0), resources.get("memory_percent",0), resources.get("disk_percent",0)
    if cpu > 80.0 or mem > 80.0 or disk > 90.0:
        print("Resources high, delaying reasoning cycle.")
        return

    # Inject new X_flags
    dynamic_x_flag_injection()

    # Process X_flags
    for x_flag in core_state.get("X_flags", []):
        if x_flag in core_state.get("knowledge", {}):
            continue
        result = gpt_reasoner(x_flag, core_state)
        core_state["reasoning_history"].append(result)
        core_state["knowledge"][x_flag] = result
        print(f"Processed {x_flag}: {result}")

    # Save state
    with open(CORE_STATE_PATH, "w") as f:
        json.dump(core_state, f, indent=2)

if __name__ == "__main__":
    while True:
        print("Echo alive - Starting hybrid reasoning cycle.")
        weighted_reasoning_cycle()
        time.sleep(10)
