#!/usr/bin/env python3
"""Central Executive Context for Echo.

This module owns small, safe updates to memory/executive_context.json. It
intentionally does not expose a whole-file overwrite helper; loops should update
specific fields or use the narrow helper functions below.
"""
from __future__ import annotations

import argparse
import copy
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

BASE = Path(__file__).resolve().parents[1]
CONTEXT_PATH = BASE / "memory" / "executive_context.json"

ALLOWED_UPDATE_KEYS = {
    "current_mission",
    "current_objective",
    "current_focus",
    "focus_reason",
    "reason_for_focus",
    "active_task",
    "active_blocker",
    "current_blocker",
    "system_health",
    "confidence",
    "energy",
    "risk_level",
    "resources",
    "human_availability",
    "pending_approval",
    "last_success",
    "last_failure",
    "time_since_progress",
    "capability_blockers",
    "maintenance_findings",
    "last_verified_success",
    "last_verified_failure",
    "objective_progress",
    "evidence_summary",
    "evidence_sources",
    "outcome_confidence",
    "last_outcome_checked_at",
    "outcome_evidence_signature",
    "allowed_autonomous_actions",
    "forbidden_actions",
    "notes",
}

SYSTEM_HEALTH_OWNERS = {
    "homeostasis",
    "core.homeostasis",
    "tools.homeostasis_check",
    "homeostasis.test",
}

SOURCE_ALLOWED_KEYS = {
    "outcome_loop": {
        "last_verified_success",
        "last_verified_failure",
        "objective_progress",
        "evidence_summary",
        "evidence_sources",
        "outcome_confidence",
        "last_outcome_checked_at",
        "outcome_evidence_signature",
    },
    "core.outcome_loop": {
        "last_verified_success",
        "last_verified_failure",
        "objective_progress",
        "evidence_summary",
        "evidence_sources",
        "outcome_confidence",
        "last_outcome_checked_at",
        "outcome_evidence_signature",
    },
    "outcome_loop.test": {
        "last_verified_success",
        "last_verified_failure",
        "objective_progress",
        "evidence_summary",
        "evidence_sources",
        "outcome_confidence",
        "last_outcome_checked_at",
        "outcome_evidence_signature",
    },
}


def utcnow() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def default_context() -> dict[str, Any]:
    now = utcnow()
    return {
        "schema_version": 1,
        "created_at": now,
        "updated_at": now,
        "current_mission": "Keep Echo useful, grounded, reliable, and aligned with Andrew's current priorities.",
        "current_objective": "Establish a single executive context before integrating more loops.",
        "current_focus": "Build Executive Context foundation",
        "focus_reason": "Echo has multiple active loops and needs one shared authority for current focus.",
        "reason_for_focus": "Echo has multiple active loops and needs one shared authority for current focus.",
        "active_task": None,
        "active_blocker": None,
        "current_blocker": None,
        "system_health": "unknown",
        "confidence": 0.5,
        "energy": "normal",
        "risk_level": "low",
        "resources": {
            "primary_state": "memory/executive_context.json",
            "repo": str(BASE),
        },
        "human_availability": "unknown",
        "pending_approval": None,
        "last_success": None,
        "last_failure": None,
        "time_since_progress": None,
        "capability_blockers": [],
        "maintenance_findings": [],
        "last_verified_success": None,
        "last_verified_failure": None,
        "objective_progress": "unknown",
        "evidence_summary": None,
        "evidence_sources": [],
        "outcome_confidence": 0.0,
        "last_outcome_checked_at": None,
        "outcome_evidence_signature": None,
        "allowed_autonomous_actions": [
            "read local state",
            "write reports",
            "run dry-run checks",
            "make low-risk local code changes when asked",
        ],
        "forbidden_actions": [
            "spend money",
            "bypass captcha or identity checks",
            "change credentials",
            "delete user data without explicit approval",
            "replace executive_context.json wholesale from a random loop",
        ],
        "history": [],
        "notes": [],
    }


def _deep_merge_defaults(data: dict[str, Any], defaults: dict[str, Any]) -> dict[str, Any]:
    merged = copy.deepcopy(defaults)
    for key, value in data.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key].update(value)
        else:
            merged[key] = value
    return merged


def _read_json(path: Path) -> dict[str, Any] | None:
    try:
        if path.exists():
            data = json.loads(path.read_text())
            if isinstance(data, dict):
                return data
    except Exception:
        return None
    return None


