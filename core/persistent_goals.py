#!/usr/bin/env python3
"""
core/persistent_goals.py — Goals Echo keeps attempting until solved or blocked.

Unlike standing tasks (which rotate), persistent goals are worked on repeatedly
with different approaches until they're solved, Andrew unblocks them, or Echo
determines they're genuinely impossible without human help.

Echo uses the full agent loop (with tools) to attempt each goal.
After 3 failed attempts hitting the same blocker, Andrew gets a Telegram message.
"""
import json
from datetime import datetime
from pathlib import Path

BASE = Path(__file__).resolve().parents[1]
GOALS_FILE = BASE / "memory/persistent_goals.json"

MAX_ATTEMPTS_BEFORE_FLAG = 3
MAX_ATTEMPTS_BEFORE_ABANDON = 15
ATTEMPT_COOLDOWN_HOURS = 6


def load_goals() -> dict:
    if GOALS_FILE.exists():
        try:
            return json.loads(GOALS_FILE.read_text())
        except Exception:
            pass
    return {"goals": []}


def save_goals(data: dict):
    tmp = GOALS_FILE.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, indent=2, default=str))
    tmp.rename(GOALS_FILE)


def get_active_goals() -> list:
    data = load_goals()
    now = datetime.now()
    active = []
    for g in data["goals"]:
        # needs_andrew = waiting on Andrew, don't retry until resolved
        if g.get("status") not in ("solved", "abandoned", "needs_andrew", "needs_review"):
            # Respect attempt cooldown
            last = g.get("last_attempt")
            if last:
                try:
                    hours_since = (now - datetime.fromisoformat(last)).total_seconds() / 3600
                    if hours_since < ATTEMPT_COOLDOWN_HOURS:
                        continue
                except Exception:
                    pass
            active.append(g)
    return active


def pick_goal() -> dict | None:
    """Pick the highest-priority unsolved goal to attempt this cycle."""
    active = get_active_goals()
    if not active:
        return None
    # Prioritize goals with fewer attempts (newer problems first)
    active.sort(key=lambda g: len(g.get("attempts", [])))
    return active[0]


def record_attempt(
    goal_id: str,
    approach: str,
    result: str,
    blocker: str = "",
    verified: bool = False,
    evidence: str = "",
):
    data = load_goals()
    now = datetime.now().isoformat()
    for g in data["goals"]:
        if g["id"] == goal_id:
            g.setdefault("attempts", []).append({
                "ts": now,
                "approach": approach[:300],
                "result": result[:500],
                "blocker": blocker,
                "verified": verified,
                "evidence": evidence[:500],
            })
            g["last_attempt"] = now
            g["attempts"] = g["attempts"][-20:]  # cap history

            # Check if solved
            if verified:
                g["status"] = "solved"
                g["solved_at"] = now
                g["solution_evidence"] = evidence[:1000]

            # Check if blocked by human-only requirement
            human_blockers = ["phone", "sms", "bank", "tax", "payment", "identity", "credit card"]
            if not verified and any(b in (result + blocker).lower() for b in human_blockers):
                g["status"] = "needs_andrew"
                g["andrew_flagged"] = False  # will be flagged next cycle

            # Flag Andrew if too many failed attempts
            attempts = g.get("attempts", [])
            if not verified and len(attempts) >= MAX_ATTEMPTS_BEFORE_FLAG and g.get("status") == "active":
                g["status"] = "needs_andrew"
                g["andrew_flagged"] = False

            # Hard cap: auto-abandon if hammering for too long with no progress
            if not verified and len(attempts) >= MAX_ATTEMPTS_BEFORE_ABANDON:
                g["status"] = "abandoned"
                g["abandoned_at"] = now
                g["abandon_reason"] = f"auto-abandoned after {len(attempts)} attempts with no resolution"

            # Propagate status back to gap_index (Temporal Mirror linkage)
            if g.get("status") in ("needs_andrew", "solved") and g.get("gap_id"):
                _update_gap_index(g["gap_id"], g["status"], g["id"])

            break
    save_goals(data)


def mark_goal_solved(goal_id: str, evidence: str, verified_by: str) -> bool:
    """Resolve a goal only with explicit evidence and an identified verifier."""
    if not evidence.strip() or not verified_by.strip():
        return False
    data = load_goals()
    for goal in data["goals"]:
        if goal["id"] == goal_id:
            goal["status"] = "solved"
            goal["solved_at"] = datetime.now().isoformat()
            goal["solution_evidence"] = evidence[:1000]
            goal["verified_by"] = verified_by[:100]
            save_goals(data)
            return True
    return False


