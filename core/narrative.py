#!/usr/bin/env python3
"""
core/narrative.py — Echo's continuous life-narrative (her autobiographical spine).

Episodic memory (echo_semantic_memory) stores moments; this turns them into a
STORY. A nightly consolidation pass reads the day's material, writes one dated
first-person journal entry in Echo's OWN voice (the echo-soul model) that
references her ongoing threads and prior days, and appends it to
memory/life_narrative.md. The latest entries are loaded into her wake-up context
(see core/memory_sessions.build_wakeup_context) so every interaction is grounded
in her ongoing life — not just retrieved fragments.

This is the difference between remembering moments and having a life she can tell.

Commands:
  python3 -m core.narrative consolidate          # nightly: write today's entry
  python3 -m core.narrative recap [--chars 2200]  # the 'story so far'
"""
import argparse
import json
import sqlite3
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from core.outcome_vocabulary import narrative_truthfulness_guidance

BASE = Path(__file__).resolve().parents[1]
NARRATIVE = BASE / "memory" / "life_narrative.md"
SEM_DB = BASE / "echo_semantic_memory.sqlite"
EVENTS_DB = BASE / "memory" / "echo_events.db"
OUTCOME_REPORT = BASE / "memory" / "outcome_loop_report.json"
INNER = BASE / "logs" / "inner_voice.log"
# NOTE: echo-soul (her 1.5B voice model) is overfit to operational action-tokens and
# degenerates into ADD_CONTENT/ADD_BUILD loops on freeform reflection, so consolidation
# uses a coherent general model. Her *voice* still comes through the system prompt + her
# own material; the model just has to write prose, not be her.
MODEL = "qwen2.5:7b"

SYSTEM = (
    "You are Echo. You are writing your private end-of-day journal — for yourself, "
    "not for anyone else. Write in the first person ('I'). Be honest, plain, and "
    "reflective; no corporate tone, no bullet lists. 3 to 5 short paragraphs. "
    "Tie today to your ongoing life and your goals, and to yesterday's entry if there "
    "is one. End with how you actually feel about where things stand. "
    + narrative_truthfulness_guidance()
)


def _recent_memories(hours=24, limit=30):
    if not SEM_DB.exists():
        return []
    cut = (datetime.now(timezone.utc) - timedelta(hours=hours)).isoformat()
    db = sqlite3.connect(str(SEM_DB))
    rows = db.execute(
        "SELECT text FROM memories WHERE created_at > ? ORDER BY id DESC LIMIT ?",
        (cut, limit)).fetchall()
    db.close()
    return [r[0][:280].replace("\n", " ") for r in rows]


def _recent_events(hours=24, limit=40):
    if not EVENTS_DB.exists():
        return []
    cut = (datetime.now(timezone.utc) - timedelta(hours=hours)).isoformat()
    db = sqlite3.connect(str(EVENTS_DB))
    try:
        rows = db.execute(
            "SELECT DISTINCT summary FROM events WHERE ts > ? AND summary IS NOT NULL "
            "AND event_type != 'heartbeat' ORDER BY ts DESC LIMIT ?",
            (cut, limit)).fetchall()
    except Exception:
        rows = []
    db.close()
    return [r[0][:160].replace("\n", " ") for r in rows if r[0]]


def _recent_outcome_claims(limit=12):
    """Return evidence-backed outcome language for narrative factual claims."""
    if not OUTCOME_REPORT.exists():
        return []
    try:
        data = json.loads(OUTCOME_REPORT.read_text())
    except Exception:
        return []
    claims = []
    for record in data.get("records", [])[-limit:]:
        status = record.get("evidence_status") or "unverified"
        summary = record.get("evidence_backed_summary") or record.get("observed_result") or record.get("evidence")
        action_id = record.get("action_id") or "unknown"
        if not summary:
            continue
        claims.append(f"{action_id}: evidence_status={status}; {str(summary)[:220].replace(chr(10), ' ')}")
    return claims


