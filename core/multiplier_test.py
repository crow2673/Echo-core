import json
import random
from gpt_reasoner import gpt_reasoner

# --- Load core_state ---
with open("../memory/core_state.json", "r") as f:
    core_state = json.load(f)

# --- Define core survival skills with value scores ---
survival_skills = {
    "find_food": 5,
    "gather_water": 6,
    "build_shelter": 4,
    "basic_fabrication": 7,
    "crypto_mining": 9,  # example of income-generating skill
    "microtask_automation": 8
}

# --- Pick one random skill to test ---
new_flag = random.choice(list(survival_skills.keys()))
if new_flag not in core_state["X_flags"]:
    core_state["X_flags"].append(new_flag)
print(f"Added X_flag for testing: {new_flag}")

# --- Assign scores for prioritization ---
flag_scores = {flag: survival_skills.get(flag, 1) for flag in core_state["X_flags"]}

# --- Sort X_flags by score descending (highest utility first) ---
sorted_flags = sorted(core_state["X_flags"], key=lambda f: flag_scores[f], reverse=True)

# --- Guided reasoning cycle ---
for x_flag in sorted_flags:
    if x_flag not in core_state["knowledge"]:
        result = gpt_reasoner(x_flag, core_state)
        core_state["knowledge"][x_flag] = result
        core_state["reasoning_history"].append(result)
        print(f"Processed {x_flag}: {result}")
    else:
        print(f"Skipping {x_flag}, already known.")

# --- Save updated core_state ---
with open("../memory/core_state.json", "w") as f:
    json.dump(core_state, f, indent=2)

print("Test cycle complete. Core state updated.")
