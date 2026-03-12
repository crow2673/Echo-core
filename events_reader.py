import json
from pathlib import Path
from collections import Counter

EVENTS_FILE = Path("echo_events.ndjson")

def tail_events(n=50):
    if not EVENTS_FILE.exists():
        return []
    # cheap tail: read all lines if file isn't massive; if it grows huge we can optimize later
    lines = EVENTS_FILE.read_text().splitlines()[-n:]
    events = []
    for line in lines:
        line = line.strip()
        if not line:
            continue
        try:
            events.append(json.loads(line))
        except json.JSONDecodeError:
            pass
    return events

def summarize_events(n=50):
    evs = tail_events(n)
    if not evs:
        return "No recent events."
    actions = Counter()
    glml_vals = []
    for e in evs:
        if isinstance(e, dict):
            if "action" in e:
                actions[str(e["action"])] += 1
            if "glml" in e:
                try:
                    glml_vals.append(float(e["glml"]))
                except Exception:
                    pass
    action_part = ", ".join(f"{k}:{v}" for k,v in actions.most_common(8)) or "none"
    glml_part = ""
    if glml_vals:
        glml_part = f" | glml last={glml_vals[-1]:.4f} min={min(glml_vals):.4f} max={max(glml_vals):.4f}"
    return f"Recent events (last {len(evs)}): actions[{action_part}]{glml_part}"

if __name__ == "__main__":
    print(summarize_events(50))
