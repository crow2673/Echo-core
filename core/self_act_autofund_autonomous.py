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
        "completed_tasks": [],
        "resources": {"cpu_percent": 0, "memory_percent": 0, "disk_percent": 0},
        "income_sources": {},
        "skills_needed": {}
    }

# --- Simulated or placeholder live tasks ---
SIMULATED_TASKS = [
    {"task_id": "crypto_mine", "income": 0.5, "prereq_skills": ["crypto"], "resources": {"cpu": 50, "mem": 30}},
    {"task_id": "microtasks", "income": 0.2, "prereq_skills": [], "resources": {"cpu": 10, "mem": 10}},
    {"task_id": "golem_compute", "income": 1.0, "prereq_skills": ["compute"], "resources": {"cpu": 70, "mem": 40}}
]

CPU_LIMIT = 80.0
MEM_LIMIT = 80.0
DISK_LIMIT = 90.0

def update_live_resources():
    core_state["resources"]["cpu_percent"] = psutil.cpu_percent(interval=0.5)
    core_state["resources"]["memory_percent"] = psutil.virtual_memory().percent
    core_state["resources"]["disk_percent"] = psutil.disk_usage("/").percent

def fetch_live_tasks():
    # Replace this with actual API calls to live income sources
    return SIMULATED_TASKS

def dynamic_x_flag_injection():
    live_tasks = fetch_live_tasks()
    for task in live_tasks:
        # Skip if task already completed
        if task["task_id"] in core_state["completed_tasks"]:
            continue
        # Check skill prerequisites
        if all(skill in core_state["knowledge"] for skill in task["prereq_skills"]):
            if task["task_id"] not in core_state["X_flags"]:
                core_state["X_flags"].append(task["task_id"])
                core_state["income_sources"][task["task_id"]] = task["income"]
                print(f"[AUTO] Added X_flag: {task['task_id']} with income {task['income']}")

def weighted_reasoning_cycle():
    update_live_resources()
    res = core_state["resources"]
    if res["cpu_percent"] > CPU_LIMIT or res["memory_percent"] > MEM_LIMIT or res["disk_percent"] > DISK_LIMIT:
        print("[AUTO] High resource usage, delaying reasoning cycle.")
        return

    # Inject new tasks
    dynamic_x_flag_injection()

    # Process X_flags
    for x_flag in core_state["X_flags"][:]:
        if x_flag in core_state["knowledge"]:
            # Task already learned, move to completed
            if x_flag not in core_state["completed_tasks"]:
                core_state["completed_tasks"].append(x_flag)
            core_state["X_flags"].remove(x_flag)
            continue

        result = gpt_reasoner(x_flag, core_state)
        core_state["reasoning_history"].append(result)
        core_state["knowledge"][x_flag] = result
        print(f"[AUTO] Processed {x_flag}: {result}")
        # After processing, mark as completed
        core_state["completed_tasks"].append(x_flag)
        core_state["X_flags"].remove(x_flag)

    # Save updated state
    with open(CORE_STATE_PATH, "w") as f:
        json.dump(core_state, f, indent=2)

if __name__ == "__main__":
    while True:
        print("[AUTO] Echo alive - running autonomous self-funding cycle.")
        weighted_reasoning_cycle()
        time.sleep(10)
