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
try:
    from core.semantic_matcher import match as semantic_match
    SEMANTIC = True
except Exception:
    SEMANTIC = False

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

    # Vast.ai status check
    if any(x in text for x in ["vast.ai", "vast ai", "machine 57470", "gpu rental", "rentals"]):
        action = next((a for a in actions if a["id"] == "vast_status"), None)
        if action:
            return action, {}

    # Registry / service verification
    if any(x in text for x in ["registry.json", "verify all", "services are actually running", "check services"]):
        action = next((a for a in actions if a["id"] == "healthcheck"), None)
        if action:
            return action, {}

    # Income path reasoning
    if any(x in text for x in ["income path", "income_knowledge", "activate next", "which income"]):
        action = next((a for a in actions if a["id"] == "golem_status"), None)
        if action:
            return action, {}

    # TODO review — suggest writing a draft if article topic found
    if any(x in text for x in ["review todo", "todo.md", "highest-value next action"]):
        action = next((a for a in actions if a["id"] == "query_ledger"), None)
        if action:
            return action, {}

    # System state summary — run healthcheck
    if any(x in text for x in ["echo system state", "system state", "current state", "summarize"]):
        action = next((a for a in actions if a["id"] == "healthcheck"), None)
        if action:
            return action, {}

    # World context / article topic — only if queue has fewer than 2 queued items
    if any(x in text for x in ["world_context", "trending topic", "write an article", "draft_queue"]):
        try:
            q = json.loads((Path.home() / "Echo/content/draft_queue.json").read_text())
            queued = [d for d in q if d.get("status") in ("queued", "pending_review")]
            if len(queued) >= 2:
                return None, None  # queue is full, skip
        except Exception:
            pass
        action = next((a for a in actions if a["id"] == "create_draft"), None)
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
        if SEMANTIC:
            action, env_vars, score = semantic_match(summary, actions)
            if action:
                log(f"semantic match: '{summary[:50]}' → {action['id']} (score={score:.3f})")
            else:
                # Fallback to keyword matching
                action, env_vars = match_action(summary, actions)
                if action:
                    log(f"keyword match: '{summary[:50]}' → {action['id']}")
        else:
            action, env_vars = match_action(summary, actions)

        if not action:
            continue

        # Don't act on safe=False actions autonomously
        if not action.get("safe", True):
            log(f"skipped unsafe action: {action['id']}")
            continue

        # Don't act on disabled actions
        if action.get("disabled", False):
            log(f"skipped disabled action: {action['id']}")
            continue

        # Cooldown check — prevent flood (e.g. create_draft max once per 24h)
        cooldown_hours = action.get("cooldown_hours", 0)
        if cooldown_hours > 0:
            from core.event_ledger import query_recent
            from datetime import timedelta
            recent_same = [
                e for e in query_recent(limit=50, source="governor")
                if action["id"] in e.get("summary", "")
                and (datetime.now() - datetime.fromisoformat(e["ts"])) < timedelta(hours=cooldown_hours)
            ]
            if recent_same:
                log(f"cooldown: {action['id']} fired {len(recent_same)}x in last {cooldown_hours}h, skipping")
                continue

        log(f"matched: '{summary[:60]}' → {action['id']}")
        success, output = execute_action(action, env_vars)

        score = 1.0 if success else -1.0
        log(f"  result: {'OK' if success else 'FAIL'} — {output[:100]}")
        # Mirror to Notion Actions database
        try:
            from core.notion_bridge import log_action_to_notion
            log_action_to_notion(action['id'], success, output[:300])
        except Exception:
            pass

        # Update standing task scores
        try:
            import json as _json
            from pathlib import Path as _Path
            _sf = _Path("/home/andrew/Echo/memory/standing_tasks.json")
            _data = _json.loads(_sf.read_text())
            for _t in _data["tasks"]:
                if _t["id"] == action["id"] or action["id"] in _t["task"]:
                    if success:
                        _t["wins"] = _t.get("wins", 0) + 1
                        _t["weight"] = min(2.0, _t.get("weight", 1.0) + 0.05)
                    else:
                        _t["losses"] = _t.get("losses", 0) + 1
                        if not _t.get("failure_immune", False):
                            _min = _t.get("min_weight", 0.1)
                            _t["weight"] = max(_min, _t.get("weight", 1.0) - 0.05)
            _sf.write_text(_json.dumps(_data, indent=2))
        except Exception:
            pass

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

    # Check Notion Build Queue for tasks from Claude/ChatGPT
    try:
        from core.notion_task_reader import run as check_build_queue
        check_build_queue()
    except Exception as e:
        log(f"notion_task_reader error: {e}")

if __name__ == "__main__":
    run()
