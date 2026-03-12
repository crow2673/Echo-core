import json
import psutil
import subprocess

core_state_path = "../memory/core_state.json"

# --- Load core_state ---
with open(core_state_path, "r") as f:
    core_state = json.load(f)

# --- Example live resource tracking ---
# CPU & memory availability
cpu_percent = psutil.cpu_percent()
memory_percent = psutil.virtual_memory().percent

# Disk space (could represent materials storage)
disk_percent = psutil.disk_usage('/').percent

# Example: Income from microtasks / mining
try:
    mining_output = float(subprocess.check_output(["yagna", "activity", "status"]).decode().strip())
except:
    mining_output = 0

# Update core_state resources
core_state["resources"] = {
    "cpu_percent": cpu_percent,
    "memory_percent": memory_percent,
    "disk_percent": disk_percent,
    "income": core_state.get("resources", {}).get("income", 0) + mining_output
}

# Save updated core_state
with open(core_state_path, "w") as f:
    json.dump(core_state, f, indent=2)

print("Live resources updated:", core_state["resources"])
