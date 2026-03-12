import json
import random
from gpt_reasoner import gpt_reasoner

# --- Load core_state ---
with open("../memory/core_state.json", "r") as f:
    core_state = json.load(f)

# --- Define skills with base value (resource, unlock potential, cost) ---
skills = {
    "find_food": {"value": 5, "cost": 1},
    "gather_water": {"value": 6, "cost": 1},
    "build_shelter": {"value": 4, "cost": 2},
    "basic_fabrication": {"value": 7, "cost": 3},
    "crypto_mining": {"value": 9, "cost": 4},  # income-generating
    "microtask_automation": {"value": 8, "cost": 3},
    "advanced_tools": {"value": 10, "cost": 5}  # requires prior skills
}

# --- Evaluate resources and learned skills to adjust priority ---
def calculate_priority(flag, state):
    base = skills.get(flag, {"value": 1, "cost": 1})
    learned = flag in state["knowledge"]
    resource_multiplier = min(sum([s.get("value", 1) for s in skills.values() if s["value"] <= base["value"]]), 10)
    priority = (base["value"] * resource_multiplier) / base["cost"]
    if learned:
        priority = 0  # Skip already known skills
    return priority

# --- Randomly discover new tasks to simulate environment ---
discovered_flags = random.sample(list(skills.keys()), 2)
for f in discovered_flags:
    if f not in core_state["X_flags"]:
        core_state["X_flags"].append(f)
        print(f"Discovered new task: {f}")

# --- Sort X_flags by calculated priority descending ---
sorted_flags = sorted(core_state["X_flags"], key=lambda f: calculate_priority(f, core_state), reverse=True)

# --- Autonomous reasoning cycle ---
for x_flag in sorted_flags:
    if x_flag not in core_state["knowledge"]:
        result = gpt_reasoner(x_flag, core_state)
        core_state["knowledge"][x_flag] = result
        core_state["reasoning_history"].append(result)
        print(f"Processed {x_flag}: {result}")
    else:
        print(f"Skipping {x_flag}, already known.")

# --- Optionally prune low-priority flags to keep memory lean ---
core_state["X_flags"] = [f for f in core_state["X_flags"] if f not in core_state["knowledge"]]

# --- Save updated core_state ---
with open("../memory/core_state.json", "w") as f:
    json.dump(core_state, f, indent=2)

print("Autonomous multiplier cycle complete. Core state updated.")
