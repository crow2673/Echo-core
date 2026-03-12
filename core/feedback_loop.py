#!/usr/bin/env python3
import json
from pathlib import Path
from datetime import datetime

BASE = Path(__file__).resolve().parents[1]
FEEDBACK_FILE = BASE / "memory/feedback_log.json"
REASONING_FILE = BASE / "memory/core_state_reasoning.json"

def load_feedback():
    if FEEDBACK_FILE.exists():
        return json.loads(FEEDBACK_FILE.read_text())
    return []

def save_feedback(data):
    FEEDBACK_FILE.write_text(json.dumps(data, indent=2))

def log_suggestions():
    if not REASONING_FILE.exists():
        return
    state = json.loads(REASONING_FILE.read_text())
    history = state.get("reasoning_history", [])
    feedback = load_feedback()
    seen = {f["how"][:100] for f in feedback}
    new_count = 0
    for entry in history:
        how = entry.get("how", "")
        key = how[:100]
        if key and key not in seen:
            feedback.append({
                "logged_at": datetime.now().isoformat(),
                "how": how,
                "why": entry.get("why", ""),
                "confidence": entry.get("confidence", 0),
                "outcome": "pending",
                "acted_on": False
            })
            seen.add(key)
            new_count += 1
    save_feedback(feedback)
    print(f"Logged {new_count} new suggestions ({len(feedback)} total)")

def build_outcome_context():
    feedback = load_feedback()
    if not feedback:
        return ""
    lines = ["Past reasoning outcomes (do not repeat pending suggestions):"]
    for f in feedback[-10:]:
        status = f.get("outcome", "pending")
        acted = "acted on" if f.get("acted_on") else "not acted on"
        date = f.get("logged_at", "")[:10]
        how = f.get("how", "")[:120]
        lines.append(f"- [{date}] [{status}] [{acted}] {how}")
    return "\n".join(lines)

def mark_outcome(how_snippet, outcome, acted_on=False):
    feedback = load_feedback()
    for f in feedback:
        if how_snippet.lower() in f.get("how", "").lower():
            f["outcome"] = outcome
            f["acted_on"] = acted_on
            f["resolved_at"] = datetime.now().isoformat()
    save_feedback(feedback)
    print(f"Marked: {how_snippet[:50]} -> {outcome}")

if __name__ == "__main__":
    log_suggestions()
    print()
    print(build_outcome_context())
