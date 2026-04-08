#!/usr/bin/env python3
"""
decision_trace.py — Unified decision audit trail for Echo
Records every significant decision: intent, plan, action, result, verified, source.
Thin layer — no new loops. Plugs into planner, verify, reach, daemon.

Every trace entry:
{
  "timestamp": "...",
  "intent": "trade_execute",
  "plan": "what Echo decided to do",
  "reason": "why",
  "action": "what was executed",
  "result": "what happened",
  "verified": true/false,
  "source": "local" | "claude" | "timer",
  "duration_ms": 0
}
"""
import json
import time
from pathlib import Path
from datetime import datetime

BASE = Path(__file__).resolve().parents[1]
TRACE_FILE = BASE / "memory/decision_trace.jsonl"
LOG = BASE / "logs/decision_trace.log"

def log(msg):
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"[trace] {msg}")
    try:
        with open(LOG, "a") as f:
            f.write(f"{ts} — {msg}\n")
    except Exception:
        pass

def record(intent, plan="", reason="", action="", result="",
           verified=None, source="local", duration_ms=0, extra=None):
    """
    Record a decision trace entry.
    Call this anywhere Echo makes a significant decision.
    """
    entry = {
        "timestamp": datetime.now().isoformat(),
        "intent": intent,
        "plan": plan[:200] if plan else "",
        "reason": reason[:200] if reason else "",
        "action": action[:200] if action else "",
        "result": result[:200] if result else "",
        "verified": verified,
        "source": source,
        "duration_ms": round(duration_ms),
    }
    if extra:
        entry["extra"] = extra

    try:
        with open(TRACE_FILE, "a") as f:
            f.write(json.dumps(entry) + "\n")
    except Exception as e:
        log(f"Failed to write trace: {e}")

    log(f"{intent} | {source} | verified={verified} | {action[:60]}")
    return entry

def trace_plan(plan_result, source="local", duration_ms=0):
    """
    Record a full plan execution from echo_planner.
    Extracts all relevant fields automatically.
    """
    goal = plan_result.get("goal", "")
    status = plan_result.get("status", "unknown")
    steps = plan_result.get("steps", [])
    results = plan_result.get("results", [])

    for i, step in enumerate(steps):
        result_entry = results[i] if i < len(results) else {}
        result = result_entry.get("result", {})
        verification = result_entry.get("verification", {})

        record(
            intent=step.get("intent", "unknown"),
            plan=goal,
            reason=step.get("description", ""),
            action=f"Step {step.get('step', i+1)} of {len(steps)}",
            result=str(result.get("stdout", result.get("error", "")))[:200],
            verified=verification.get("passed") if verification else None,
            source=source,
            duration_ms=duration_ms / len(steps) if steps else 0
        )

def load_recent(n=20):
    """Load the last N trace entries."""
    if not TRACE_FILE.exists():
        return []
    lines = TRACE_FILE.read_text().strip().splitlines()
    entries = []
    for line in lines[-n:]:
        try:
            entries.append(json.loads(line))
        except Exception:
            continue
    return entries

def print_recent(n=20):
    """Print recent decision trace in human-readable format."""
    entries = load_recent(n)
    if not entries:
        print("No decision trace entries yet.")
        return
    print(f"\n=== DECISION TRACE (last {len(entries)}) ===")
    for e in entries:
        ts = e["timestamp"][:16]
        intent = e["intent"]
        source = e["source"]
        verified = "✅" if e["verified"] else ("❌" if e["verified"] is False else "—")
        action = e["action"][:50]
        result = e["result"][:60]
        print(f"{ts} | {intent:15} | {source:6} | {verified} | {action}")
        if result:
            print(f"              └─ {result}")
    print("==========================================\n")

def get_summary_stats():
    """Return summary stats for briefing/governor."""
    entries = load_recent(100)
    if not entries:
        return {"total": 0}
    total = len(entries)
    verified = sum(1 for e in entries if e.get("verified") is True)
    failed = sum(1 for e in entries if e.get("verified") is False)
    api_calls = sum(1 for e in entries if e.get("source") == "claude")
    intents = {}
    for e in entries:
        intent = e.get("intent", "unknown")
        intents[intent] = intents.get(intent, 0) + 1
    return {
        "total": total,
        "verified": verified,
        "failed": failed,
        "api_calls": api_calls,
        "top_intents": sorted(intents.items(), key=lambda x: -x[1])[:5]
    }

if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1 and sys.argv[1] == "stats":
        stats = get_summary_stats()
        print(f"\n=== DECISION TRACE STATS ===")
        print(f"Total decisions: {stats['total']}")
        print(f"Verified OK: {stats['verified']}")
        print(f"Failed: {stats['failed']}")
        print(f"API calls: {stats['api_calls']}")
        print(f"Top intents: {stats['top_intents']}")
        print("============================\n")
    else:
        # Write a test entry then show it
        record(
            intent="test",
            plan="Verify decision trace works",
            reason="Session build test",
            action="write test entry",
            result="success",
            verified=True,
            source="local",
            duration_ms=12
        )
        print_recent(5)