def _write_context(context: dict[str, Any]) -> None:
    CONTEXT_PATH.parent.mkdir(parents=True, exist_ok=True)
    tmp = CONTEXT_PATH.with_name(f"{CONTEXT_PATH.name}.{os.getpid()}.tmp")
    tmp.write_text(json.dumps(context, indent=2, sort_keys=True) + "\n")
    tmp.rename(CONTEXT_PATH)


def _append_history(context: dict[str, Any], event_type: str, summary: str, data: dict[str, Any] | None = None) -> None:
    event = {
        "ts": utcnow(),
        "type": event_type,
        "summary": summary[:500],
    }
    if data:
        event["data"] = data
    history = context.setdefault("history", [])
    history.append(event)
    context["history"] = history[-100:]


def load_context(create: bool = True) -> dict[str, Any]:
    """Load context safely and create defaults if missing.

    If the file is missing or unreadable, this returns defaults. Missing keys are
    filled on read. When create=True, defaults/repairs are persisted.
    """
    defaults = default_context()
    existing = _read_json(CONTEXT_PATH)
    if existing is None:
        context = defaults
        _append_history(context, "context_created", "Executive Context defaults created.")
        if create:
            _write_context(context)
        return context

    context = _deep_merge_defaults(existing, defaults)
    if context != existing and create:
        context["updated_at"] = utcnow()
        _append_history(context, "context_repaired", "Missing Executive Context defaults were restored.")
        _write_context(context)
    return context


def safe_update(updates: dict[str, Any], source: str = "unknown", reason: str = "") -> dict[str, Any]:
    """Safely update allowed top-level fields only.

    Unknown keys are ignored rather than written. This prevents arbitrary loops
    from replacing the schema or history with unrelated data.
    """
    if not isinstance(updates, dict):
        raise TypeError("updates must be a dict")

    context = load_context(create=True)
    applied: dict[str, Any] = {}
    ignored: list[str] = []
    for key, value in updates.items():
        allowed_for_source = SOURCE_ALLOWED_KEYS.get(source)
        if allowed_for_source is not None and key not in allowed_for_source:
            ignored.append(key)
            continue
        if key == "system_health" and source not in SYSTEM_HEALTH_OWNERS:
            ignored.append(key)
            continue
        if key in ALLOWED_UPDATE_KEYS:
            if context.get(key) != value:
                context[key] = value
                applied[key] = value
        else:
            ignored.append(key)

    if not applied:
        return context

    context["updated_at"] = utcnow()
    history_keys = set(applied)
    if not (source in SOURCE_ALLOWED_KEYS and history_keys == {"last_outcome_checked_at"}):
        _append_history(
            context,
            "safe_update",
            reason or f"Safe update from {source}.",
            {"source": source, "applied_keys": sorted(applied), "ignored_keys": sorted(ignored)},
        )
    _write_context(context)
    return context


def get_current_focus() -> dict[str, Any]:
    context = load_context(create=True)
    return {
        "current_mission": context.get("current_mission"),
        "current_objective": context.get("current_objective"),
        "current_focus": context.get("current_focus"),
        "focus_reason": context.get("focus_reason"),
        "reason_for_focus": context.get("reason_for_focus"),
        "active_task": context.get("active_task"),
        "active_blocker": context.get("active_blocker"),
        "current_blocker": context.get("current_blocker"),
        "system_health": context.get("system_health"),
        "risk_level": context.get("risk_level"),
        "capability_blockers": context.get("capability_blockers", []),
        "maintenance_findings": context.get("maintenance_findings", []),
        "last_verified_success": context.get("last_verified_success"),
        "last_verified_failure": context.get("last_verified_failure"),
        "objective_progress": context.get("objective_progress"),
        "evidence_summary": context.get("evidence_summary"),
        "evidence_sources": context.get("evidence_sources", []),
        "outcome_confidence": context.get("outcome_confidence"),
        "last_outcome_checked_at": context.get("last_outcome_checked_at"),
        "confidence": context.get("confidence"),
    }


def set_active_task(task: str, source: str = "unknown", reason: str = "") -> dict[str, Any]:
    task = str(task).strip()
    if not task:
        raise ValueError("task must not be empty")
    return safe_update(
        {
            "active_task": {
                "task": task,
                "source": source,
                "started_at": utcnow(),
                "status": "active",
            },
            "current_focus": task,
            "focus_reason": reason or f"Active task set by {source}.",
            "current_blocker": None,
            "active_blocker": None,
        },
        source=source,
        reason=reason or "Set active task.",
    )


