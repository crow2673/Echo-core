import time
import json
from gpt_reasoner import gpt_reasoner
import resource_tracker  # imports and updates core_state["resources"]

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
        "resources": {}
    }

def weighted_reasoning_cycle():
    # Update live resources
    resource_tracker  # this updates core_state["resources"]

    # Example thresholds for CPU / memory / disk usage
    cpu_limit = 80.0
    mem_limit = 80.0
    disk_limit = 90.0

    resources = core_state.get("resources", {})
    cpu = resources.get("cpu_percent", 0)
    mem = resources.get("memory_percent", 0)
    disk = resources.get("disk_percent", 0)

    # Skip cycle if resources are too high
    if cpu > cpu_limit or mem > mem_limit or disk > disk_limit:
        print("Resources high, delaying reasoning cycle.")
        return

    # Prioritize X_flags based on resource-adjusted strategy
    for x_flag in core_state.get("X_flags", []):
        # Example: skip tasks already in knowledge
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
        print("Echo alive - Starting reasoning cycle with live resources.")
        weighted_reasoning_cycle()
        time.sleep(10)
