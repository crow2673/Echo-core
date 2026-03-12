import json, sys
from pathlib import Path

ECHO = Path.home() / "Echo"
STATE = ECHO / "memory" / "core_state_reasoning.json"

def load():
    if STATE.exists():
        return json.loads(STATE.read_text())
    return {"reasoning_history": [], "knowledge": {}, "X_flags": []}

def save(d):
    STATE.parent.mkdir(parents=True, exist_ok=True)
    STATE.write_text(json.dumps(d, indent=2) + "\n")

def main():
    if len(sys.argv) < 2:
        print("usage: reasoning_flag.py add <flag...> | list | clear")
        return 2

    cmd = sys.argv[1]
    d = load()

    if cmd == "add":
        flag = " ".join(sys.argv[2:]).strip()
        if not flag:
            print("no flag provided")
            return 2
        d.setdefault("X_flags", [])
        if flag not in d["X_flags"]:
            d["X_flags"].append(flag)
        save(d)
        print("[ok] queued:", flag)
        return 0

    if cmd == "list":
        for i, f in enumerate(d.get("X_flags", []), 1):
            print(f"{i}. {f}")
        return 0

    if cmd == "clear":
        d["X_flags"] = []
        save(d)
        print("[ok] cleared")
        return 0

    print("unknown cmd:", cmd)
    return 2

if __name__ == "__main__":
    raise SystemExit(main())
