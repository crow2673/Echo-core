import time
import json
from gpt_reasoner import gpt_reasoner
import psutil  # live resource monitoring

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

# --- Live task simulation ---
SIMULATED_TASKS = {
    "gather_water": {"income": 5, "skill": "water_management"},
    "build_shelter": {"income": 10, "skill": "construction"},
    "hunt_food": {"income": 8, "skill": "hunting"},
    "craft_tools": {"income": 12, "skill": "toolmaking"},
    "mine_ore": {"income": 15, "skill": "mining"}
}

CPU_LIMIT = 80.0
MEM_LIMIT = 80.0
DISK_LIMIT = 90.0

def update_live_resources():
    core_state["resources"]["cpu_percent"] = psutil.cpu_percent(interval=0.5)
    core_state["resources"]["memory_percent"] = psutil.virtual_memory().percent
    core_state["resources"]["disk_percent"] = psutil.disk_usage("/").percent

def dynamic_x_flag_injection():
    # Add tasks Echo hasn't learned yet, prioritize by highest income
    sorted_tasks = sorted(SIMULATED_TASKS.items(), key=lambda t: t[1]["income"], reverse=True)
    for task, info in sorted_tasks:
        skill = info["skill"]
        if skill not in core_state["knowledge"] and task not in core_state["X_flags"]:
            core_state["X_flags"].append(task)
            print(f"[AUTO] Injected X_flag: {task}")

def prune_completed_flags():
    original_flags = core_state["X_flags"][:]
    core_state["X_flags"] = [x for x in core_state["X_flags"] if x not in core_state["knowledge"]]
    for removed in set(original_flags) - set(core_state["X_flags"]):
        print(f"[AUTO] Pruned X_flag: {removed}")

def weighted_reasoning_cycle():
    update_live_resources()
    res = core_state.get("resources", {})
    if res.get("cpu_percent",0) > CPU_LIMIT or res.get("memory_percent",0) > MEM_LIMIT or res.get("disk_percent",0) > DISK_LIMIT:
        print(f"[AUTO] Resources high, delaying cycle: CPU {res['cpu_percent']}%, MEM {res['memory_percent']}%, DISK {res['disk_percent']}%")
        return

    dynamic_x_flag_injection()
    prune_completed_flags()

    # Process tasks in priority order
    for x_flag in core_state.get("X_flags", []):
        if x_flag in core_state.get("knowledge", {}):
            continue
        result = gpt_reasoner(x_flag, core_state)
        core_state["reasoning_history"].append(result)
        core_state["knowledge"][x_flag] = result
        core_state["income_sources"][x_flag] = SIMULATED_TASKS[x_flag]["income"]
        print(f"[AUTO] Processed {x_flag}: {result} | Income: {SIMULATED_TASKS[x_flag]['income']}")

    # Save state
    with open(CORE_STATE_PATH, "w") as f:
        json.dump(core_state, f, indent=2)

if __name__ == "__main__":
    while True:
        print("[AUTO] Starting continuous reasoning cycle...")
        weighted_reasoning_cycle()
        time.sleep(5)
