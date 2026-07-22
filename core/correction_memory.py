#!/usr/bin/env python3
"""Durable lessons derived from Andrew's explicit corrections."""
import json
import re
from datetime import datetime, timezone
from pathlib import Path

BASE = Path(__file__).resolve().parents[1]
LESSONS_FILE = BASE / "memory/correction_lessons.json"


def _load() -> dict:
    if LESSONS_FILE.exists():
        try:
            return json.loads(LESSONS_FILE.read_text())
        except Exception:
            pass
    return {"lessons": []}


def _save(data: dict):
    tmp = LESSONS_FILE.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, indent=2))
    tmp.rename(LESSONS_FILE)


def _topic(text: str) -> str:
    words = re.findall(r"[a-z0-9]+", text.lower())
    stop = {"that", "this", "what", "with", "from", "your", "you", "echo", "wrong", "not"}
    return " ".join(word for word in words if len(word) > 3 and word not in stop)[:120]


def record_correction(correction: str, prior_reply: str = "") -> dict:
    correction = str(correction or "").strip()
    if not correction:
        return {}
    data = _load()
    signature = correction.lower()[:200]
    for lesson in data["lessons"]:
        if lesson.get("signature") == signature:
            lesson["times_reinforced"] = lesson.get("times_reinforced", 1) + 1
            lesson["last_reinforced"] = datetime.now(timezone.utc).isoformat()
            _save(data)
            return lesson
    lesson = {
        "id": f"correction_{len(data['lessons']) + 1}",
        "signature": signature,
        "topic": _topic(correction + " " + prior_reply),
        "rule": correction[:500],
        "corrected_reply": prior_reply[:800],
        "created_at": datetime.now(timezone.utc).isoformat(),
        "times_reinforced": 1,
        "active": True,
    }
    data["lessons"].append(lesson)
    data["lessons"] = data["lessons"][-200:]
    _save(data)
    return lesson


def relevant(query: str, limit: int = 5) -> list[dict]:
    query_words = set(_topic(query).split())
    ranked = []
    data = _load()
    for lesson in data["lessons"]:
        if not lesson.get("active", True):
            continue
        overlap = len(query_words & set(lesson.get("topic", "").split()))
        if overlap or not query_words:
            ranked.append((overlap, lesson.get("times_reinforced", 1), lesson))
    ranked.sort(key=lambda item: (item[0], item[1]), reverse=True)
    selected = [item[2] for item in ranked[:limit]]
    if selected:
        now = datetime.now(timezone.utc).isoformat()
        for lesson in selected:
            lesson["retrieval_count"] = lesson.get("retrieval_count", 0) + 1
            lesson["last_retrieved"] = now
        _save(data)
    return selected


def context_block(query: str, limit: int = 5) -> str:
    lessons = relevant(query, limit)
    if not lessons:
        return ""
    return "ACTIVE LESSONS FROM ANDREW'S CORRECTIONS:\n" + "\n".join(
        f"- {lesson['rule']}" for lesson in lessons
    )


def backfill_from_interaction_ledger() -> int:
    ledger = BASE / "memory/interaction_ledger.jsonl"
    if not ledger.exists():
        return 0
    turns = []
    for line in ledger.read_text().splitlines():
        try:
            turns.append(json.loads(line))
        except Exception:
            pass
    added = 0
    prior_reply = ""
    for turn in turns:
        if turn.get("role") == "echo":
            prior_reply = turn.get("text", "")
        elif turn.get("role") == "andrew" and turn.get("kind") == "correction":
            before = len(_load()["lessons"])
            record_correction(turn.get("text", ""), prior_reply)
            if len(_load()["lessons"]) > before:
                added += 1
    return added
