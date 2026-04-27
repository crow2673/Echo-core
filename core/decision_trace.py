#!/usr/bin/env python3
"""
decision_trace.py — Unified decision audit trail for Echo
Records every significant decision: intent, plan, action, result, verified, source.
"""
import json
import time
from datetime import datetime, timedelta
from pathlib import Path

BASE = Path(__file__).resolve().parents[1]
TRACE_FILE = BASE / "memory/decision_trace.jsonl"
LOG = BASE / "logs/decision_trace.log"


def log(msg):
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"[trace] {msg}", flush=True)
    try:
        LOG.parent.mkdir(exist_ok=True)
        with open(LOG, "a") as f:
            f.write(f"{ts} — {msg}\n")
    except Exception:
        pass


def record(intent: str, plan: str = "", reason: str = "", action: str = "",
           result: str = "", verified: bool = False, source: str = "local",
           duration_ms: int = 0, **extra):
    entry = {
        "timestamp": datetime.now().isoformat(),
        "intent": intent,
        "plan": plan,
        "reason": reason,
        "action": action,
        "result": result,
        "verified": verified,
        "source": source,
        "duration_ms": duration_ms,
    }
    entry.update(extra)
    try:
        TRACE_FILE.parent.mkdir(parents=True, exist_ok=True)
        with open(TRACE_FILE, "a") as f:
            f.write(json.dumps(entry) + "\n")
        log(f"{intent} | verified={verified}")
    except Exception as e:
        log(f"Failed to write trace: {e}")


def trace_plan(plan: dict, result: str = "", verified: bool = False):
    """
    Record a full plan execution from echo_planner.
    Extracts all relevant fields automatically.
    """
    goal = plan.get("goal", "unknown")
    status = plan.get("status", "unknown")
    steps = plan.get("steps", [])
    step_summary = "; ".join(f"step{i+1}:{s}" for i, s in enumerate(steps[:5]) if s)
    record(
        intent=goal,
        plan=step_summary,
        action=f"plan executed ({len(steps)} steps)",
        result=result,
        verified=verified,
        source="planner",
    )


def load_recent(n=50):
    """Load the last N trace entries."""
    if not TRACE_FILE.exists():
        return []
    entries = []
    for line in TRACE_FILE.read_text().strip().splitlines():
        if not line:
            continue
        try:
            entries.append(json.loads(line))
        except Exception:
            pass
    return entries[-n:]


def print_recent(n=20):
    """Print recent decision trace in human-readable format."""
    entries = load_recent(n)
    if not entries:
        print("No decision trace entries yet.")
        return
    print(f"\n=== DECISION TRACE (last {len(entries)}) ===")
    for e in entries:
        ts = e.get("timestamp", "?")[:16]
        intent = e.get("intent", "?")
        verified = e.get("verified", False)
        result = e.get("result", "")[:60]
        print(f"  [{ts}] {intent} | verified={verified} | {result}")


def get_summary_stats(days=7) -> dict:
    """Return summary stats for briefing/governor."""
    cutoff = (datetime.now() - timedelta(days=days)).isoformat()
    entries = load_recent(500)
    recent = [e for e in entries if e.get("timestamp", "") >= cutoff]
    total = len(recent)
    intents = {}
    for e in recent:
        intent = e.get("intent", "unknown")
        intents[intent] = intents.get(intent, 0) + 1
    top_intents = sorted(intents.items(), key=lambda x: x[1], reverse=True)[:5]
    verified = sum(1 for e in recent if e.get("verified", False))
    return {
        "total": total,
        "verified": verified,
        "top_intents": top_intents,
        "period_days": days,
    }


if __name__ == "__main__":
    print_recent()
    stats = get_summary_stats()
    print(f"\n=== DECISION TRACE STATS ===")
    print(f"Total decisions: {stats['total']}")
