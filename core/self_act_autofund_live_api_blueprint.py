import time
import json
from skill_xp_engine import award_xp
import psutil

CORE_STATE_PATH = "../memory/core_state.json"

# --- Load or initialize core state ---
try:
    with open(CORE_STATE_PATH, "r") as f:
        core_state = json.load(f)
except FileNotFoundError:
    core_state = {
        "reasoning_history": [],
        "knowledge": {},
        "X_flags": [],
        "resources": {},
        "skill_xp": {},
        "unlocked_skills": [],
        "income_sources": {}  # track potential income per task
    }

# --- Placeholder for live income APIs ---
def fetch_live_tasks():
    """
    Replace these placeholders with real API calls:
      - get_crypto_tasks()
      - get_microtasks()
      - get_golem_tasks()
    Each task should provide:
      - task_id
      - expected_income
      - required_skills (prereqs)
      - resource_requirements (CPU, memory)
    """
    tasks = [
        {"task_id": "crypto_mine", "income": 0.5, "prereq_skills": ["crypto"], "resources": {"cpu":50,"mem":30}},
        {"task_id": "microtasks", "income": 0.2, "prereq_skills": [], "resources": {"cpu":10,"mem":10}},
        {"task_id": "golem_compute", "income": 1.0, "prereq_skills": ["compute"], "resources": {"cpu":70,"mem":40}}
    ]
    return tasks

def update_resources():
    core_state["resources"]["cpu_percent"] = psutil.cpu_percent(interval=0.5)
    core_state["resources"]["memory_percent"] = psutil.virtual_memory().percent
    core_state["resources"]["disk_percent"] = psutil.disk_usage("/").percent

def dynamic_x_flag_injection():
    """
    Add tasks Echo can perform based on:
      - current unlocked skills
      - prerequisites for each task
      - resource constraints
    """
    for task in fetch_live_tasks():
        if all(skill in core_state["unlocked_skills"] for skill in task["prereq_skills"]):
            if task["task_id"] not in core_state["X_flags"]:
                core_state["X_flags"].append(task["task_id"])
                core_state["income_sources"][task["task_id"]] = task["income"]
                print(f"[API] Injected X_flag: {task['task_id']} with income {task['income']}")

def process_x_flags():
    """
    Award XP for each task's skill.
    Placeholder: map task_id -> skill_name. Replace with real mapping.
    """
    for x_flag in core_state["X_flags"]:
        # Example skill mapping (replace with actual task->skill mapping)
        skill_name = x_flag.replace("_", " ")  # e.g., "crypto_mine" -> "crypto mine"
        result = award_xp(skill_name, core_state["income_sources"].get(x_flag, 0))
        print(f"[API] Processed {x_flag} -> Skill {skill_name}: {result}")

def prune_completed_flags():
    core_state["X_flags"] = [x for x in core_state["X_flags"] if x not in core_state["skill_xp"]]

def main_loop():
    while True:
        update_resources()
        cpu, mem, disk = (core_state["resources"][k] for k in ["cpu_percent","memory_percent","disk_percent"])
        if cpu > 80 or mem > 80 or disk > 90:
            print("[API] Resources high, pausing cycle.")
        else:
            dynamic_x_flag_injection()
            process_x_flags()
            prune_completed_flags()
        time.sleep(10)

if __name__ == "__main__":
    main_loop()
