import time
import json
from gpt_reasoner import gpt_reasoner
import psutil
import requests
import os
import sys

CORE_STATE_PATH = os.path.join(os.path.dirname(__file__), "../memory/core_state.json")

# --- Define a robust default core_state structure ---
# This ensures all expected keys and their default types are always present.
DEFAULT_CORE_STATE = {
    "reasoning_history": [],
    "knowledge": {},
    "X_flags": [],
    "completed_tasks": [],
    "resources": {"cpu_percent": 0, "memory_percent": 0, "disk_percent": 0},
    "income_sources": {},
    "skills_needed": {}
}

# --- Load or initialize core_state ---
# Start with a clean copy of the default state
core_state = DEFAULT_CORE_STATE.copy()

if os.path.exists(CORE_STATE_PATH):
    try:
        with open(CORE_STATE_PATH, "r") as f:
            loaded_data = json.load(f)
            # Merge loaded data into our default structure, prioritizing loaded values
            core_state.update(loaded_data)
    except json.JSONDecodeError:
        print(f"Warning: {CORE_STATE_PATH} is corrupted or invalid JSON. Initializing with default state.", file=sys.stderr)
        # core_state remains DEFAULT_CORE_STATE.copy()
    except Exception as e: # Catch any other file loading errors
        print(f"Error loading {CORE_STATE_PATH}: {e}. Initializing with default state.", file=sys.stderr)
        # core_state remains DEFAULT_CORE_STATE.copy()
else:
    print(f"Info: {CORE_STATE_PATH} not found. Initializing with default state.", file=sys.stderr)
    # core_state remains DEFAULT_CORE_STATE.copy()

# Ensure that test skills are *always* present for the injected task,
# at least during this temporary testing phase.
core_state["knowledge"]["LLM_integration"] = True
core_state["knowledge"]["reasoning"] = True
print(f"[AUTO] Ensured test skills for LLM_integration and reasoning are present in core_state['knowledge'].")


CPU_LIMIT = 80.0
MEM_LIMIT = 80.0
DISK_LIMIT = 90.0

# --- Placeholder API endpoints ---
API_ENDPOINTS = {
    "crypto_mine": "https://api.example.com/crypto_status",
    "golem_compute": "https://api.example.com/golem_status",
    "microtasks": "https://api.example.com/microtask_status"
}

def update_live_resources():
    core_state["resources"]["cpu_percent"] = psutil.cpu_percent(interval=0.5)
    core_state["resources"]["memory_percent"] = psutil.virtual_memory().percent
    core_state["resources"]["disk_percent"] = psutil.disk_usage("/").percent

def fetch_live_tasks():
    tasks = []
    # --- TEMPORARY: Inject a test X_flag to ensure LLM is called ---
    test_task_id = "test_llm_reasoning_task"
    if test_task_id not in core_state["completed_tasks"] and test_task_id not in core_state["X_flags"]:
        tasks.append({
            "task_id": test_task_id,
            "income": 100.0,
            "prereq_skills": ["LLM_integration", "reasoning"],
            "resources": {"cpu": 50, "mem": 30}
        })
    # --- END TEMPORARY INJECTION ---

    for task_id, url in API_ENDPOINTS.items():
        try:
            resp = requests.get(url, timeout=2)
            data = resp.json()
            tasks.append({
                "task_id": task_id,
                "income": data.get("income", 0),
                "prereq_skills": data.get("prereq_skills", []),
                "resources": data.get("resources", {"cpu": 10, "mem": 10})
            })
        except Exception as e:
            print(f"[API] Failed to fetch {task_id}: {e}", file=sys.stderr) # Directing error to stderr

    return tasks

def dynamic_x_flag_injection():
    live_tasks = fetch_live_tasks()
    for task in live_tasks:
        if task["task_id"] in core_state["completed_tasks"]:
            continue
        # The skills are guaranteed to be present by the startup logic now for the test task
        # We assume for testing purposes that required skills for `test_llm_reasoning_task` are met.
        if all(skill in core_state["knowledge"] for skill in task["prereq_skills"]):
            if task["task_id"] not in core_state["X_flags"]:
                core_state["X_flags"].append(task["task_id"])
                core_state["income_sources"][task["task_id"]] = task["income"]
                print(f"[AUTO] Added live X_flag: {task['task_id']} (income {task['income']})")

def weighted_reasoning_cycle():
    update_live_resources()
    res = core_state["resources"]
    if res["cpu_percent"] > CPU_LIMIT or res["memory_percent"] > MEM_LIMIT or res["disk_percent"] > DISK_LIMIT:
        print("[AUTO] High resource usage, delaying cycle.", file=sys.stderr)
        return

    dynamic_x_flag_injection()

    for x_flag in core_state["X_flags"][:]: # Iterate over a copy to allow modification
        if x_flag in core_state["knowledge"]: # If the LLM has already processed this and added to knowledge
            if x_flag not in core_state["completed_tasks"]:
                core_state["completed_tasks"].append(x_flag) # Mark as completed if already known
            core_state["X_flags"].remove(x_flag)
            continue # Skip LLM call if already in knowledge

        print(f"[AUTO] Calling gpt_reasoner for '{x_flag}'...")
        result = gpt_reasoner(x_flag, core_state)
        core_state["reasoning_history"].append(result)
        core_state["knowledge"][x_flag] = result
        print(f"[AUTO] Processed {x_flag}: How='{result.get('how', 'N/A')}', Why='{result.get('why', 'N/A')}', Confidence={result.get('confidence', 'N/A')}")
        core_state["completed_tasks"].append(x_flag) # Mark as completed after LLM reasoning
        core_state["X_flags"].remove(x_flag) # Remove from X_flags as it's processed

    with open(CORE_STATE_PATH, "w") as f:
        json.dump(core_state, f, indent=2)

if __name__ == "__main__":
    # Ensure the current state (which now guarantees default structure and test skills) is saved
    # This overwrites any previous `core_state.json` at the start of the script.
    with open(CORE_STATE_PATH, "w") as f:
        json.dump(core_state, f, indent=2)
        print(f"[AUTO] Initialized/Updated {CORE_STATE_PATH} at startup with guaranteed structure and test skills.")

    while True:
        print("[AUTO] Echo alive - running live API autonomous cycle.")
        weighted_reasoning_cycle()
        time.sleep(10)
