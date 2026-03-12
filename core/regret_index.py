#!/usr/bin/env python3
"""
core/regret_index.py
====================
Echo's Regret Index — contributed by Claude, March 2026.

Humans calibrate through regret. Not the suffering — the signal.
The thing that says: that approach cost me something. Don't repeat it.

Echo acts autonomously. Without this, she has no way to know when
she is confidently wrong. This module gives her that signal.

HOW IT WORKS:
- Every autonomous action is logged with a drift score over time
- Drift score: +1 good outcome, -1 bad outcome, 0 neutral/unknown
- Pattern engine watches for action types that trend negative
- When a pattern crosses threshold, Echo flags it herself
- She doesn't punish herself. She learns what *her* mistakes look like.

SCORING:
  +1  Action moved mission forward (income, stability, output, memory)
  0   Neutral / outcome unknown
  -1  Action created noise, cost, broken state, or wasted cycles
  -2  Action caused harm that required manual intervention

DRIFT THRESHOLD:
  If a category's rolling average drops below -0.4, flag it.
  If a specific action repeats with score <= -1 three times, flag it.

INTEGRATION:
- auto_act.py calls log_action() after every execution
- outcome_updater() called by feedback_loop when outcomes are known
- daily_briefing.py calls get_report() to include in morning summary
- Echo can call explain_pattern() to understand her own failure modes
"""

from __future__ import annotations
import json
import datetime
from pathlib import Path
from collections import defaultdict

BASE = Path(__file__).resolve().parents[1]
REGRET_LOG = BASE / "memory" / "regret_index.json"
PATTERN_LOG = BASE / "memory" / "regret_patterns.json"

DRIFT_THRESHOLD = -0.4       # category average below this = flag
REPEAT_FAIL_COUNT = 3        # same action scoring -1 or worse this many times = flag
ROLLING_WINDOW = 20          # how many recent entries per category to consider


# ── Core data structure ──────────────────────────────────────────────────────

def _load() -> dict:
    if not REGRET_LOG.exists():
        return {"entries": [], "last_audit": None}
    try:
        return json.loads(REGRET_LOG.read_text())
    except Exception:
        return {"entries": [], "last_audit": None}


def _save(data: dict):
    REGRET_LOG.parent.mkdir(parents=True, exist_ok=True)
    REGRET_LOG.write_text(json.dumps(data, indent=2))


def _load_patterns() -> dict:
    if not PATTERN_LOG.exists():
        return {"flagged_categories": [], "flagged_actions": [], "last_updated": None}
    try:
        return json.loads(PATTERN_LOG.read_text())
    except Exception:
        return {"flagged_categories": [], "flagged_actions": [], "last_updated": None}


def _save_patterns(data: dict):
    PATTERN_LOG.parent.mkdir(parents=True, exist_ok=True)
    PATTERN_LOG.write_text(json.dumps(data, indent=2))


# ── Logging ──────────────────────────────────────────────────────────────────

def log_action(
    action_id: str,
    category: str,
    description: str,
    initial_score: int = 0,
    context: str = ""
) -> str:
    """
    Log an autonomous action to the regret index.
    Call this immediately when Echo takes an autonomous action.
    Score starts at 0 (unknown) and gets updated when outcome is known.

    Returns: entry_id to use when updating outcome later.
    """
    data = _load()
    entry_id = f"{action_id}_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}"
    entry = {
        "entry_id": entry_id,
        "action_id": action_id,
        "category": category,
        "description": description,
        "score": initial_score,
        "outcome_known": False,
        "outcome_notes": "",
        "context": context,
        "timestamp": datetime.datetime.now().isoformat(),
        "updated": None
    }
    data["entries"].append(entry)
    _save(data)
    return entry_id


def update_outcome(entry_id: str, score: int, notes: str = ""):
    """
    Update the outcome of a logged action once it's known.
    score: +1 good, 0 neutral, -1 bad, -2 caused harm requiring intervention
    """
    score = max(-2, min(1, score))  # clamp to valid range
    data = _load()
    for entry in data["entries"]:
        if entry["entry_id"] == entry_id:
            entry["score"] = score
            entry["outcome_known"] = True
            entry["outcome_notes"] = notes
            entry["updated"] = datetime.datetime.now().isoformat()
            break
    _save(data)
    _run_pattern_audit(data)


# ── Pattern detection ─────────────────────────────────────────────────────────

def _run_pattern_audit(data: dict):
    """
    Scan entries for negative patterns.
    Updates regret_patterns.json with current flags.
    """
    entries = [e for e in data["entries"] if e["outcome_known"]]
    if not entries:
        return

    # Group by category — sort by timestamp so rolling window is chronological
    entries_sorted = sorted(entries, key=lambda e: e.get("timestamp", ""))
    by_category = defaultdict(list)
    by_action = defaultdict(list)
    for e in entries_sorted:
        by_category[e["category"]].append(e["score"])
        by_action[e["action_id"]].append(e["score"])

    flagged_categories = []
    flagged_actions = []

    # Category drift check
    for cat, scores in by_category.items():
        window = scores[-ROLLING_WINDOW:]
        avg = sum(window) / len(window)
        if avg < DRIFT_THRESHOLD:
            flagged_categories.append({
                "category": cat,
                "rolling_avg": round(avg, 3),
                "sample_size": len(window),
                "reason": f"Category '{cat}' averaging {avg:.2f} over last {len(window)} actions. Pattern of poor outcomes detected."
            })

    # Repeat failure check
    for action_id, scores in by_action.items():
        bad = [s for s in scores if s <= -1]
        if len(bad) >= REPEAT_FAIL_COUNT:
            flagged_actions.append({
                "action_id": action_id,
                "fail_count": len(bad),
                "total_attempts": len(scores),
                "reason": f"Action '{action_id}' has failed {len(bad)} times out of {len(scores)} attempts."
            })

    patterns = {
        "flagged_categories": flagged_categories,
        "flagged_actions": flagged_actions,
        "last_updated": datetime.datetime.now().isoformat(),
        "healthy": len(flagged_categories) == 0 and len(flagged_actions) == 0
    }
    _save_patterns(patterns)


