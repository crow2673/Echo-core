#!/usr/bin/env python3
import json, subprocess, sys
from pathlib import Path

ROOT = Path.home() / "Echo"
REG = ROOT / "docs" / "actions.json"

def load():
    return json.loads(REG.read_text())["actions"]

def ls():
    for a in load():
        print(f'{a["id"]:16}  {a["label"]}')

def run(action_id):
    actions = {a["id"]: a for a in load()}
    if action_id not in actions:
        print("Unknown action:", action_id)
        ls()
        sys.exit(2)
    cmd = actions[action_id]["cmd"]
    print("Running:", " ".join(cmd))
    raise SystemExit(subprocess.call(cmd))

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: action_runner.py list | run <id>")
        sys.exit(2)
    if sys.argv[1] == "list":
        ls()
    elif sys.argv[1] == "run":
        run(sys.argv[2])
    else:
        sys.exit(2)