def flag_unverified_solutions() -> list[str]:
    """Move legacy solved goals without evidence into review instead of trusting prose."""
    data = load_goals()
    flagged = []
    for goal in data["goals"]:
        if goal.get("status") == "solved" and not goal.get("solution_evidence"):
            goal["status"] = "needs_review"
            goal["review_reason"] = "legacy solution has no independent verification evidence"
            flagged.append(goal["id"])
    if flagged:
        save_goals(data)
    return flagged


def _update_gap_index(gap_id: str, new_status: str, goal_id: str):
    """Propagate goal resolution status back to gap_index.json."""
    gap_index_file = BASE / "memory" / "gap_index.json"
    if not gap_index_file.exists():
        return
    try:
        gap_index = json.loads(gap_index_file.read_text())
        gap = gap_index.get("gaps", {}).get(gap_id)
        if not gap:
            return
        # Map goal status → gap status
        status_map = {"needs_andrew": "escalated", "solved": "resolved"}
        gap["status"] = status_map.get(new_status, gap["status"])
        gap["goal_id"] = goal_id
        gap["updated_at"] = datetime.now().isoformat()
        tmp = gap_index_file.with_suffix(".tmp")
        tmp.write_text(json.dumps(gap_index, indent=2))
        tmp.rename(gap_index_file)
    except Exception:
        pass


def add_goal(
    goal_id: str,
    description: str,
    source: str = "echo",
    gap_id: str | None = None,
    success_criteria: str = "",
    verification: dict | None = None,
):
    """Add a new persistent goal if it doesn't already exist."""
    data = load_goals()
    existing_ids = {g["id"] for g in data["goals"]}
    if goal_id in existing_ids:
        return
    data["goals"].append({
        "id": goal_id,
        "description": description,
        "created": datetime.now().isoformat(),
        "source": source,
        "status": "active",
        "attempts": [],
        "last_attempt": None,
        "andrew_flagged": False,
        "gap_id": gap_id,
        "success_criteria": success_criteria or f"Independent evidence confirms: {description[:300]}",
        "verification_required": True,
        "verification": verification,
    })
    save_goals(data)


def flag_andrew_if_needed():
    """Send Telegram for any goals that are stuck and haven't been flagged yet."""
    data = load_goals()
    changed = False
    flagged = []
    for g in data["goals"]:
        if g.get("status") == "needs_andrew" and not g.get("andrew_flagged"):
            flagged.append(g)
            g["andrew_flagged"] = True
            changed = True
    if changed:
        save_goals(data)
    if flagged:
        try:
            from core.notifier import notify
            for g in flagged:
                attempts = g.get("attempts", [])
                last_result = attempts[-1].get("result", "unknown") if attempts else "no attempts"
                msg = (
                    f"Stuck on goal: {g['description'][:100]}\n"
                    f"Tried {len(attempts)} times. Last result: {last_result[:200]}\n"
                    f"Need your help to unblock this."
                )
                notify("Echo needs help", msg)
        except Exception:
            pass


def promote_known_gaps():
    """
    Read known_gaps.md and promote SETUP BLOCKERS into persistent goals.
    Echo will attempt to solve them herself before flagging Andrew.
    """
    gaps_file = BASE / "memory/known_gaps.md"
    if not gaps_file.exists():
        return

    content = gaps_file.read_text()
    data = load_goals()
    existing_ids = {g["id"] for g in data["goals"]}

    # Known income blockers to promote
    blockers = [
        {
            "id": "reddit_credentials",
            "description": "Get Reddit credentials to enable Fiverr outreach — attempt account creation via Playwright or find alternative outreach channels",
            "keywords": ["REDDIT_USERNAME", "reddit_password"],
        },
        {
            "id": "medium_token",
            "description": "Get Medium integration token to enable Partner Program earnings — attempt Google SSO account creation and token generation",
            "keywords": ["MEDIUM_TOKEN", "medium partner"],
        },
        {
            "id": "devto_api_key",
            "description": "Get Dev.to API key to enable direct publishing — attempt account creation and API key generation via Playwright",
            "keywords": ["DEVTO_API_KEY", "dev.to"],
        },
    ]

    changed = False
    for b in blockers:
        if b["id"] in existing_ids:
            continue
        if any(kw.lower() in content.lower() for kw in b["keywords"]):
            data["goals"].append({
                "id": b["id"],
                "description": b["description"],
                "created": datetime.now().isoformat(),
                "source": "known_gaps",
                "status": "active",
                "attempts": [],
                "last_attempt": None,
                "andrew_flagged": False,
            })
            changed = True

    if changed:
        save_goals(data)


if __name__ == "__main__":
    promote_known_gaps()
    goals = get_active_goals()
    print(f"Active goals: {len(goals)}")
    for g in goals:
        print(f"  [{g['status']}] {g['id']}: {g['description'][:60]}")
