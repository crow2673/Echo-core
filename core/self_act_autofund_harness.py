import time
import json
from gpt_reasoner import gpt_reasoner

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
        "resources": {"cpu_percent": 0, "memory_percent": 0, "disk_percent": 0},
        "income_sources": {},
        "skills_needed": {}
    }

# --- Simulated income/skill feed for testing ---
SIMULATED_TASKS = {
    "gather_water": {"income": 5, "skill": "water_management"},
    "build_shelter": {"income": 10, "skill": "construction"},
    "hunt_food": {"income": 8, "skill": "hunting"},
    "craft_tools": {"income": 12, "skill": "toolmaking"},
}

CPU_LIMIT = 80.0
MEM_LIMIT = 80.0
DISK_LIMIT = 90.0

def update_simulated_resources():
    # Mock resource usage
    core_state["resources"]["cpu_percent"] = 10.0
    core_state["resources"]["memory_percent"] = 35.0
    core_state["resources"]["disk_percent"] = 5.0

def dynamic_x_flag_injection():
    # Prioritize tasks by highest simulated income for missing skills
    for task, info in SIMULATED_TASKS.items():
        skill = info["skill"]
        if skill not in core_state["knowledge"] and task not in core_state["X_flags"]:
            core_state["X_flags"].append(task)
            print(f"[HARNESSS] Added X_flag: {task}")

def prune_completed_flags():
    # Remove X_flags that already exist in knowledge
    original_flags = core_state["X_flags"][:]
    core_state["X_flags"] = [x for x in core_state["X_flags"] if x not in core_state["knowledge"]]
    for removed in set(original_flags) - set(core_state["X_flags"]):
        print(f"[HARNESSS] Pruned X_flag: {removed}")

def weighted_reasoning_cycle():
    update_simulated_resources()
    resources = core_state.get("resources", {})
    if (resources.get("cpu_percent",0) > CPU_LIMIT or
        resources.get("memory_percent",0) > MEM_LIMIT or
        resources.get("disk_percent",0) > DISK_LIMIT):
        print("[HARNESSS] Resources high, skipping cycle")
        return

    dynamic_x_flag_injection()
    prune_completed_flags()

    # Process X_flags
    for x_flag in core_state.get("X_flags", []):
        result = gpt_reasoner(x_flag, core_state)
        core_state["reasoning_history"].append(result)
        core_state["knowledge"][x_flag] = result
        # Simulate income allocation
        core_state["income_sources"][x_flag] = SIMULATED_TASKS[x_flag]["income"]
        print(f"[HARNESSS] Processed {x_flag}: {result} | Simulated income: {SIMULATED_TASKS[x_flag]['income']}")

    # Save state
    with open(CORE_STATE_PATH, "w") as f:
        json.dump(core_state, f, indent=2)

if __name__ == "__main__":
    cycle_count = 0
    while cycle_count < 10:  # run limited cycles for test harness
        print(f"[HARNESSS] Starting cycle {cycle_count+1}")
        weighted_reasoning_cycle()
        cycle_count += 1
        time.sleep(2)
    print("[HARNESSS] Test harness complete.")
