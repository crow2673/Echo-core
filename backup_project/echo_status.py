"""
name: Status
description: Show Echo's current status
type: python
"""

import json
from pathlib import Path

STATE_FILE = Path(__file__).parent / "echo_state.json"
MEMORY_FILE = Path(__file__).parent / "echo_memory.json"

def load_state():
    if STATE_FILE.exists():
        with open(STATE_FILE) as f:
            return json.load(f)
    return {}

def load_memory():
    if MEMORY_FILE.exists():
        with open(MEMORY_FILE) as f:
            return json.load(f)
    return []

def main():
    state = load_state()
    memory = load_memory()
    print("\n--- Echo Status ---")
    print(f"State: {state.get('build_state', {})}")
    print(f"Memory capsules: {len(memory)}")
    print("------------------\n")

if __name__ == "__main__":
    main()
