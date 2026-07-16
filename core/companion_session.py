#!/usr/bin/env python3
"""Manual companion sessions for bounded work-period continuity.

This is not a watcher. It records explicit user/session events so Echo can
park and resume a work period without inferring progress from silence.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

BASE = Path(__file__).resolve().parents[1]
DEFAULT_DB_PATH = BASE / "memory" / "companion_sessions.sqlite"
STATUSES = {"active", "parked", "completed", "abandoned"}


class CompanionSessionError(RuntimeError):
    pass


def utcnow() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _json(value: Any) -> str:
    return json.dumps(value if value is not None else [], sort_keys=True)


def _load_json(value: str | None, default: Any) -> Any:
    if not value:
        return default
    try:
        return json.loads(value)
    except Exception:
        return default


def _session_id(title: str, created_at: str) -> str:
    digest = hashlib.sha256(f"{title}|{created_at}|{os.getpid()}".encode("utf-8")).hexdigest()[:12]
    return f"session-{digest}"


def connect(db_path: str | Path | None = None) -> sqlite3.Connection:
    path = Path(db_path or DEFAULT_DB_PATH)
    path.parent.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(str(path))
    db.row_factory = sqlite3.Row
    ensure_schema(db)
    return db


def ensure_schema(db: sqlite3.Connection) -> None:
    db.execute(
        """
        CREATE TABLE IF NOT EXISTS companion_sessions (
            session_id TEXT PRIMARY KEY,
            title TEXT NOT NULL,
            purpose TEXT NOT NULL,
            related_executive_focus TEXT,
            related_asset_ids TEXT,
            related_task_ids TEXT,
            started_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            ended_at TEXT,
            status TEXT NOT NULL,
            current_step TEXT,
            completed_steps TEXT,
            blockers TEXT,
            decisions TEXT,
            observation_references TEXT,
            structured_fact_references TEXT,
            next_action TEXT,
            interruption_reason TEXT,
            resume_cue TEXT,
            outcome TEXT,
            provenance TEXT,
            privacy_scope TEXT NOT NULL
        )
        """
    )
    db.execute(
        """
        CREATE TABLE IF NOT EXISTS companion_session_events (
            event_id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id TEXT NOT NULL,
            operation TEXT NOT NULL,
            actor TEXT NOT NULL,
            reason TEXT,
            timestamp TEXT NOT NULL,
            previous_state TEXT,
            resulting_state TEXT NOT NULL
        )
        """
    )
    db.execute("CREATE INDEX IF NOT EXISTS idx_companion_sessions_status ON companion_sessions(status)")
    db.commit()


def _row_to_session(row: sqlite3.Row | None) -> dict[str, Any] | None:
    if row is None:
        return None
    session = dict(row)
    for key in (
        "related_asset_ids",
        "related_task_ids",
        "completed_steps",
        "blockers",
        "decisions",
        "observation_references",
        "structured_fact_references",
    ):
        session[key] = _load_json(session.get(key), [])
    session["provenance"] = _load_json(session.get("provenance"), {})
    return session


def _state(session: dict[str, Any] | None) -> str | None:
    if session is None:
        return None
    return json.dumps(session, sort_keys=True)


def _get(db: sqlite3.Connection, session_id: str) -> dict[str, Any] | None:
    return _row_to_session(db.execute("SELECT * FROM companion_sessions WHERE session_id=?", (session_id,)).fetchone())


def _write_event(
    db: sqlite3.Connection,
    session_id: str,
    operation: str,
    actor: str,
    reason: str,
    previous: dict[str, Any] | None,
    resulting: dict[str, Any],
    timestamp: str,
) -> None:
    db.execute(
        """
        INSERT INTO companion_session_events
        (session_id, operation, actor, reason, timestamp, previous_state, resulting_state)
        VALUES (?,?,?,?,?,?,?)
        """,
        (session_id, operation, actor, reason, timestamp, _state(previous), _state(resulting)),
    )


def _insert(db: sqlite3.Connection, session: dict[str, Any]) -> None:
    db.execute(
        """
        INSERT INTO companion_sessions (
            session_id, title, purpose, related_executive_focus, related_asset_ids,
            related_task_ids, started_at, updated_at, ended_at, status, current_step,
            completed_steps, blockers, decisions, observation_references,
            structured_fact_references, next_action, interruption_reason, resume_cue,
            outcome, provenance, privacy_scope
        ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
        """,
        _to_db_tuple(session),
    )


def _update(db: sqlite3.Connection, session: dict[str, Any]) -> None:
    db.execute(
        """
        UPDATE companion_sessions SET
            title=?, purpose=?, related_executive_focus=?, related_asset_ids=?,
            related_task_ids=?, updated_at=?, ended_at=?, status=?, current_step=?,
            completed_steps=?, blockers=?, decisions=?, observation_references=?,
            structured_fact_references=?, next_action=?, interruption_reason=?,
            resume_cue=?, outcome=?, provenance=?, privacy_scope=?
        WHERE session_id=?
        """,
        (
            session["title"],
            session["purpose"],
            session.get("related_executive_focus"),
            _json(session.get("related_asset_ids", [])),
            _json(session.get("related_task_ids", [])),
            session["updated_at"],
            session.get("ended_at"),
            session["status"],
            session.get("current_step"),
            _json(session.get("completed_steps", [])),
            _json(session.get("blockers", [])),
            _json(session.get("decisions", [])),
            _json(session.get("observation_references", [])),
            _json(session.get("structured_fact_references", [])),
            session.get("next_action"),
            session.get("interruption_reason"),
            session.get("resume_cue"),
            session.get("outcome"),
            _json(session.get("provenance", {})),
            session["privacy_scope"],
            session["session_id"],
        ),
    )


def _to_db_tuple(session: dict[str, Any]) -> tuple:
    return (
        session["session_id"],
        session["title"],
        session["purpose"],
        session.get("related_executive_focus"),
        _json(session.get("related_asset_ids", [])),
        _json(session.get("related_task_ids", [])),
        session["started_at"],
        session["updated_at"],
        session.get("ended_at"),
        session["status"],
        session.get("current_step"),
        _json(session.get("completed_steps", [])),
        _json(session.get("blockers", [])),
        _json(session.get("decisions", [])),
        _json(session.get("observation_references", [])),
        _json(session.get("structured_fact_references", [])),
        session.get("next_action"),
        session.get("interruption_reason"),
        session.get("resume_cue"),
        session.get("outcome"),
        _json(session.get("provenance", {})),
        session["privacy_scope"],
    )


def _active_or_parked(db: sqlite3.Connection) -> dict[str, Any] | None:
    row = db.execute(
        "SELECT * FROM companion_sessions WHERE status IN ('active','parked') ORDER BY updated_at DESC LIMIT 1"
    ).fetchone()
    return _row_to_session(row)


def _active(db: sqlite3.Connection) -> dict[str, Any] | None:
    row = db.execute("SELECT * FROM companion_sessions WHERE status='active' ORDER BY updated_at DESC LIMIT 1").fetchone()
    return _row_to_session(row)


def _exec_focus() -> str | None:
    try:
        from core.executive_context import load_context

        context = load_context(create=False)
        return context.get("current_focus")
    except Exception:
        return None


def start_session(
    *,
    title: str,
    purpose: str,
    current_step: str = "",
    next_action: str = "",
    related_asset_ids: list[str] | None = None,
    related_task_ids: list[str] | None = None,
    privacy_scope: str = "owner_private",
    actor: str = "Andrew",
    provenance: dict[str, Any] | None = None,
    db_path: str | Path | None = None,
) -> dict[str, Any]:
    ts = utcnow()
    with connect(db_path) as db:
        if _active(db):
            raise CompanionSessionError("active companion session already exists")
        session = {
            "session_id": _session_id(title, ts),
            "title": title,
            "purpose": purpose,
            "related_executive_focus": _exec_focus(),
            "related_asset_ids": related_asset_ids or [],
            "related_task_ids": related_task_ids or [],
            "started_at": ts,
            "updated_at": ts,
            "ended_at": None,
            "status": "active",
            "current_step": current_step,
            "completed_steps": [],
            "blockers": [],
            "decisions": [],
            "observation_references": [],
            "structured_fact_references": [],
            "next_action": next_action,
            "interruption_reason": None,
            "resume_cue": None,
            "outcome": None,
            "provenance": provenance or {"source": "manual_companion_session"},
            "privacy_scope": privacy_scope,
        }
        _insert(db, session)
        _write_event(db, session["session_id"], "start_session", actor, "manual start", None, session, ts)
        db.commit()
        return session


def _mutate(session_id: str, operation: str, actor: str, reason: str, mutator, db_path=None) -> dict[str, Any]:
    ts = utcnow()
    with connect(db_path) as db:
        session = _get(db, session_id)
        if not session:
            raise CompanionSessionError(f"session not found: {session_id}")
        previous = dict(session)
        mutator(session, ts)
        session["updated_at"] = ts
        _update(db, session)
        _write_event(db, session_id, operation, actor, reason, previous, session, ts)
        db.commit()
        return session


def record_update(session_id: str, *, current_step: str = "", completed_step: str = "", next_action: str = "", actor="Andrew", db_path=None) -> dict[str, Any]:
    def apply(session, _ts):
        if session["status"] not in {"active", "parked"}:
            raise CompanionSessionError("cannot update completed or abandoned session")
        if current_step:
            session["current_step"] = current_step
        if completed_step:
            session.setdefault("completed_steps", []).append(completed_step)
        if next_action:
            session["next_action"] = next_action

    return _mutate(session_id, "record_update", actor, current_step or completed_step or next_action, apply, db_path)


def record_observation_reference(session_id: str, *, observation_id: str, source: str = "observation_manager", notes: str = "", actor="Andrew", db_path=None) -> dict[str, Any]:
    def apply(session, _ts):
        refs = session.setdefault("observation_references", [])
        ref = {"observation_id": observation_id, "source": source, "notes": notes}
        if ref not in refs:
            refs.append(ref)

    return _mutate(session_id, "record_observation_reference", actor, observation_id, apply, db_path)


def record_structured_fact_reference(session_id: str, *, fact_id: str, actor="Andrew", db_path=None) -> dict[str, Any]:
    try:
        from core.structured_facts import connect as fact_connect

        with fact_connect() as fact_db:
            row = fact_db.execute("SELECT * FROM structured_facts WHERE fact_id=? AND status='current'", (fact_id,)).fetchone()
            fact = dict(row) if row else None
            if fact:
                fact["source_memory_ids"] = _load_json(fact.get("source_memory_ids"), [])
    except Exception:
        fact = None
    if not fact:
        raise CompanionSessionError("only current reviewed structured facts may be referenced")

    def apply(session, _ts):
        refs = session.setdefault("structured_fact_references", [])
        ref = {
            "fact_id": fact_id,
            "status": fact.get("status"),
            "privacy_scope": fact.get("privacy_scope"),
            "source_reference": fact.get("source_reference"),
        }
        if ref not in refs:
            refs.append(ref)

    return _mutate(session_id, "record_structured_fact_reference", actor, fact_id, apply, db_path)


def record_decision(session_id: str, *, decision: str, reason: str = "", actor="Andrew", db_path=None) -> dict[str, Any]:
    def apply(session, ts):
        session.setdefault("decisions", []).append({"decision": decision, "reason": reason, "ts": ts, "actor": actor})

    return _mutate(session_id, "record_decision", actor, reason or decision, apply, db_path)


def record_blocker(session_id: str, *, blocker: str, next_action: str = "", actor="Andrew", db_path=None) -> dict[str, Any]:
    def apply(session, ts):
        session.setdefault("blockers", []).append({"blocker": blocker, "ts": ts, "actor": actor})
        if next_action:
            session["next_action"] = next_action

    return _mutate(session_id, "record_blocker", actor, blocker, apply, db_path)


def park_session(session_id: str, *, reason: str, resume_cue: str, next_action: str, actor="Andrew", db_path=None) -> dict[str, Any]:
    def apply(session, _ts):
        if session["status"] not in {"active", "parked"}:
            raise CompanionSessionError("only active or parked sessions can be parked")
        session["status"] = "parked"
        session["interruption_reason"] = reason
        session["resume_cue"] = resume_cue
        session["next_action"] = next_action

    return _mutate(session_id, "park_session", actor, reason, apply, db_path)


def resume_session(session_id: str, *, actor="Andrew", db_path=None) -> dict[str, Any]:
    def apply(session, _ts):
        if session["status"] != "parked":
            raise CompanionSessionError("only parked sessions can be resumed")
        session["status"] = "active"

    session = _mutate(session_id, "resume_session", actor, "manual resume", apply, db_path)
    session["resume_brief"] = summarize_session(session_id, db_path=db_path)["resume_brief"]
    return session


def complete_session(session_id: str, *, outcome: str, actor="Andrew", db_path=None) -> dict[str, Any]:
    def apply(session, ts):
        if session["status"] not in {"active", "parked"}:
            raise CompanionSessionError("only active or parked sessions can be completed")
        session["status"] = "completed"
        session["outcome"] = outcome
        session["ended_at"] = ts

    return _mutate(session_id, "complete_session", actor, outcome, apply, db_path)


def abandon_session(session_id: str, *, reason: str, actor="Andrew", db_path=None) -> dict[str, Any]:
    def apply(session, ts):
        if session["status"] == "completed":
            raise CompanionSessionError("completed sessions cannot be abandoned")
        session["status"] = "abandoned"
        session["outcome"] = reason
        session["ended_at"] = ts

    return _mutate(session_id, "abandon_session", actor, reason, apply, db_path)


def get_active_session(*, db_path=None) -> dict[str, Any] | None:
    with connect(db_path) as db:
        return _active(db)


def get_session(session_id: str, *, db_path=None) -> dict[str, Any] | None:
    with connect(db_path) as db:
        return _get(db, session_id)


def list_events(session_id: str, *, db_path=None) -> list[dict[str, Any]]:
    with connect(db_path) as db:
        rows = db.execute(
            "SELECT * FROM companion_session_events WHERE session_id=? ORDER BY event_id ASC",
            (session_id,),
        ).fetchall()
    out = []
    for row in rows:
        event = dict(row)
        event["previous_state"] = _load_json(event.get("previous_state"), None)
        event["resulting_state"] = _load_json(event.get("resulting_state"), {})
        out.append(event)
    return out


def summarize_session(session_id: str, *, db_path=None) -> dict[str, Any]:
    session = get_session(session_id, db_path=db_path)
    if not session:
        raise CompanionSessionError(f"session not found: {session_id}")
    last_completed = session.get("completed_steps", [])[-1] if session.get("completed_steps") else None
    blocker = session.get("blockers", [])[-1]["blocker"] if session.get("blockers") else None
    brief = {
        "session_id": session["session_id"],
        "title": session["title"],
        "purpose": session["purpose"],
        "status": session["status"],
        "last_known_state": session.get("current_step"),
        "last_completed_action": last_completed,
        "unresolved_blocker": blocker,
        "next_action": session.get("next_action"),
        "resume_cue": session.get("resume_cue"),
        "important_evidence": {
            "observation_references": session.get("observation_references", []),
            "structured_fact_references": session.get("structured_fact_references", []),
            "decisions": session.get("decisions", [])[-3:],
        },
        "privacy_scope": session.get("privacy_scope"),
    }
    return {"session": session, "resume_brief": brief}


def _print(payload: Any) -> None:
    print(json.dumps(payload, indent=2, sort_keys=True, default=str))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--db", default=str(DEFAULT_DB_PATH))
    sub = parser.add_subparsers(dest="cmd", required=True)

    start = sub.add_parser("start")
    start.add_argument("--title", required=True)
    start.add_argument("--purpose", required=True)
    start.add_argument("--current-step", default="")
    start.add_argument("--next-action", default="")
    start.add_argument("--asset-id", action="append", default=[])
    start.add_argument("--task-id", action="append", default=[])
    start.add_argument("--privacy-scope", default="owner_private")

    update = sub.add_parser("update")
    update.add_argument("--session-id", required=True)
    update.add_argument("--current-step", default="")
    update.add_argument("--completed-step", default="")
    update.add_argument("--next-action", default="")

    obs = sub.add_parser("observation")
    obs.add_argument("--session-id", required=True)
    obs.add_argument("--observation-id", required=True)
    obs.add_argument("--source", default="observation_manager")
    obs.add_argument("--notes", default="")

    fact = sub.add_parser("fact")
    fact.add_argument("--session-id", required=True)
    fact.add_argument("--fact-id", required=True)

    decision = sub.add_parser("decision")
    decision.add_argument("--session-id", required=True)
    decision.add_argument("--decision", required=True)
    decision.add_argument("--reason", default="")

    blocker = sub.add_parser("blocker")
    blocker.add_argument("--session-id", required=True)
    blocker.add_argument("--blocker", required=True)
    blocker.add_argument("--next-action", default="")

    park = sub.add_parser("park")
    park.add_argument("--session-id", required=True)
    park.add_argument("--reason", required=True)
    park.add_argument("--resume-cue", required=True)
    park.add_argument("--next-action", required=True)

    resume = sub.add_parser("resume")
    resume.add_argument("--session-id", required=True)

    complete = sub.add_parser("complete")
    complete.add_argument("--session-id", required=True)
    complete.add_argument("--outcome", required=True)

    abandon = sub.add_parser("abandon")
    abandon.add_argument("--session-id", required=True)
    abandon.add_argument("--reason", required=True)

    show = sub.add_parser("show")
    show.add_argument("--session-id", required=True)

    sub.add_parser("active")

    args = parser.parse_args()
    db_path = args.db
    if args.cmd == "start":
        _print(start_session(title=args.title, purpose=args.purpose, current_step=args.current_step, next_action=args.next_action, related_asset_ids=args.asset_id, related_task_ids=args.task_id, privacy_scope=args.privacy_scope, db_path=db_path))
    elif args.cmd == "update":
        _print(record_update(args.session_id, current_step=args.current_step, completed_step=args.completed_step, next_action=args.next_action, db_path=db_path))
    elif args.cmd == "observation":
        _print(record_observation_reference(args.session_id, observation_id=args.observation_id, source=args.source, notes=args.notes, db_path=db_path))
    elif args.cmd == "fact":
        _print(record_structured_fact_reference(args.session_id, fact_id=args.fact_id, db_path=db_path))
    elif args.cmd == "decision":
        _print(record_decision(args.session_id, decision=args.decision, reason=args.reason, db_path=db_path))
    elif args.cmd == "blocker":
        _print(record_blocker(args.session_id, blocker=args.blocker, next_action=args.next_action, db_path=db_path))
    elif args.cmd == "park":
        _print(park_session(args.session_id, reason=args.reason, resume_cue=args.resume_cue, next_action=args.next_action, db_path=db_path))
    elif args.cmd == "resume":
        _print(resume_session(args.session_id, db_path=db_path))
    elif args.cmd == "complete":
        _print(complete_session(args.session_id, outcome=args.outcome, db_path=db_path))
    elif args.cmd == "abandon":
        _print(abandon_session(args.session_id, reason=args.reason, db_path=db_path))
    elif args.cmd == "show":
        _print(summarize_session(args.session_id, db_path=db_path))
    elif args.cmd == "active":
        _print(get_active_session(db_path=db_path) or {})
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