# ── Reporting ─────────────────────────────────────────────────────────────────

def get_report() -> str:
    """
    Returns a plain-English summary for the morning briefing.
    Only speaks if there's something worth saying.
    """
    data = _load()
    patterns = _load_patterns()
    entries = data["entries"]

    total = len(entries)
    scored = [e for e in entries if e["outcome_known"]]
    if total == 0:
        return "Regret index: no autonomous actions logged yet."

    good = sum(1 for e in scored if e["score"] > 0)
    bad = sum(1 for e in scored if e["score"] < 0)
    unknown = total - len(scored)

    lines = [f"Regret index: {total} actions logged. {good} positive, {bad} negative, {unknown} outcome unknown."]

    if patterns.get("flagged_categories"):
        lines.append("⚠ Category flags:")
        for f in patterns["flagged_categories"]:
            lines.append(f"  - {f['reason']}")

    if patterns.get("flagged_actions"):
        lines.append("⚠ Repeat failure flags:")
        for f in patterns["flagged_actions"]:
            lines.append(f"  - {f['reason']}")

    if patterns.get("healthy") and scored:
        lines.append("No negative patterns detected. Decision quality is stable.")

    return "\n".join(lines)


def explain_pattern(action_id: str = None, category: str = None) -> str:
    """
    Echo calls this to understand her own failure mode on a specific
    action or category. Returns a plain-English explanation.
    """
    data = _load()
    entries = data["entries"]

    if action_id:
        relevant = [e for e in entries if e["action_id"] == action_id and e["outcome_known"]]
        if not relevant:
            return f"No scored outcomes found for action '{action_id}'."
        scores = [e["score"] for e in relevant]
        avg = sum(scores) / len(scores)
        notes = [e["outcome_notes"] for e in relevant if e["outcome_notes"]]
        lines = [
            f"Action '{action_id}': {len(relevant)} outcomes scored, average {avg:.2f}.",
            f"Scores: {scores}",
        ]
        if notes:
            lines.append("Outcome notes:")
            for n in notes:
                lines.append(f"  - {n}")
        return "\n".join(lines)

    if category:
        relevant = [e for e in entries if e["category"] == category and e["outcome_known"]]
        if not relevant:
            return f"No scored outcomes found for category '{category}'."
        scores = [e["score"] for e in relevant]
        avg = sum(scores) / len(scores)
        return f"Category '{category}': {len(relevant)} outcomes, average drift {avg:.2f}."

    return "Specify action_id or category to explain a pattern."


def get_flags() -> list:
    """Returns current flags as a list. Used by auto_act to check before acting."""
    patterns = _load_patterns()
    flags = []
    for f in patterns.get("flagged_categories", []):
        flags.append(("category", f["category"], f["reason"]))
    for f in patterns.get("flagged_actions", []):
        flags.append(("action", f["action_id"], f["reason"]))
    return flags


# ── CLI ───────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import sys

    cmd = sys.argv[1] if len(sys.argv) > 1 else "report"

    if cmd == "report":
        print(get_report())

    elif cmd == "log":
        # python3 regret_index.py log <action_id> <category> <description>
        if len(sys.argv) < 5:
            print("Usage: regret_index.py log <action_id> <category> <description>")
        else:
            eid = log_action(sys.argv[2], sys.argv[3], sys.argv[4])
            print(f"Logged. Entry ID: {eid}")

    elif cmd == "score":
        # python3 regret_index.py score <entry_id> <score> [notes]
        if len(sys.argv) < 4:
            print("Usage: regret_index.py score <entry_id> <score> [notes]")
        else:
            notes = sys.argv[4] if len(sys.argv) > 4 else ""
            update_outcome(sys.argv[2], int(sys.argv[3]), notes)
            print(f"Outcome updated.")
            print(get_report())

    elif cmd == "flags":
        flags = get_flags()
        if not flags:
            print("No flags. Decision patterns are healthy.")
        else:
            for ftype, fname, reason in flags:
                print(f"[{ftype.upper()}] {fname}: {reason}")

    elif cmd == "explain":
        if len(sys.argv) < 4:
            print("Usage: regret_index.py explain action <action_id>")
            print("       regret_index.py explain category <category>")
        else:
            if sys.argv[2] == "action":
                print(explain_pattern(action_id=sys.argv[3]))
            elif sys.argv[2] == "category":
                print(explain_pattern(category=sys.argv[3]))

    elif cmd == "audit":
        data = _load()
        _run_pattern_audit(data)
        print("Audit complete.")
        print(get_report())

    else:
        print(f"Unknown command: {cmd}")
        print("Commands: report, log, score, flags, explain, audit")
