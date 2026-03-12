import json, time
from pathlib import Path

MEM = Path.home() / "Echo/memory/constraints.jsonl"
LOG = Path.home() / "Echo/memory/reachability_watch.log"

def load_constraints():
    if not MEM.exists():
        return []
    return [json.loads(l) for l in MEM.read_text().splitlines() if l.strip()]

def main():
    constraints = load_constraints()
    for c in constraints:
        if c.get("name") == "public_reachability" and c.get("status") == "deferred":
            with LOG.open("a") as f:
                f.write(f"[{time.ctime()}] Reachability constraint active. Watching for wake conditions.\n")

if __name__ == "__main__":
    main()
