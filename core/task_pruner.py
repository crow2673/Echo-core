#!/usr/bin/env python3
"""
core/task_pruner.py — Strategic decay for Echo's standing task queue.

Prevents standing_tasks.json from becoming a digital attic.
Runs weekly via the dispatcher (skip_judgment: True).

Rules:
  1. Hard-cap self-generated tasks at 60. Remove lowest-weight oldest ones first.
  2. Remove near-duplicates: self-generated tasks with >60% keyword overlap
     with another task — keep the higher-weight version.
  3. Age-decay: self-generated tasks older than 45 days with weight < 0.8
     and wins/(wins+losses) < 0.35 are removed.
  4. Never touch core system tasks (no self_generated flag).
"""
import json
import re
from datetime import datetime, timedelta
from pathlib import Path

BASE = Path(__file__).resolve().parents[1]
TASKS_FILE = BASE / "memory" / "standing_tasks.json"
LOG = BASE / "logs" / "task_pruner.log"
LOG.parent.mkdir(exist_ok=True)

MAX_SELF_GENERATED = 60
AGE_DAYS = 45
AGE_WEIGHT_THRESHOLD = 0.8
AGE_WIN_RATE_THRESHOLD = 0.35
DEDUP_OVERLAP_THRESHOLD = 0.60

STOPWORDS = {
    "the", "and", "for", "this", "that", "with", "from", "into", "goal",
    "should", "would", "could", "will", "have", "been", "echo", "make",
    "using", "which", "when", "then", "also", "monitor", "review", "check",
    "ensure", "perform", "implement", "optimize", "improve", "system", "task",
    "service", "current", "regular", "daily", "weekly", "recent", "active",
}


def log(msg):
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{ts}] {msg}"
    print(line, flush=True)
    with open(LOG, "a") as f:
        f.write(line + "\n")


def _keywords(text: str) -> set:
    words = re.sub(r'[^a-z0-9 ]', ' ', text.lower()).split()
    return {w for w in words if len(w) >= 4 and w not in STOPWORDS}


def _win_rate(task: dict) -> float:
    wins = task.get("wins", 0)
    losses = task.get("losses", 0)
    total = wins + losses
    return wins / total if total > 0 else 0.5


def prune(dry_run: bool = False) -> dict:
    if not TASKS_FILE.exists():
        log("standing_tasks.json not found — skipping")
        return {"removed": 0, "kept": 0}

    data = json.loads(TASKS_FILE.read_text())
    tasks = data.get("tasks", [])

    system_tasks = [t for t in tasks if not t.get("self_generated")]
    self_tasks = [t for t in tasks if t.get("self_generated")]

    removed_ids = set()
    removal_reasons = {}

    now = datetime.now()
    cutoff = now - timedelta(days=AGE_DAYS)

    # Rule 3: Age-decay — old, low-weight, low-win-rate tasks
    for t in self_tasks:
        added = t.get("added_at", "")
        if not added:
            continue
        try:
            added_dt = datetime.fromisoformat(added)
        except Exception:
            continue
        if added_dt > cutoff:
            continue
        if t.get("weight", 1.0) >= AGE_WEIGHT_THRESHOLD:
            continue
        if _win_rate(t) >= AGE_WIN_RATE_THRESHOLD:
            continue
        removed_ids.add(t["id"])
        removal_reasons[t["id"]] = f"age-decay ({(now - added_dt).days}d old, weight={t.get('weight'):.2f}, WR={_win_rate(t):.0%})"

    # Rule 2: Near-duplicate removal — keep highest weight, remove rest
    active_self = [t for t in self_tasks if t["id"] not in removed_ids]
    # Sort highest weight first so we keep the better version
    active_self.sort(key=lambda t: t.get("weight", 0), reverse=True)
    seen_kw_sets = []

    for t in active_self:
        kw = _keywords(t.get("task", ""))
        if len(kw) < 3:
            continue
        for seen_kw in seen_kw_sets:
            if not seen_kw:
                continue
            overlap = len(kw & seen_kw) / max(len(kw | seen_kw), 1)
            if overlap >= DEDUP_OVERLAP_THRESHOLD:
                removed_ids.add(t["id"])
                removal_reasons[t["id"]] = f"near-duplicate ({overlap:.0%} overlap with higher-weight task)"
                break
        else:
            seen_kw_sets.append(kw)

    # Rule 1: Hard cap — if still over limit after dedup, remove oldest lowest-weight
    surviving = [t for t in self_tasks if t["id"] not in removed_ids]
    if len(surviving) > MAX_SELF_GENERATED:
        # Sort by weight asc then age desc (oldest, weakest first)
        surviving.sort(key=lambda t: (t.get("weight", 0), -(datetime.fromisoformat(t.get("added_at", "2000-01-01")).timestamp() if t.get("added_at") else 0)))
        excess = surviving[:len(surviving) - MAX_SELF_GENERATED]
        for t in excess:
            removed_ids.add(t["id"])
            removal_reasons[t["id"]] = f"hard-cap (>{MAX_SELF_GENERATED} self-generated tasks)"

    # Apply removals
    for tid, reason in removal_reasons.items():
        log(f"  REMOVE [{tid[:40]}]: {reason}")

    if not dry_run and removed_ids:
        kept_tasks = [t for t in tasks if t["id"] not in removed_ids]
        data["tasks"] = kept_tasks
        tmp = TASKS_FILE.with_suffix(".tmp")
        tmp.write_text(json.dumps(data, indent=2))
        tmp.rename(TASKS_FILE)

    result = {
        "removed": len(removed_ids),
        "kept": len(tasks) - len(removed_ids),
        "system_tasks": len(system_tasks),
        "self_tasks_before": len(self_tasks),
        "self_tasks_after": len(self_tasks) - len(removed_ids),
        "reasons": removal_reasons,
    }
    log(f"Prune complete — removed {result['removed']}, kept {result['kept']} (dry_run={dry_run})")
    return result


def run():
    log("task_pruner starting")
    result = prune(dry_run=False)
    if result["removed"] > 0:
        try:
            from core.notifier import notify
            notify(
                "Echo pruned task queue",
                f"Removed {result['removed']} stale/duplicate tasks.\n"
                f"Queue: {result['self_tasks_after']} self-generated + {result['system_tasks']} system tasks.",
                urgent=False,
            )
        except Exception:
            pass
    return result


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    result = prune(dry_run=args.dry_run)
    print(json.dumps(result, indent=2, default=str))
