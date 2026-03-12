import time
import json
from gpt_reasoner import gpt_reasoner
import resource_tracker  # updates core_state["resources"]
import income_feed       # custom module that fetches live income per task

CORE_STATE_PATH = "../memory/core_state.json"

# Load or initialize core_state
try:
    with open(CORE_STATE_PATH, "r") as f:
        core_state = json.load(f)
except FileNotFoundError:
    core_state = {
        "reasoning_history": [],
        "knowledge": {},
        "X_flags": [],
        "resources": {},
        "income_sources": {},  # {"task_name": reward_value}
        "skills_needed": {}    # {"skill_name": {"prereq": [], "task": "task_name"}}
    }

def update_income_sources():
    """
    Fetch live task rewards and update core_state["income_sources"]
    """
    live_income = income_feed.get_live_income()  # returns dict {task: reward}
    core_state["income_sources"].update(live_income)
    print(f"Live income updated: {live_income}")

def dynamic_x_flag_injection():
    """
    Inject X_flags based on:
    - knowledge gaps
    - highest live income potential
    """
    potential_flags = []
    for skill, info in core_state.get("skills_needed", {}).items():
        if skill not in core_state["knowledge"]:
            task = info.get("task")
            reward = core_state.get("income_sources", {}).get(task, 0)
            if reward > 0 and skill not in core_state["X_flags"]:
                potential_flags.append((skill, reward))
    # Sort highest reward first
    potential_flags.sort(key=lambda x: x[1], reverse=True)
    for skill, reward in potential_flags:
        core_state["X_flags"].append(skill)
        print(f"Added X_flag based on live income: {skill} (reward: {reward})")

def prune_x_flags():
    """
    Remove X_flags that are already learned
    """
    pruned_flags = []
    for flag in list(core_state.get("X_flags", [])):
        if flag in core_state.get("knowledge", {}):
            core_state["X_flags"].remove(flag)
            pruned_flags.append(flag)
    if pruned_flags:
        print(f"Pruned X_flags: {pruned_flags}")

def weighted_reasoning_cycle():
    # Update live resources
    resource_tracker  # updates core_state["resources"]

    cpu_limit = 80.0
    mem_limit = 80.0
    disk_limit = 90.0
    resources = core_state.get("resources", {})
    cpu = resources.get("cpu_percent", 0)
    mem = resources.get("memory_percent", 0)
    disk = resources.get("disk_percent", 0)

    if cpu > cpu_limit or mem > mem_limit or disk > disk_limit:
        print("Resources high, delaying reasoning cycle.")
        return

    # Update live income
    update_income_sources()

    # Inject new X_flags based on live income
    dynamic_x_flag_injection()

    # Process X_flags with GPT-based reasoning
    for x_flag in list(core_state.get("X_flags", [])):
        if x_flag in core_state.get("knowledge", {}):
            continue
        result = gpt_reasoner(x_flag, core_state)
        core_state["reasoning_history"].append(result)
        core_state["knowledge"][x_flag] = result
        print(f"Processed {x_flag}: {result}")

    # Prune learned flags
    prune_x_flags()

    # Save updated state
    with open(CORE_STATE_PATH, "w") as f:
        json.dump(core_state, f, indent=2)

if __name__ == "__main__":
    while True:
        print("Echo alive - Starting live-income reasoning cycle.")
        weighted_reasoning_cycle()
        time.sleep(10)
