#!/usr/bin/env python3
"""core/reasoning_trace_collector.py — capture VERIFIED reasoning so it can train her.

The intelligence signal was evaporating: agent_loop builds a task trace (reasoning
+ tool calls + an independent verification) in memory, then throws it away. So the
fine-tune had nothing to learn reasoning from — only chat logs, which only shape
voice. This persists the GOOD traces (only those whose outcome an independent
verifier confirmed) into a durable corpus the fine-tune can learn from. Over time
this turns self-improvement from a voice-tuner into an intelligence-tuner.

Only VERIFIED-correct traces are saved — we never train her on reasoning that
produced a wrong/unverified result.

  save_verified_trace(task, trace, status, evidence=None, final_answer="") -> bool
"""
import json
from datetime import datetime, timezone
from pathlib import Path

BASE = Path(__file__).resolve().parents[1]
CORPUS = BASE / "memory/reasoning_traces.jsonl"

# statuses agent_loop uses for a genuinely verified completion
VERIFIED_STATUSES = {"verified", "completed_verified", "success_verified"}


def save_verified_trace(task: str, trace: list, status: str,
                        evidence: list = None, final_answer: str = "") -> bool:
    """Append a trace to the corpus ONLY if it ended in an independently verified
    success. Returns True if saved."""
    verified = (status in VERIFIED_STATUSES) or (
        isinstance(evidence, list) and evidence and
        isinstance(evidence[-1], dict) and evidence[-1].get("verified") is True
    )
    if not verified:
        return False
    rec = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "task": task,
        "status": status,
        # compact the steps to the trainable essence: which tool, on what, result-ok
        "steps": [
            {"tool": s.get("tool"), "args": s.get("args"),
             "ok": s.get("verified", s.get("ok"))}
            for s in (trace or [])
        ],
        "final_answer": final_answer,
        "verified": True,
    }
    with open(CORPUS, "a") as f:
        f.write(json.dumps(rec, default=str) + "\n")
    return True


def count() -> int:
    if not CORPUS.exists():
        return 0
    return sum(1 for ln in CORPUS.read_text().splitlines() if ln.strip())


if __name__ == "__main__":
    print(f"verified reasoning traces collected: {count()}  (file: {CORPUS})")
