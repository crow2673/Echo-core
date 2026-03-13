#!/usr/bin/env python3
"""
Echo Governor — Stage 6
Reads self_act reasoning from event ledger, matches to actions, executes, scores.
This is the closed loop: reason → act → score → learn.

Runs every 5 minutes via echo-governor.timer
"""
import json, re, subprocess, sys
from pathlib import Path
from datetime import datetime, timedelta

BASE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BASE))

from core.event_ledger import log_event, query_recent

ACTIONS_PATH = BASE / "docs/actions.json"
LOG = BASE / "logs/governor.log"

# How far back to look for unacted reasoning
LOOKBACK_MINUTES = 10

def log(msg):
    LOG.parent.mkdir(exist_ok=True)
    ts = datetime.now().strftime("%Y-%m-%d %H:%M")
    line = f"[{ts}] {msg}"
    print(line)
    with open(LOG, "a") as f:
        f.write(line + "\n")

def load_actions():
    raw = json.loads(ACTIONS_PATH.read_text())
    return raw if isinstance(raw, list) else raw.get("actions", [])

def get_recent_reasoning():
    """Get reasoning events from last LOOKBACK_MINUTES that suggest an action."""
    events = query_recent(limit=20, event_type="reasoning")
    cutoff = datetime.now() - timedelta(minutes=LOOKBACK_MINUTES)
    recent = []
    for e in events:
        try:
            ts = datetime.fromisoformat(e["ts"])
            if ts > cutoff:
                recent.append(e)
        except Exception:
            pass
    return recent

def match_action(reasoning_text, actions):
    """
    Try to match reasoning text to a concrete action.
    Returns (action, env_vars) or (None, None).
    """
    text = reasoning_text.lower()

    # Golem pricing — reasoning suggests lowering price
    if any(x in text for x in ["lower price", "reduce price", "drop price", "pricing too high", "adjust pricing"]):
        action = next((a for a in actions if a["id"] == "golem_pricing_update"), None)
        if action:
            return action, {"GOLEM_CPU": "0.00008", "GOLEM_DUR": "0.00002"}

    # Golem status check
    if any(x in text for x in ["golem status", "check golem", "golem node"]):
        action = next((a for a in actions if a["id"] == "golem_status"), None)
        if action:
            return action, {}

    # Health check
    if any(x in text for x in ["health check", "system status", "services down", "check services"]):
        action = next((a for a in actions if a["id"] == "healthcheck"), None)
        if action:
            return action, {}

    # Notify Andrew
    if any(x in text for x in ["notify andrew", "alert andrew", "send notification"]):
        action = next((a for a in actions if a["id"] == "notify_phone"), None)
        if action:
            # Extract message if possible
            msg = reasoning_text[:100]
            return action, {"ECHO_TITLE": "Echo Update", "ECHO_MSG": msg}

    # Query ledger
    if any(x in text for x in ["query ledger", "check ledger", "recent events"]):
        action = next((a for a in actions if a["id"] == "query_ledger"), None)
        if action:
            return action, {}

    return None, None

def execute_action(action, env_vars):
    """Execute an action and return (success, output)."""
    import os
    cmd = action.get("cmd", [])
    if not cmd:
        return False, "no cmd"

    env = os.environ.copy()
    env.update(env_vars)

    try:
        result = subprocess.run(
            cmd, env=env, capture_output=True, text=True, timeout=60
        )
        success = result.returncode == 0
        output = (result.stdout + result.stderr).strip()[:200]
        return success, output
    except Exception as e:
        return False, str(e)

def run():
    log("governor cycle started")
    actions = load_actions()
    recent = get_recent_reasoning()

    if not recent:
        log("no recent reasoning to act on")
        return

    acted = 0
    for event in recent:
        summary = event.get("summary", "")
        action, env_vars = match_action(summary, actions)

        if not action:
            continue

        # Don't act on safe=False actions autonomously
        if not action.get("safe", True):
            log(f"skipped unsafe action: {action['id']}")
            continue

        log(f"matched: '{summary[:60]}' → {action['id']}")
        success, output = execute_action(action, env_vars)

        score = 1.0 if success else -1.0
        log(f"  result: {'OK' if success else 'FAIL'} — {output[:100]}")

        log_event(
            "feedback",
            "governor",
            f"action={action['id']} success={success} reasoning='{summary[:80]}'",
            score=score
        )
        acted += 1

    # Score any unscored regret entries
    try:
        from core.regret_scorer import run as score_regrets
        score_regrets()
    except Exception as e:
        log(f"regret_scorer error: {e}")
    log(f"governor cycle done — acted on {acted}/{len(recent)} reasoning events")

if __name__ == "__main__":
    run()
