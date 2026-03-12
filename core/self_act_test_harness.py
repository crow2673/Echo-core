import json
import random
from core.self_act_hybrid import weighted_reasoning_cycle, CORE_STATE_PATH

# --- Load core state ---
try:
    with open(CORE_STATE_PATH, "r") as f:
        core_state = json.load(f)
except FileNotFoundError:
    core_state = {
        "reasoning_history": [],
        "knowledge": {},
        "X_flags": [],
        "resources": {},
        "income_sources": {},
        "skills_needed": {}
    }

# --- Define a single "core skill" task for testing ---
core_skills = [
    "gather_water",
    "build_shelter",
    "fire_start",
    "find_food",
    "basic_navigation"
]

# --- Pick one at random ---
test_task = random.choice(core_skills)

# --- Inject into X_flags if not already present ---
if test_task not in core_state["X_flags"]:
    core_state["X_flags"].append(test_task)
    print(f"Injected test X_flag: {test_task}")

# --- Save updated core_state ---
with open(CORE_STATE_PATH, "w") as f:
    json.dump(core_state, f, indent=2)

# --- Run a single reasoning cycle ---
weighted_reasoning_cycle()

# --- Output results ---
with open(CORE_STATE_PATH, "r") as f:
    updated_state = json.load(f)

print("\n=== Test Harness Result ===")
print(f"Processed X_flags: {updated_state.get('X_flags', [])}")
print(f"Knowledge updates for test task: {updated_state['knowledge'].get(test_task, {})}")
