#!/usr/bin/env python3
"""Durable callback jobs for Echo's tmux collaboration relay.

The conductor still uses tmux as the transport. This module adds the missing
contract around that transport: a job, a correlation id, append-only state
events, and validated replies.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import secrets
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any


BASE = Path(__file__).resolve().parents[1]
DEFAULT_JOBS = BASE / "memory/collab_relay_jobs.jsonl"
DEFAULT_EVENTS = BASE / "memory/collab_relay_events.jsonl"
DEFAULT_CHANNEL = BASE / "collab/channel.jsonl"

JOB_RE = re.compile(r"^relay-job-[a-f0-9]{16}$")
CORRELATION_RE = re.compile(r"^corr-[a-f0-9]{16}$")
HANDLE_RE = re.compile(r"^[a-z][a-z0-9_-]{0,31}$")

FINAL_STATES = {
    "replied",
    "blocked_interactive",
    "unavailable",
    "timed_out",
    "failed",
    "duplicate_reply",
    "wrong_correlation",
}


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _now_iso() -> str:
    return _now().isoformat()


def jobs_path() -> Path:
    return Path(os.environ.get("ECHO_RELAY_JOBS_PATH", DEFAULT_JOBS))


def events_path() -> Path:
    return Path(os.environ.get("ECHO_RELAY_EVENTS_PATH", DEFAULT_EVENTS))


def channel_path() -> Path:
    return Path(os.environ.get("ECHO_COLLAB_CHANNEL_PATH", DEFAULT_CHANNEL))


def validate_job_id(job_id: str) -> None:
    if not JOB_RE.match(job_id or ""):
        raise ValueError("invalid job_id")


def validate_correlation_id(correlation_id: str) -> None:
    if not CORRELATION_RE.match(correlation_id or ""):
        raise ValueError("invalid correlation_id")


def validate_handle(handle: str) -> None:
    if not HANDLE_RE.match(handle or ""):
        raise ValueError("invalid agent handle")


def _append_jsonl(path: Path, record: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "a", encoding="utf-8") as fh:
        fh.write(json.dumps(record, sort_keys=True) + "\n")


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    out: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            out.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return out


def _new_token(prefix: str) -> str:
    return f"{prefix}-{secrets.token_hex(8)}"


def _fingerprint(*parts: str) -> str:
    h = hashlib.sha256()
    for part in parts:
        h.update((part or "").encode("utf-8", errors="replace"))
        h.update(b"\0")
    return h.hexdigest()


def create_job(
    *,
    recipient: str,
    original_question: str,
    sender: str = "andrew",
    channel: str = "telegram",
    timeout_seconds: int = 150,
    parent_request_id: str | None = None,
) -> dict[str, Any]:
    validate_handle(recipient)
    validate_handle(sender)
    job_id = _new_token("relay-job")
    correlation_id = _new_token("corr")
    validate_job_id(job_id)
    validate_correlation_id(correlation_id)
    created = _now()
    reply_deadline = created + timedelta(seconds=max(1, int(timeout_seconds)))
    safe_reply_file = f"/tmp/echo_reply_{job_id}.txt"
    job = {
        "record_type": "relay_job",
        "job_id": job_id,
        "correlation_id": correlation_id,
        "sender": sender,
        "recipient": recipient,
        "channel": channel,
        "original_question": original_question,
        "created_at": created.isoformat(),
        "reply_deadline": reply_deadline.isoformat(),
        "reply_file": safe_reply_file,
        "reply_command": (
            f'python3 -m collab.bus reply --job-id "{job_id}" '
            f'--correlation-id "{correlation_id}" --from-agent "{recipient}" '
            f'--message-file "{safe_reply_file}"'
        ),
        "parent_request_id": parent_request_id,
        "dedupe_fingerprint": _fingerprint(recipient, sender, channel, original_question, created.isoformat()),
    }
    _append_jsonl(jobs_path(), job)
    record_event(job_id, "created", actor=sender, details={"recipient": recipient})
    return get_job(job_id) or job


def record_event(
    job_id: str,
    state: str,
    *,
    actor: str,
    reason: str | None = None,
    details: dict[str, Any] | None = None,
) -> dict[str, Any]:
    validate_job_id(job_id)
    if actor:
        validate_handle(actor)
    event = {
        "record_type": "relay_job_event",
        "job_id": job_id,
        "state": state,
        "actor": actor,
        "reason": reason,
        "details": details or {},
        "ts": _now_iso(),
    }
    _append_jsonl(events_path(), event)
    return event


def list_events(job_id: str | None = None) -> list[dict[str, Any]]:
    events = _read_jsonl(events_path())
    if job_id:
        validate_job_id(job_id)
        events = [event for event in events if event.get("job_id") == job_id]
    return events


def get_job(job_id: str) -> dict[str, Any] | None:
    validate_job_id(job_id)
    jobs = [job for job in _read_jsonl(jobs_path()) if job.get("job_id") == job_id]
    if not jobs:
        return None
    job = dict(jobs[-1])
    events = list_events(job_id)
    job["events"] = events
    job["state"] = events[-1]["state"] if events else "created"
    return job


def require_job(job_id: str) -> dict[str, Any]:
    job = get_job(job_id)
    if not job:
        raise ValueError("unknown job")
    return job


def mark_ready(job_id: str, *, actor: str = "echo", details: dict[str, Any] | None = None) -> dict[str, Any]:
    require_job(job_id)
    return record_event(job_id, "recipient_ready", actor=actor, details=details)


def mark_delivered(job_id: str, *, actor: str = "echo", details: dict[str, Any] | None = None) -> dict[str, Any]:
    require_job(job_id)
    return record_event(job_id, "delivered", actor=actor, details=details)


def mark_blocked(job_id: str, state: str, *, reason: str, actor: str = "echo", details: dict[str, Any] | None = None) -> dict[str, Any]:
    if state not in {"blocked_interactive", "unavailable", "timed_out", "failed"}:
        raise ValueError("invalid blocked state")
    require_job(job_id)
    return record_event(job_id, state, actor=actor, reason=reason, details=details)


def claim_job(job_id: str, correlation_id: str, from_agent: str) -> dict[str, Any]:
    validate_correlation_id(correlation_id)
    validate_handle(from_agent)
    job = require_job(job_id)
    if job["correlation_id"] != correlation_id:
        record_event(job_id, "wrong_correlation", actor=from_agent, reason="claim correlation mismatch")
        raise ValueError("wrong correlation_id")
    if job["recipient"] != from_agent:
        record_event(job_id, "failed", actor=from_agent, reason="claim recipient mismatch")
        raise ValueError("wrong recipient")
    return record_event(job_id, "claimed", actor=from_agent)


def progress_job(job_id: str, correlation_id: str, from_agent: str, message: str) -> dict[str, Any]:
    validate_correlation_id(correlation_id)
    validate_handle(from_agent)
    job = require_job(job_id)
    if job["correlation_id"] != correlation_id:
        record_event(job_id, "wrong_correlation", actor=from_agent, reason="progress correlation mismatch")
        raise ValueError("wrong correlation_id")
    if job["recipient"] != from_agent:
        record_event(job_id, "failed", actor=from_agent, reason="progress recipient mismatch")
        raise ValueError("wrong recipient")
    return record_event(job_id, "progress", actor=from_agent, details={"message": message[:1000]})


def fail_job(job_id: str, correlation_id: str, from_agent: str, message: str) -> dict[str, Any]:
    validate_correlation_id(correlation_id)
    validate_handle(from_agent)
    job = require_job(job_id)
    if job["correlation_id"] != correlation_id:
        record_event(job_id, "wrong_correlation", actor=from_agent, reason="fail correlation mismatch")
        raise ValueError("wrong correlation_id")
    if job["recipient"] != from_agent:
        record_event(job_id, "failed", actor=from_agent, reason="fail recipient mismatch")
        raise ValueError("wrong recipient")
    if not (message or "").strip():
        raise ValueError("failure message is required")
    record_event(job_id, "failed", actor=from_agent, details={"message": message[:4000]})
    return {"job": get_job(job_id), "message": message}


def reply_job(job_id: str, correlation_id: str, from_agent: str, message: str) -> dict[str, Any]:
    validate_correlation_id(correlation_id)
    validate_handle(from_agent)
    job = require_job(job_id)
    if job["correlation_id"] != correlation_id:
        record_event(job_id, "wrong_correlation", actor=from_agent, reason="reply correlation mismatch")
        raise ValueError("wrong correlation_id")
    if job["recipient"] != from_agent:
        record_event(job_id, "failed", actor=from_agent, reason="reply recipient mismatch")
        raise ValueError("wrong recipient")
    text = (message or "").strip()
    if not text:
        raise ValueError("reply message is empty")
    if any(event.get("state") == "replied" for event in job.get("events", [])):
        record_event(job_id, "duplicate_reply", actor=from_agent, reason="reply already recorded")
        raise ValueError("duplicate reply")
    event = record_event(
        job_id,
        "replied",
        actor=from_agent,
        details={"message_sha256": hashlib.sha256(text.encode("utf-8")).hexdigest()},
    )
    return {"job": get_job(job_id), "event": event, "message": text}


def read_bus() -> list[dict[str, Any]]:
    return _read_jsonl(channel_path())


def latest_bus_id() -> int:
    messages = read_bus()
    return int(messages[-1].get("id", 0)) if messages else 0


def wait_for_correlated_result(job_id: str, timeout_seconds: int, poll_seconds: float = 1.0) -> dict[str, Any]:
    job = require_job(job_id)
    deadline = time.monotonic() + max(0.0, float(timeout_seconds))
    correlation_id = job["correlation_id"]
    recipient = job["recipient"]
    last_status = job.get("state", "created")
    scanned_once = False
    while not scanned_once or time.monotonic() <= deadline:
        scanned_once = True
        for msg in read_bus():
            if msg.get("job_id") != job_id or msg.get("correlation_id") != correlation_id:
                continue
            if msg.get("from") != recipient:
                continue
            msg_type = msg.get("type")
            if msg_type == "relay_reply":
                return {"status": "replied", "message": msg.get("text", ""), "bus_message": msg, "job": get_job(job_id)}
            if msg_type == "relay_fail":
                return {"status": "failed", "message": msg.get("text", ""), "bus_message": msg, "job": get_job(job_id)}
            if msg_type == "relay_claim":
                last_status = "claimed"
        current = get_job(job_id)
        if current:
            state = current.get("state", last_status)
            if state in {"failed", "blocked_interactive", "unavailable"}:
                return {"status": state, "message": "", "bus_message": None, "job": current}
            last_status = state
        if time.monotonic() > deadline:
            break
        time.sleep(max(0.05, float(poll_seconds)))
    final = get_job(job_id)
    state = final.get("state", last_status) if final else last_status
    timeout_reasons = {
        "created": "not delivered",
        "recipient_ready": "recipient ready but not delivered",
        "delivered": "delivered but not claimed",
        "claimed": "claimed and still running",
        "progress": "claimed and reported progress",
    }
    reason = timeout_reasons.get(state, f"timed out with agent state {state}")
    record_event(job_id, "timed_out", actor="echo", reason=reason, details={"last_observed_state": state})
    return {"status": "timed_out", "message": "", "bus_message": None, "job": get_job(job_id), "last_observed_state": state}
