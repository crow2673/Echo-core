#!/usr/bin/env python3
"""Review-gated conversation learning candidates for Echo.

This module separates conversation preservation from training eligibility.
Interaction ledger and semantic memory may keep raw exchanges, but examples
created here remain pending until a reviewer explicitly approves them.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

BASE = Path(__file__).resolve().parents[1]
CANDIDATES_PATH = BASE / "memory/conversation_learning_candidates.jsonl"
EVENTS_PATH = BASE / "memory/conversation_learning_candidate_events.jsonl"
APPROVED_DATASET_PATH = BASE / "memory/finetune_dataset_reviewed.jsonl"

VALID_STATES = {"captured", "pending_review", "approved", "corrected", "rejected", "excluded"}
OPERATIONAL_CLAIM_PATTERNS = [
    re.compile(r"\btrading bots?\b.*\b(running|smooth|working|profitable|active)\b", re.I),
    re.compile(r"\b(running|smooth|working|active)\b.*\btrading bots?\b", re.I),
    re.compile(r"\bpublished\b.*\b(article|post)\b", re.I),
    re.compile(r"\bearned\b.*\b(money|income|\$)\b", re.I),
    re.compile(r"\bincome strateg(?:y|ies)\b", re.I),
    re.compile(r"\bsecurity updates?\b", re.I),
    re.compile(r"\bsystem health\b.*\b(running smoothly|healthy|ok)\b", re.I),
]
PRIVATE_PATTERNS = [
    re.compile(r"\b(password|token|api[_ -]?key|secret|credential)\b", re.I),
    re.compile(r"\b\d{3}[-.\s]?\d{3}[-.\s]?\d{4}\b"),
]


def utcnow() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _path_from_env(name: str, default: Path) -> Path:
    value = os.environ.get(name)
    return Path(value) if value else default


def _candidate_path() -> Path:
    return _path_from_env("ECHO_CONVERSATION_LEARNING_CANDIDATES", CANDIDATES_PATH)


def _events_path() -> Path:
    return _path_from_env("ECHO_CONVERSATION_LEARNING_EVENTS", EVENTS_PATH)


def _approved_dataset_path() -> Path:
    return _path_from_env("ECHO_CONVERSATION_LEARNING_APPROVED_DATASET", APPROVED_DATASET_PATH)


def _append_jsonl(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(payload, sort_keys=True) + "\n")


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    rows: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            rows.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return rows


def dedupe_fingerprint(
    *,
    source: str,
    andrew_message: str,
    echo_response: str,
    source_interaction_ids: list[int] | None = None,
) -> str:
    payload = {
        "source": source,
        "source_interaction_ids": source_interaction_ids or [],
        "andrew_message": andrew_message.strip(),
        "echo_response": echo_response.strip(),
    }
    return hashlib.sha256(json.dumps(payload, sort_keys=True).encode("utf-8")).hexdigest()


def _candidate_id(fingerprint: str) -> str:
    return f"conversation-learning-{fingerprint[:16]}"


def _claim_flags(text: str) -> list[str]:
    flags = []
    for pattern in OPERATIONAL_CLAIM_PATTERNS:
        if pattern.search(text or ""):
            flags.append(pattern.pattern)
    return flags


def _privacy_classification(*texts: str) -> str:
    joined = "\n".join(texts)
    if any(pattern.search(joined) for pattern in PRIVATE_PATTERNS):
        return "excluded_private"
    return "owner_private"


def _initial_status(echo_response: str, privacy: str) -> str:
    if privacy == "excluded_private":
        return "excluded"
    if _claim_flags(echo_response):
        return "pending_review"
    return "pending_review"


def _candidate_lesson(andrew_message: str, echo_response: str, flags: list[str]) -> str:
    if flags:
        return (
            "Review whether Echo's operational claims are evidence-backed before "
            "using this exchange for training."
        )
    if len(echo_response.strip()) < 40:
        return "Review whether this short exchange contains any durable training lesson."
    return "Review whether this exchange demonstrates useful conversational behavior."


def _review_category(flags: list[str], evidence_status: str) -> str:
    if flags or evidence_status in {"blocked", "failed"}:
        return "failure_or_misunderstanding"
    return "successful_behavior_worth_reinforcing"


def list_candidates(path: Path | None = None) -> list[dict[str, Any]]:
    rows = _read_jsonl(path or _candidate_path())
    current: dict[str, dict[str, Any]] = {}
    for row in rows:
        if row.get("record_type") == "candidate":
            current[row["candidate_id"]] = row
    return sorted(current.values(), key=lambda r: (r.get("created_at", ""), r.get("candidate_id", "")))


def get_candidate(candidate_id: str, path: Path | None = None) -> dict[str, Any] | None:
    for candidate in list_candidates(path):
        if candidate.get("candidate_id") == candidate_id:
            return candidate
    return None


def capture_candidate(
    *,
    andrew_message: str,
    echo_response: str,
    source: str,
    channel: str = "telegram",
    source_interaction_ids: list[int] | None = None,
    timestamps: dict[str, str] | None = None,
    model_used: str | None = None,
    immediate_context_refs: list[str] | None = None,
    retrieved_memory_refs: list[str] | None = None,
    evidence_status: str = "unverified",
    candidate_path: Path | None = None,
    events_path: Path | None = None,
) -> dict[str, Any]:
    fingerprint = dedupe_fingerprint(
        source=source,
        andrew_message=andrew_message,
        echo_response=echo_response,
        source_interaction_ids=source_interaction_ids,
    )
    existing = next((c for c in list_candidates(candidate_path) if c.get("deduplication_fingerprint") == fingerprint), None)
    if existing:
        return existing

    flags = _claim_flags(echo_response)
    privacy = _privacy_classification(andrew_message, echo_response)
    now = utcnow()
    candidate = {
        "record_type": "candidate",
        "candidate_id": _candidate_id(fingerprint),
        "status": _initial_status(echo_response, privacy),
        "source": source,
        "channel": channel,
        "source_interaction_ledger_ids": source_interaction_ids or [],
        "timestamps": timestamps or {},
        "andrew_message": andrew_message,
        "echo_response": echo_response,
        "model_used": model_used,
        "immediate_context_references": immediate_context_refs or [],
        "retrieved_memory_references": retrieved_memory_refs or [],
        "evidence_status": evidence_status,
        "operational_claim_flags": flags,
        "privacy_classification": privacy,
        "candidate_lesson": _candidate_lesson(andrew_message, echo_response, flags),
        "review_category": _review_category(flags, evidence_status),
        "reviewer": None,
        "review_reason": None,
        "created_at": now,
        "updated_at": now,
        "deduplication_fingerprint": fingerprint,
    }
    event = {
        "record_type": "event",
        "candidate_id": candidate["candidate_id"],
        "event": "captured",
        "actor": source,
        "reason": "conversation captured for review; not approved for training",
        "previous_status": None,
        "resulting_status": candidate["status"],
        "timestamp": now,
    }
    _append_jsonl(candidate_path or _candidate_path(), candidate)
    _append_jsonl(events_path or _events_path(), event)
    return candidate


def review_candidate(
    candidate_id: str,
    *,
    decision: str,
    reviewer: str,
    reason: str,
    corrected_andrew_message: str | None = None,
    corrected_echo_response: str | None = None,
    candidate_lesson: str | None = None,
    review_category: str | None = None,
    candidate_path: Path | None = None,
    events_path: Path | None = None,
) -> dict[str, Any]:
    if decision not in {"approved", "corrected", "rejected", "excluded"}:
        raise ValueError(f"unsupported review decision: {decision}")
    if not reviewer or not reason:
        raise ValueError("reviewer and reason are required")
    current = get_candidate(candidate_id, candidate_path)
    if not current:
        raise ValueError(f"candidate not found: {candidate_id}")
    if current.get("status") in {"rejected", "excluded"} and decision == "approved":
        raise ValueError("rejected or excluded candidates cannot be silently approved")

    now = utcnow()
    updated = dict(current)
    updated.update({
        "status": decision,
        "reviewer": reviewer,
        "review_reason": reason,
        "reviewed_at": now,
        "updated_at": now,
    })
    if corrected_andrew_message is not None:
        updated["corrected_andrew_message"] = corrected_andrew_message
    if corrected_echo_response is not None:
        updated["corrected_echo_response"] = corrected_echo_response
    if candidate_lesson is not None:
        updated["candidate_lesson"] = candidate_lesson
    if review_category is not None:
        updated["review_category"] = review_category

    event = {
        "record_type": "event",
        "candidate_id": candidate_id,
        "event": "review",
        "actor": reviewer,
        "reason": reason,
        "previous_status": current.get("status"),
        "resulting_status": decision,
        "timestamp": now,
    }
    _append_jsonl(candidate_path or _candidate_path(), updated)
    _append_jsonl(events_path or _events_path(), event)
    return updated


def approved_training_examples(candidate_path: Path | None = None) -> list[dict[str, Any]]:
    examples = []
    for candidate in list_candidates(candidate_path):
        if candidate.get("status") not in {"approved", "corrected"}:
            continue
        human = candidate.get("corrected_andrew_message") or candidate.get("andrew_message") or ""
        gpt = candidate.get("corrected_echo_response") or candidate.get("echo_response") or ""
        if not human.strip() or not gpt.strip():
            continue
        examples.append({
            "conversations": [
                {"from": "human", "value": human},
                {"from": "gpt", "value": gpt},
            ],
            "ts": candidate.get("reviewed_at") or candidate.get("updated_at"),
            "source": "reviewed_conversation_learning",
            "candidate_id": candidate["candidate_id"],
            "review_category": candidate.get("review_category"),
            "candidate_lesson": candidate.get("candidate_lesson"),
        })
    return examples


def export_approved_dataset(
    *,
    candidate_path: Path | None = None,
    output_path: Path | None = None,
) -> dict[str, Any]:
    examples = approved_training_examples(candidate_path)
    out = output_path or _approved_dataset_path()
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text("\n".join(json.dumps(ex, sort_keys=True) for ex in examples) + ("\n" if examples else ""), encoding="utf-8")
    return {"output": str(out), "approved_examples": len(examples)}


def _self_test() -> dict[str, Any]:
    import tempfile

    with tempfile.TemporaryDirectory() as tmp:
        candidate_path = Path(tmp) / "candidates.jsonl"
        events_path = Path(tmp) / "events.jsonl"
        c1 = capture_candidate(
            andrew_message="What is going on?",
            echo_response="Trading bots are running smoothly.",
            source="self_test",
            source_interaction_ids=[1, 2],
            candidate_path=candidate_path,
            events_path=events_path,
        )
        c2 = capture_candidate(
            andrew_message="What is going on?",
            echo_response="Trading bots are running smoothly.",
            source="self_test",
            source_interaction_ids=[1, 2],
            candidate_path=candidate_path,
            events_path=events_path,
        )
        review_candidate(
            c1["candidate_id"],
            decision="rejected",
            reviewer="fixture",
            reason="unsupported operational claim",
            candidate_path=candidate_path,
            events_path=events_path,
        )
        return {
            "ok": c1["candidate_id"] == c2["candidate_id"],
            "candidate_count": len(list_candidates(candidate_path)),
            "event_count": len(_read_jsonl(events_path)),
        }


def main() -> int:
    parser = argparse.ArgumentParser(description="Review-gated conversation learning candidates")
    parser.add_argument("--list", action="store_true")
    parser.add_argument("--show")
    parser.add_argument("--approve")
    parser.add_argument("--correct")
    parser.add_argument("--reject")
    parser.add_argument("--exclude")
    parser.add_argument("--reviewer")
    parser.add_argument("--reason")
    parser.add_argument("--corrected-andrew-message")
    parser.add_argument("--corrected-echo-response")
    parser.add_argument("--lesson")
    parser.add_argument("--review-category")
    parser.add_argument("--export-approved", action="store_true")
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()

    if args.self_test:
        print(json.dumps(_self_test(), indent=2))
        return 0
    if args.list:
        print(json.dumps(list_candidates(), indent=2))
        return 0
    if args.show:
        print(json.dumps(get_candidate(args.show), indent=2))
        return 0
    review_targets = [
        ("approved", args.approve),
        ("corrected", args.correct),
        ("rejected", args.reject),
        ("excluded", args.exclude),
    ]
    for decision, candidate_id in review_targets:
        if candidate_id:
            print(json.dumps(review_candidate(
                candidate_id,
                decision=decision,
                reviewer=args.reviewer or "",
                reason=args.reason or "",
                corrected_andrew_message=args.corrected_andrew_message,
                corrected_echo_response=args.corrected_echo_response,
                candidate_lesson=args.lesson,
                review_category=args.review_category,
            ), indent=2))
            return 0
    if args.export_approved:
        print(json.dumps(export_approved_dataset(), indent=2))
        return 0
    parser.print_help()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
