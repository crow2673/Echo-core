import json
from pathlib import Path
from core.identity import load_identity, assert_scope

# Load identity first (non-negotiable)
IDENTITY = load_identity()

# Load system contract
with open("echo_contract.json", "r") as f:
    contract = json.load(f)

root = Path(contract["root"]).expanduser().resolve()

# Enforce identity scope
assert_scope(root, IDENTITY)

state = {
    "pipelines": list((root / contract["pipelines"]).glob("*.py")),
    "models": list((root / contract["models"]).rglob("*.pkl")),
    "contracts": list(root.rglob("*contract*.json")),
}

print("Echo identity:")
print(" name:", IDENTITY["identity"]["name"])
print(" root:", IDENTITY["identity"]["root_path"])
print(" offline:", IDENTITY["identity"]["offline_first"])
print()

print("Echo state snapshot:")
for k, v in state.items():
    print(f"{k}: {len(v)}")