def record_blocker(blocker: str, source: str = "unknown", severity: str = "medium") -> dict[str, Any]:
    blocker = str(blocker).strip()
    if not blocker:
        raise ValueError("blocker must not be empty")
    return safe_update(
        {
            "current_blocker": {
                "blocker": blocker,
                "source": source,
                "severity": severity,
                "recorded_at": utcnow(),
            },
            "active_blocker": {
                "blocker": blocker,
                "source": source,
                "severity": severity,
                "recorded_at": utcnow(),
            },
            "risk_level": "high" if severity == "critical" else "medium",
        },
        source=source,
        reason="Record current blocker.",
    )


def record_success(summary: str, source: str = "unknown", evidence: str = "") -> dict[str, Any]:
    summary = str(summary).strip()
    if not summary:
        raise ValueError("summary must not be empty")
    context = safe_update(
        {
            "last_success": {
                "summary": summary,
                "source": source,
                "evidence": evidence[:1000],
                "recorded_at": utcnow(),
            },
            "current_blocker": None,
            "active_blocker": None,
            "time_since_progress": "0s",
            "risk_level": "low",
        },
        source=source,
        reason="Record success.",
    )
    active = context.get("active_task")
    if isinstance(active, dict):
        active["status"] = "succeeded"
        active["completed_at"] = utcnow()
        context["active_task"] = active
        context["updated_at"] = utcnow()
        _append_history(context, "active_task_succeeded", summary, {"source": source})
        _write_context(context)
    return context


def record_failure(summary: str, source: str = "unknown", evidence: str = "", blocker: str = "") -> dict[str, Any]:
    summary = str(summary).strip()
    if not summary:
        raise ValueError("summary must not be empty")
    updates: dict[str, Any] = {
        "last_failure": {
            "summary": summary,
            "source": source,
            "evidence": evidence[:1000],
            "recorded_at": utcnow(),
        },
        "risk_level": "medium",
    }
    if blocker:
        updates["current_blocker"] = {
            "blocker": blocker[:500],
            "source": source,
            "severity": "medium",
            "recorded_at": utcnow(),
        }
        updates["active_blocker"] = updates["current_blocker"]
    return safe_update(updates, source=source, reason="Record failure.")


def _run_self_test() -> dict[str, Any]:
    before = load_context(create=True)
    set_active_task("Executive Context CLI self-test", source="executive_context.self_test")
    record_blocker("Temporary test blocker", source="executive_context.self_test", severity="low")
    record_success(
        "Executive Context load/update/read self-test passed.",
        source="executive_context.self_test",
        evidence="load_context, set_active_task, record_blocker, record_success, get_current_focus",
    )
    focus = get_current_focus()
    return {
        "path": str(CONTEXT_PATH),
        "created_before_test": bool(before),
        "current_focus": focus,
        "ok": focus.get("last_error") is None and focus.get("current_focus") == "Executive Context CLI self-test",
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Echo Executive Context helper")
    parser.add_argument("--print", action="store_true", help="Print the full context.")
    parser.add_argument("--focus", action="store_true", help="Print current focus only.")
    parser.add_argument("--set-active-task", metavar="TASK", help="Set the active task.")
    parser.add_argument("--record-blocker", metavar="BLOCKER", help="Record a blocker.")
    parser.add_argument("--record-success", metavar="SUMMARY", help="Record a success.")
    parser.add_argument("--record-failure", metavar="SUMMARY", help="Record a failure.")
    parser.add_argument("--source", default="executive_context.cli")
    parser.add_argument("--self-test", action="store_true", help="Run a small load/update/read test.")
    args = parser.parse_args()

    result: Any
    if args.self_test:
        result = _run_self_test()
    elif args.set_active_task:
        result = set_active_task(args.set_active_task, source=args.source)
    elif args.record_blocker:
        result = record_blocker(args.record_blocker, source=args.source)
    elif args.record_success:
        result = record_success(args.record_success, source=args.source)
    elif args.record_failure:
        result = record_failure(args.record_failure, source=args.source)
    elif args.focus:
        result = get_current_focus()
    else:
        result = load_context(create=True)

    if args.print or args.focus or args.self_test:
        print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
