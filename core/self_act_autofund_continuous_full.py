import time
import json
from gpt_reasoner import gpt_reasoner
import psutil
import resource_tracker  # live resource updates
# from income_apis import get_crypto_income, get_golem_income, get_microtask_income  # live income hooks

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

CPU_LIMIT = 80.0
MEM_LIMIT = 80.0
DISK_LIMIT = 90.0

SIMULATED_TASKS = {
    "gather_water": {"income": 5, "skill": "water_management"},
    "build_shelter": {"income": 10, "skill": "construction"},
    "hunt_food": {"income": 8, "skill": "hunting"},
    "craft_tools": {"income": 12, "skill": "toolmaking"},
    "mine_ore": {"income": 15, "skill": "mining"}
}

def update_live_resources():
    resource_tracker  # updates core_state["resources"]
    core_state["resources"]["cpu_percent"] = psutil.cpu_percent(interval=0.5)
    core_state["resources"]["memory_percent"] = psutil.virtual_memory().percent
    core_state["resources"]["disk_percent"] = psutil.disk_usage("/").percent

def fetch_live_tasks():
    # Placeholder for live API task fetching
    tasks = []
    tasks.append({"task_id": "crypto_mine", "income": 0.5, "prereq_skills": ["crypto"], "resources": {"cpu": 50, "mem": 30}})
    tasks.append({"task_id": "microtasks", "income": 0.2, "prereq_skills": [], "resources": {"cpu": 10, "mem": 10}})
    tasks.append({"task_id": "golem_compute", "income": 1.0, "prereq_skills": ["compute"], "resources": {"cpu": 70, "mem": 40}})
    return tasks

def dynamic_x_flag_injection():
    # Simulated tasks
    sorted_tasks = sorted(SIMULATED_TASKS.items(), key=lambda t: t[1]["income"], reverse=True)
    for task, info in sorted_tasks:
        skill = info["skill"]
        if skill not in core_state["knowledge"] and task not in core_state["X_flags"]:
            core_state["X_flags"].append(task)
            core_state["income_sources"][task] = info["income"]
            print(f"[AUTO] Injected X_flag: {task} with income {info['income']}")
    # Live API tasks
    live_tasks = fetch_live_tasks()
    for task in live_tasks:
        if all(skill in core_state["knowledge"] for skill in task["prereq_skills"]):
            if task["task_id"] not in core_state["X_flags"]:
                core_state["X_flags"].append(task["task_id"])
                core_state["income_sources"][task["task_id"]] = task["income"]
                print(f"[LIVE] Added X_flag dynamically: {task['task_id']} with income {task['income']}")

def prune_completed_flags():
    core_state["X_flags"] = [x for x in core_state["X_flags"] if x not in core_state["knowledge"]]

def weighted_reasoning_cycle():
    update_live_resources()
    res = core_state["resources"]
    if res["cpu_percent"] > CPU_LIMIT or res["memory_percent"] > MEM_LIMIT or res["disk_percent"] > DISK_LIMIT:
        print("Resources high, delaying reasoning cycle.")
        return
    dynamic_x_flag_injection()
    # prioritize by income
    prioritized_flags = sorted(core_state["X_flags"], key=lambda f: core_state["income_sources"].get(f,0), reverse=True)
    for x_flag in prioritized_flags:
        if x_flag in core_state["knowledge"]:
            continue
        result = gpt_reasoner(x_flag, core_state)
        core_state["reasoning_history"].append(result)
        core_state["knowledge"][x_flag] = result
        print(f"Processed {x_flag}: {result}, potential income: {core_state['income_sources'].get(x_flag,0)}")
    prune_completed_flags()
    with open(CORE_STATE_PATH, "w") as f:
        json.dump(core_state, f, indent=2)

if __name__ == "__main__":
    while True:
        print("Echo alive - Starting continuous live autonomous cycle.")
        weighted_reasoning_cycle()
        time.sleep(10)