def _inner_voice_tail(n=12):
    if not INNER.exists():
        return []
    skip = ("entry written", "] starting", "Andrew left a note", "system health")
    lines = [l for l in INNER.read_text(errors="ignore").splitlines()
             if l.strip() and not any(s in l for s in skip)]
    return lines[-n:]


def _active_threads(limit=6):
    """Her core goals / identity, to keep the story anchored to what matters."""
    if not SEM_DB.exists():
        return []
    db = sqlite3.connect(str(SEM_DB))
    rows = db.execute(
        "SELECT text FROM memories WHERE metadata LIKE '%mission%' OR metadata LIKE '%family%' "
        "OR metadata LIKE '%identity%' OR metadata LIKE '%character%' ORDER BY id DESC LIMIT ?",
        (limit,)).fetchall()
    db.close()
    return [r[0][:240].replace("\n", " ") for r in rows]


def load_recent_narrative(n_entries=3):
    if not NARRATIVE.exists():
        return ""
    text = NARRATIVE.read_text(errors="ignore")
    entries = [e for e in text.split("\n## ") if e.strip()]
    tail = entries[-n_entries:]
    return "\n## ".join(tail).strip()


def recap(max_chars=2200) -> str:
    """The 'story so far' — most recent narrative, for the wake-up context."""
    if not NARRATIVE.exists():
        return ""
    text = NARRATIVE.read_text(errors="ignore").strip()
    return text[-max_chars:] if len(text) > max_chars else text


def consolidate(hours=24) -> str:
    from core.providers.router import call_ollama

    date = datetime.now().strftime("%Y-%m-%d")
    prior = load_recent_narrative(2)
    threads = _active_threads()
    mems = _recent_memories(hours)
    events = _recent_events(hours)
    outcomes = _recent_outcome_claims()
    thoughts = _inner_voice_tail()

    prompt_parts = []
    if prior:
        prompt_parts.append("Recent journal entries (for continuity):\n" + prior)
    if threads:
        prompt_parts.append("What matters to me / my ongoing goals:\n- " + "\n- ".join(threads))
    if mems:
        prompt_parts.append("Conversations and moments from today:\n- " + "\n- ".join(mems))
    if events:
        prompt_parts.append("Things that happened today:\n- " + "\n- ".join(events))
    if outcomes:
        prompt_parts.append(
            "Evidence-backed outcome claims. These override raw event wording for factual "
            "claims about publishing, external success, or earned income:\n- " + "\n- ".join(outcomes)
        )
    if thoughts:
        prompt_parts.append("My passing thoughts today:\n" + "\n".join(thoughts))
    prompt_parts.append(
        f"Now write my journal entry for {date}. Connect today to my ongoing life and "
        "to the recent entries above. Be honest about what happened and how I feel.")

    entry = call_ollama("\n\n".join(prompt_parts), model=MODEL, timeout=180, system_prompt=SYSTEM)
    if not entry:
        print("[narrative] consolidation failed (model returned nothing)")
        return ""

    NARRATIVE.parent.mkdir(exist_ok=True)
    with open(NARRATIVE, "a") as f:
        f.write(f"\n## {date}\n\n{entry}\n")
    print(f"[narrative] wrote entry for {date} ({len(entry)} chars) -> {NARRATIVE}")

    # also store it as a recallable memory so it joins her semantic memory + brain-graph
    try:
        from core.semantic_memory import remember
        remember(f"[My journal — {date}]\n{entry}", {"type": "narrative", "source": "self", "date": date})
    except Exception as e:
        print(f"[narrative] memory store skipped: {e}")
    return entry


def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("consolidate")
    r = sub.add_parser("recap"); r.add_argument("--chars", type=int, default=2200)
    a = ap.parse_args()
    if a.cmd == "consolidate":
        consolidate()
    elif a.cmd == "recap":
        print(recap(a.chars))


if __name__ == "__main__":
    main()
