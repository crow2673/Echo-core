import time
import json
import sys
sys.path.insert(0, "./core")
from gpt_reasoner import gpt_reasoner
import psutil
import requests  # for real API calls
import os # <--- NEW IMPORT

CORE_STATE_PATH = os.path.join(os.path.dirname(__file__), "../memory/core_state.json") # <--- Safer path handling

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
except json.JSONDecodeError: # <--- Added JSON error handling
    print(f"Warning: {CORE_STATE_PATH} is corrupted. Initializing with empty state.", file=sys.stderr)
    core_state = {
        "reasoning_history": [],
        "knowledge": {},
        "X_flags": [],
        "completed_tasks": [],
        "resources": {"cpu_percent": 0, "memory_percent": 0, "disk_percent": 0},
        "income_sources": {},
        "skills_needed": {}
    }


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
    # This will be processed by the LLM in the next cycle.
    if "test_llm_reasoning_task" not in core_state["completed_tasks"] and "test_llm_reasoning_task" not in core_state["X_flags"]:
        tasks.append({
            "task_id": "test_llm_reasoning_task",
            "income": 100.0,
            "prereq_skills": ["LLM_integration", "reasoning"],
            "resources": {"cpu": 50, "mem": 30}
        })
    # --- END TEMPORARY INJECTION ---

    for task_id, url in API_ENDPOINTS.items():
        try:
            resp = requests.get(url, timeout=2) # These calls will still fail, but won't block the LLM test
            data = resp.json()
            tasks.append({
                "task_id": task_id,
                "income": data.get("income", 0),
                "prereq_skills": data.get("prereq_skills", []),
                "resources": data.get("resources", {"cpu": 10, "mem": 10})
            })
        except Exception as e:
            print(f"[API] Failed to fetch {task_id}: {e}")
    return tasks

def dynamic_x_flag_injection():
    live_tasks = fetch_live_tasks()
    for task in live_tasks:
        if task["task_id"] in core_state["completed_tasks"]:
            continue
        # Assuming you have "LLM_integration" and "reasoning" skills in core_state["knowledge"]
        # For testing, we might temporarily assume these skills are present.
        # if all(skill in core_state["knowledge"] for skill in task["prereq_skills"]): # Original logic
        # Simplified for testing LLM
        if True: # <--- TEMPORARY: Assume all skills for injected task
            if task["task_id"] not in core_state["X_flags"]:
                core_state["X_flags"].append(task["task_id"])
                core_state["income_sources"][task["task_id"]] = task["income"]
                print(f"[AUTO] Added live X_flag: {task['task_id']} (income {task['income']})")

def weighted_reasoning_cycle():
    update_live_resources()
    res = core_state["resources"]
    if res["cpu_percent"] > CPU_LIMIT or res["memory_percent"] > MEM_LIMIT or res["disk_percent"] > DISK_LIMIT:
        print("[AUTO] High resource usage, delaying cycle.")
        return

    dynamic_x_flag_injection()

    for x_flag in core_state["X_flags"][:]:
        if x_flag in core_state["knowledge"]: # Skip if already reasoned about and in knowledge
            if x_flag not in core_state["completed_tasks"]:
                core_state["completed_tasks"].append(x_flag)
            core_state["X_flags"].remove(x_flag)
            continue

        print(f"[AUTO] Calling gpt_reasoner for '{x_flag}'...") # <--- Added print for visibility
        result = gpt_reasoner(x_flag, core_state)
        core_state["reasoning_history"].append(result)
        core_state["knowledge"][x_flag] = result
        print(f"[AUTO] Processed {x_flag}: How='{result.get('how', 'N/A')}', Why='{result.get('why', 'N/A')}', Confidence={result.get('confidence', 'N/A')}")
        core_state["completed_tasks"].append(x_flag) # Mark as completed after LLM reasoning
        core_state["X_flags"].remove(x_flag)

    with open(CORE_STATE_PATH, "w") as f:
        json.dump(core_state, f, indent=2)

if __name__ == "__main__":
    # Ensure core_state.json exists with necessary skills for testing
    if not os.path.exists(CORE_STATE_PATH):
        core_state["knowledge"] = {"LLM_integration": True, "reasoning": True} # <--- TEMP: Inject skills
        with open(CORE_STATE_PATH, "w") as f:
            json.dump(core_state, f, indent=2)
            print(f"[AUTO] Initialized {CORE_STATE_PATH} with test skills.")

    while True:
        print("[AUTO] Echo alive - running live API autonomous cycle.")
        weighted_reasoning_cycle()
        time.sleep(10)
