import time
import json
from skill_xp_engine import award_xp
import psutil  # for live resource monitoring

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
        "unlocked_skills": []
    }

# --- Live task simulation (replace with API tasks later) ---
LIVE_TASKS = {
    "gather_water": {"income": 5, "skill": "water_management"},
    "build_shelter": {"income": 10, "skill": "construction"},
    "hunt_food": {"income": 8, "skill": "hunting"},
    "craft_tools": {"income": 12, "skill": "toolmaking"},
    "mine_ore": {"income": 15, "skill": "mining"}
}

CPU_LIMIT = 80.0
MEM_LIMIT = 80.0
DISK_LIMIT = 90.0

def update_resources():
    core_state["resources"]["cpu_percent"] = psutil.cpu_percent(interval=0.5)
    core_state["resources"]["memory_percent"] = psutil.virtual_memory().percent
    core_state["resources"]["disk_percent"] = psutil.disk_usage("/").percent

def dynamic_x_flag_injection():
    """Inject tasks Echo hasn’t learned yet, prioritizing highest income."""
    sorted_tasks = sorted(LIVE_TASKS.items(), key=lambda t: t[1]["income"], reverse=True)
    for task, info in sorted_tasks:
        skill = info["skill"]
        if skill not in core_state["skill_xp"] and task not in core_state["X_flags"]:
            core_state["X_flags"].append(task)
            print(f"[AUTO] Injected X_flag: {task}")

def prune_completed_flags():
    """Remove X_flags that have already been processed/unlocked."""
    core_state["X_flags"] = [x for x in core_state["X_flags"] if x not in core_state["skill_xp"]]

def process_x_flags():
    """Process all X_flags, award XP, and update core state."""
    for x_flag in core_state.get("X_flags", []):
        task_info = LIVE_TASKS.get(x_flag)
        if not task_info:
            continue
        skill = task_info["skill"]
        xp_awarded = task_info["income"]  # XP matches task income for simplicity
        result = award_xp(skill, xp_awarded)
        print(f"Processed {x_flag} -> Skill {skill}: {result}")

def main_loop():
    while True:
        update_resources()
        cpu, mem, disk = (core_state["resources"][k] for k in ["cpu_percent","memory_percent","disk_percent"])
        if cpu > CPU_LIMIT or mem > MEM_LIMIT or disk > DISK_LIMIT:
            print("Resources high, pausing cycle.")
        else:
            dynamic_x_flag_injection()
            process_x_flags()
            prune_completed_flags()
        time.sleep(10)

if __name__ == "__main__":
    main_loop()
