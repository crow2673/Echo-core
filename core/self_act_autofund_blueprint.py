import time
import json
from gpt_reasoner import gpt_reasoner
# Placeholder: live APIs not connected yet
# from income_apis import get_crypto_income, get_golem_income, get_microtask_income
import psutil  # for resource tracking

CORE_STATE_PATH = "../memory/core_state.json"

# Load or initialize core state
try:
    with open(CORE_STATE_PATH, "r") as f:
        core_state = json.load(f)
except FileNotFoundError:
    core_state = {
        "reasoning_history": [],
        "knowledge": {},
        "X_flags": [],
        "resources": {},
        "income_sources": {},  # simulated potential income per task
        "skills_needed": {}    # skills to unlock tasks
    }

# --- Simulated tasks (blueprint placeholders) ---
SIMULATED_TASKS = [
    {"task_id": "crypto_mine", "income": 0.5, "prereq_skills": ["crypto"], "cpu": 50, "mem": 30},
    {"task_id": "microtasks", "income": 0.2, "prereq_skills": [], "cpu": 10, "mem": 10},
    {"task_id": "golem_compute", "income": 1.0, "prereq_skills": ["compute"], "cpu": 70, "mem": 40},
    {"task_id": "data_entry", "income": 0.1, "prereq_skills": [], "cpu": 5, "mem": 5}
]

CPU_LIMIT = 80.0
MEM_LIMIT = 80.0
DISK_LIMIT = 90.0

def update_resources():
    core_state["resources"]["cpu_percent"] = psutil.cpu_percent(interval=0.5)
    core_state["resources"]["memory_percent"] = psutil.virtual_memory().percent
    core_state["resources"]["disk_percent"] = psutil.disk_usage("/").percent

def dynamic_x_flag_injection():
    """
    Inject tasks based on skill availability and potential income.
    Prioritize highest income first.
    """
    # Sort tasks by income descending
    sorted_tasks = sorted(SIMULATED_TASKS, key=lambda t: t["income"], reverse=True)
    for task in sorted_tasks:
        if all(skill in core_state["knowledge"] for skill in task["prereq_skills"]):
            if task["task_id"] not in core_state["X_flags"] and task["task_id"] not in core_state["knowledge"]:
                core_state["X_flags"].append(task["task_id"])
                core_state["income_sources"][task["task_id"]] = task["income"]
                print(f"[BLUEPRINT] Added X_flag: {task['task_id']} (income {task['income']})")

def prune_completed_flags():
    """
    Remove X_flags that have already been processed.
    """
    core_state["X_flags"] = [x for x in core_state["X_flags"] if x not in core_state["knowledge"]]

def reasoning_cycle():
    """
    Process all X_flags with GPT reasoning, simulate learning, and update knowledge.
    """
    update_resources()
    if (core_state["resources"]["cpu_percent"] > CPU_LIMIT or
        core_state["resources"]["memory_percent"] > MEM_LIMIT or
        core_state["resources"]["disk_percent"] > DISK_LIMIT):
        print("[BLUEPRINT] Resources high, skipping cycle.")
        return

    dynamic_x_flag_injection()
    prune_completed_flags()

    for x_flag in core_state["X_flags"]:
        result = gpt_reasoner(x_flag, core_state)
        core_state["reasoning_history"].append(result)
        core_state["knowledge"][x_flag] = result
        print(f"[BLUEPRINT] Processed {x_flag}: {result}")

    # Save state
    with open(CORE_STATE_PATH, "w") as f:
        json.dump(core_state, f, indent=2)

if __name__ == "__main__":
    while True:
        print("[BLUEPRINT] Echo alive - Starting autonomous simulation cycle.")
        reasoning_cycle()
        time.sleep(10)
