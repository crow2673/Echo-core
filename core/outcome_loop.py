#!/usr/bin/env python3
"""General outcome loop for Echo actions.

Records expected outcomes, evaluates them against observable local evidence,
and writes a compact report that other Echo loops can use.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path

from core.outcome_vocabulary import (
    classify_outcome_evidence,
    evidence_status_counts,
    render_outcome_claim,
)

BASE = Path(__file__).resolve().parents[1]
DB_PATH = BASE / "memory" / "echo_events.db"
REPORT_JSON = BASE / "memory" / "outcome_loop_report.json"
REPORT_MD = BASE / "memory" / "outcome_loop_report.md"
LOG_PATH = BASE / "logs" / "outcome_loop.log"
RECENT_EVIDENCE_SECONDS = 48 * 60 * 60

OUTCOME_STATES = {
    "verified_success",
    "verified_failure",
    "in_progress",
    "blocked",
    "pending_review",
    "stale",
    "unrelated",
    "unverified",
}


def utcnow() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def parse_time(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None


def log(message: str) -> None:
    LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    line = f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] {message}"
    with LOG_PATH.open("a") as handle:
        handle.write(line + "\n")
    print(message, flush=True)


def load_json(path: Path, default):
    try:
        if path.exists():
            return json.loads(path.read_text())
    except Exception:
        pass
    return default


def write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f"{path.name}.{_pid()}.tmp")
    tmp.write_text(json.dumps(payload, indent=2, sort_keys=True))
    tmp.rename(path)


def _pid() -> int:
    import os

    return os.getpid()


def _conn():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(str(DB_PATH), timeout=10)
    db.execute(
        """
        CREATE TABLE IF NOT EXISTS outcome_expectations (
            id TEXT PRIMARY KEY,
            action_id TEXT UNIQUE,
            category TEXT,
            description TEXT,
            expected_result TEXT,
            verifier_type TEXT,
            verifier_config TEXT,
            status TEXT DEFAULT 'pending',
            score REAL DEFAULT 0,
            evidence TEXT,
            created_at TEXT,
            last_checked_at TEXT,
            resolved_at TEXT
        )
        """
    )
    db.commit()
    return db


def record_expected_outcome(
    action_id: str,
    category: str,
    description: str,
    expected_result: str,
    verifier_type: str,
    verifier_config: dict | None = None,
) -> str:
    verifier_config = verifier_config or {}
    entry_id = str(uuid.uuid4())[:10]
    db = _conn()
    existing = db.execute(
        "SELECT id FROM outcome_expectations WHERE action_id=?",
        (action_id,),
    ).fetchone()
    if existing:
        db.execute(
            """
            UPDATE outcome_expectations
            SET category=?, description=?, expected_result=?, verifier_type=?, verifier_config=?
            WHERE action_id=?
            """,
            (
                category,
                description[:500],
                expected_result[:500],
                verifier_type,
                json.dumps(verifier_config, sort_keys=True),
                action_id,
            ),
        )
        db.commit()
        db.close()
        return str(existing[0])
    db.execute(
        """
        INSERT INTO outcome_expectations
        (id, action_id, category, description, expected_result, verifier_type,
         verifier_config, status, score, created_at)
        VALUES (?,?,?,?,?,?,?,?,?,?)
        """,
        (
            entry_id,
            action_id,
            category,
            description[:500],
            expected_result[:500],
            verifier_type,
            json.dumps(verifier_config, sort_keys=True),
            "pending",
            0.0,
            utcnow(),
        ),
    )
    db.commit()
    db.close()
    return entry_id


def seed_current_expectations() -> list[str]:
    """Register current high-value outcomes if they are not already tracked."""
    seeds = [
        {
            "action_id": "reliability:homeostasis_ok",
            "category": "reliability",
            "description": "System health should have no critical homeostasis findings or human-gated blockers.",
            "expected_result": "memory/homeostasis_report.json has no critical findings and no needs_andrew items.",
            "verifier_type": "homeostasis_ok",
            "verifier_config": {},
        },
        {
            "action_id": "reliability:operational_audit_ok",
            "category": "reliability",
            "description": "Operational audit should have no critical warnings.",
            "expected_result": "memory/operational_audit.json assessment.status is ok.",
            "verifier_type": "operational_audit_ok",
            "verifier_config": {},
        },
        {
            "action_id": "reliability:log_anomaly_signal_tuned",
            "category": "tool_reliability",
            "description": "Anomaly floods should be separated from actionable health warnings.",
            "expected_result": "memory/log_anomaly_signal_report.json keeps actionable_count below the warning threshold.",
            "verifier_type": "json_path_max",
            "verifier_config": {
                "path": "memory/log_anomaly_signal_report.json",
                "json_path": "actionable_count",
                "max": 50,
            },
        },
        {
            "action_id": "self_improvement:growth_requests_closed",
            "category": "self_improvement",
            "description": "Reviewed build queue should not contain stale open requests after verified repair.",
            "expected_result": "memory/growth_build_requests.json has 0 open reviewed build requests.",
            "verifier_type": "open_build_requests_max",
            "verifier_config": {"max": 0},
        },
        {
            "action_id": "income:fiverr_prework_package",
            "category": "economic_agency",
            "description": "Fiverr income prework should produce a local service package without account activity.",
            "expected_result": "Latest Fiverr prework report has at least 5 services, lead evidence, and no browser/login/message activity.",
            "verifier_type": "fiverr_prework",
            "verifier_config": {
                "path": "memory/income_reports/fiverr_income_prework_latest.json",
                "min_services": 5,
                "min_leads": 100,
            },
        },
    ]
    ids = []
    for seed in seeds:
        ids.append(record_expected_outcome(**seed))
    return ids


def _json_path(data, dotted: str):
    cur = data
    for part in dotted.split("."):
        if isinstance(cur, dict):
            cur = cur.get(part)
        else:
            return None
    return cur


def _verify_file_exists(config: dict) -> tuple[str, float, str]:
    path = BASE / str(config.get("path", ""))
    min_size = int(config.get("min_size", 1) or 1)
    if path.exists() and path.stat().st_size >= min_size:
        return "succeeded", 1.0, f"{path.relative_to(BASE)} exists ({path.stat().st_size} bytes)"
    return "failed", -1.0, f"{path.relative_to(BASE)} missing or too small"


def _verify_json_path_max(config: dict) -> tuple[str, float, str]:
    path = BASE / str(config.get("path", ""))
    data = load_json(path, None)
    value = _json_path(data, str(config.get("json_path", ""))) if data is not None else None
    maximum = float(config.get("max", 0))
    if isinstance(value, (int, float)) and float(value) <= maximum:
        return "succeeded", 1.0, f"{path.relative_to(BASE)} {config.get('json_path')}={value} <= {maximum:g}"
    return "failed", -1.0, f"{path.relative_to(BASE)} {config.get('json_path')}={value} > {maximum:g}"


def _verify_homeostasis_ok(config: dict) -> tuple[str, float, str]:
    data = load_json(BASE / "memory/homeostasis_report.json", {})
    status = data.get("status")
    findings = data.get("findings", [])
    needs = data.get("needs_andrew", [])
    critical = [item for item in findings if item.get("severity") == "critical"]
    if not critical and not needs:
        return "succeeded", 1.0, f"homeostasis status={status}; critical=0; needs_andrew=0; warnings={len(findings)}"
    return "failed", -1.0, f"homeostasis status={status}; critical={len(critical)}; needs_andrew={len(needs)}"


def _verify_operational_audit_ok(config: dict) -> tuple[str, float, str]:
    data = load_json(BASE / "memory/operational_audit.json", {})
    assessment = data.get("assessment", {})
    status = assessment.get("status")
    critical = assessment.get("critical", [])
    warnings = assessment.get("warnings", [])
    if status == "ok" and not critical and not warnings:
        return "succeeded", 1.0, "operational audit ok; critical=0; warnings=0"
    return "failed", -1.0, f"operational audit status={status}; critical={len(critical)}; warnings={len(warnings)}"


def _verify_open_build_requests_max(config: dict) -> tuple[str, float, str]:
    data = load_json(BASE / "memory/growth_build_requests.json", {"requests": []})
    open_statuses = {"requested", "pending_build", "generation_failed"}
    open_items = [r for r in data.get("requests", []) if r.get("status") in open_statuses]
    maximum = int(config.get("max", 0) or 0)
    if len(open_items) <= maximum:
        return "succeeded", 1.0, f"open reviewed build requests={len(open_items)} <= {maximum}"
    return "failed", -1.0, f"open reviewed build requests={len(open_items)} > {maximum}"


def _verify_fiverr_prework(config: dict) -> tuple[str, float, str]:
    path = BASE / str(config.get("path", ""))
    data = load_json(path, {})
    min_services = int(config.get("min_services", 1) or 1)
    min_leads = int(config.get("min_leads", 1) or 1)
    services = data.get("service_count", len(data.get("services", [])))
    leads = int(data.get("lead_count", 0) or 0)
    safety = data.get("safety", {})
    unsafe = [
        key for key in ("browser_login", "messages_sent", "credentials_used")
        if safety.get(key)
    ]
    if services >= min_services and leads >= min_leads and not unsafe:
        return "succeeded", 1.0, f"fiverr prework services={services}; leads={leads}; no account activity"
    return "failed", -1.0, f"fiverr prework services={services}; leads={leads}; unsafe={unsafe}"


VERIFIERS = {
    "file_exists": _verify_file_exists,
    "json_path_max": _verify_json_path_max,
    "homeostasis_ok": _verify_homeostasis_ok,
    "operational_audit_ok": _verify_operational_audit_ok,
    "open_build_requests_max": _verify_open_build_requests_max,
    "fiverr_prework": _verify_fiverr_prework,
}


def evaluate_record(record: dict) -> tuple[str, float, str]:
    verifier = VERIFIERS.get(record.get("verifier_type"))
    if not verifier:
        return "unknown", 0.0, f"unsupported verifier: {record.get('verifier_type')}"
    config = {}
    try:
        config = json.loads(record.get("verifier_config") or "{}")
    except Exception:
        return "unknown", 0.0, "invalid verifier_config"
    try:
        return verifier(config)
    except Exception as exc:
        return "unknown", 0.0, f"verifier failed: {exc}"


def evaluate_pending(include_resolved: bool = True) -> list[dict]:
    db = _conn()
    clause = "" if include_resolved else "WHERE status IN ('pending','unknown','failed')"
    rows = db.execute(
        f"""
        SELECT id, action_id, category, description, expected_result,
               verifier_type, verifier_config, status, score, evidence,
               created_at, last_checked_at, resolved_at
        FROM outcome_expectations
        {clause}
        ORDER BY created_at ASC
        """
    ).fetchall()
    out = []
    for row in rows:
        record = {
            "id": row[0],
            "action_id": row[1],
            "category": row[2],
            "description": row[3],
            "expected_result": row[4],
            "verifier_type": row[5],
            "verifier_config": row[6],
            "status": row[7],
            "score": row[8],
            "evidence": row[9],
            "created_at": row[10],
            "last_checked_at": row[11],
            "resolved_at": row[12],
        }
        status, score, evidence = evaluate_record(record)
        resolved_at = record.get("resolved_at")
        if status == "succeeded" and not resolved_at:
            resolved_at = utcnow()
        if status != "succeeded":
            resolved_at = None
        db.execute(
            """
            UPDATE outcome_expectations
            SET status=?, score=?, evidence=?, last_checked_at=?, resolved_at=?
            WHERE id=?
            """,
            (status, score, evidence[:1000], utcnow(), resolved_at, record["id"]),
        )
        record.update({
            "status": status,
            "score": score,
            "evidence": evidence,
            "last_checked_at": utcnow(),
            "resolved_at": resolved_at,
        })
        out.append(record)
    db.commit()
    db.close()
    return out


def _text(value) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    try:
        return json.dumps(value, sort_keys=True)
    except Exception:
        return str(value)


def _active_task_text(executive_context: dict | None) -> str:
    task = (executive_context or {}).get("active_task")
    if isinstance(task, dict):
        return " ".join(_text(task.get(key)) for key in ("task", "status", "source"))
    return _text(task)


def _keywords(value: str) -> set[str]:
    stop = {
        "the", "and", "or", "for", "with", "has", "have", "should", "after",
        "before", "current", "context", "echo", "task", "work", "build",
        "ready", "done", "result", "expected", "memory",
    }
    words = set()
    cur = []
    for char in value.lower():
        if char.isalnum() or char in {"_", "-"}:
            cur.append(char)
        else:
            if cur:
                word = "".join(cur)
                if len(word) >= 4 and word not in stop:
                    words.add(word)
                cur = []
    if cur:
        word = "".join(cur)
        if len(word) >= 4 and word not in stop:
            words.add(word)
    return words


def _record_text(record: dict) -> str:
    return " ".join(
        _text(record.get(key))
        for key in (
            "action_id",
            "category",
            "description",
            "expected_result",
            "evidence",
            "verifier_type",
        )
    )


def _context_text(executive_context: dict | None) -> str:
    executive_context = executive_context or {}
    return " ".join(
        [
            _text(executive_context.get("current_objective")),
            _text(executive_context.get("current_focus")),
            _active_task_text(executive_context),
            _text(executive_context.get("outcome_expectations")),
        ]
    )


def _relevance(record: dict, executive_context: dict | None) -> tuple[str, float, str]:
    context_text = _context_text(executive_context)
    if not context_text.strip():
        return "relevant", 0.5, "no executive context available; treating tracked outcome as generally relevant"

    record_words = _keywords(_record_text(record))
    context_words = _keywords(context_text)
    overlap = sorted(record_words & context_words)
    if not context_words:
        return "relevant", 0.5, "executive context has no comparable keywords"

    score = len(overlap) / max(len(context_words), 1)
    if overlap and score >= 0.12:
        return "relevant", round(min(1.0, score), 3), f"matches executive context terms: {', '.join(overlap[:6])}"
    return "unrelated", round(score, 3), "does not match current objective, active task, or current focus"


def _evidence_age(record: dict, now: datetime | None = None) -> tuple[int | None, bool]:
    now = now or datetime.now(timezone.utc)
    checked = parse_time(record.get("last_checked_at"))
    if not checked:
        return None, False
    if checked.tzinfo is None:
        checked = checked.replace(tzinfo=timezone.utc)
    age = max(0, int((now - checked).total_seconds()))
    return age, age > RECENT_EVIDENCE_SECONDS


def classify_record_semantics(
    record: dict,
    executive_context: dict | None = None,
    now: datetime | None = None,
) -> dict:
    """Add objective-aware outcome semantics without changing raw verifier status."""
    raw_status = record.get("status") or "unknown"
    evidence = _text(record.get("evidence")).strip()
    relevance_status, relevance_score, relevance_reason = _relevance(record, executive_context)
    age_seconds, is_stale = _evidence_age(record, now=now)

    observed_result = evidence or "no evidence observed"
    verification_reason = ""
    outcome_state = "unverified"

    if not evidence or raw_status in {"unknown", "pending"}:
        outcome_state = "unverified"
        verification_reason = "missing or incomplete evidence"
    elif record.get("verifier_type") == "open_build_requests_max" and raw_status == "failed":
        outcome_state = "pending_review"
        verification_reason = "open build requests indicate unfinished work, not a failed attempted action"
    elif is_stale:
        outcome_state = "stale"
        verification_reason = f"evidence is older than {RECENT_EVIDENCE_SECONDS} seconds"
    elif relevance_status == "unrelated":
        outcome_state = "unrelated"
        verification_reason = relevance_reason
    elif raw_status == "succeeded":
        outcome_state = "verified_success"
        verification_reason = "relevant verifier succeeded with current evidence"
    elif raw_status == "failed":
        outcome_state = "verified_failure"
        verification_reason = "relevant expected result was checked and failed"

    evidence_claim = classify_outcome_evidence({
        **record,
        "source": "outcome_loop",
        "source_log": str(REPORT_JSON.relative_to(BASE)),
        "confidence": abs(float(record.get("score") or 0.7)) if record.get("score") is not None else 0.7,
    })

    return {
        **record,
        "outcome_state": outcome_state,
        "evidence_status": evidence_claim["evidence_status"],
        "evidence_types": evidence_claim["evidence_types"],
        "evidence_reference": evidence_claim["evidence_reference"],
        "evidence_classification_reason": evidence_claim["classification_reason"],
        "evidence_backed_summary": render_outcome_claim(evidence_claim),
        "produced_by_echo": evidence_claim["produced_by_echo"],
        "related_objective": (executive_context or {}).get("current_objective"),
        "related_task": (executive_context or {}).get("active_task"),
        "relevance_status": relevance_status,
        "relevance_score": relevance_score,
        "expected_result": record.get("expected_result"),
        "observed_result": observed_result,
        "verification_reason": verification_reason,
        "evidence_age": age_seconds,
    }


def build_report(
    records: list[dict],
    executive_context: dict | None = None,
    now: datetime | None = None,
) -> dict:
    total = len(records)
    succeeded = sum(1 for r in records if r.get("status") == "succeeded")
    failed = sum(1 for r in records if r.get("status") == "failed")
    unknown = sum(1 for r in records if r.get("status") == "unknown")
    pending = sum(1 for r in records if r.get("status") == "pending")
    scored = succeeded + failed
    success_rate = round(succeeded / scored, 3) if scored else None
    categories = {}
    for record in records:
        cat = record.get("category") or "unknown"
        item = categories.setdefault(cat, {"total": 0, "succeeded": 0, "failed": 0, "unknown": 0, "pending": 0})
        item["total"] += 1
        item[record.get("status", "unknown")] = item.get(record.get("status", "unknown"), 0) + 1
    semantic_records = [
        classify_record_semantics(
            {
                "action_id": r.get("action_id"),
                "category": r.get("category"),
                "description": r.get("description"),
                "verifier_type": r.get("verifier_type"),
                "status": r.get("status"),
                "score": r.get("score"),
                "expected_result": r.get("expected_result"),
                "evidence": r.get("evidence"),
                "last_checked_at": r.get("last_checked_at"),
            },
            executive_context=executive_context,
            now=now,
        )
        for r in records[-50:]
    ]
    return {
        "updated_at": utcnow(),
        "summary": {
            "total": total,
            "succeeded": succeeded,
            "failed": failed,
            "unknown": unknown,
            "pending": pending,
            "scored": scored,
            "success_rate": success_rate,
            "evidence_status_counts": evidence_status_counts(semantic_records),
        },
        "categories": categories,
        "records": semantic_records,
    }


def load_executive_context_snapshot() -> dict:
    try:
        from core.executive_context import load_context

        context = load_context(create=True)
        return {
            "current_objective": context.get("current_objective"),
            "active_task": context.get("active_task"),
            "current_focus": context.get("current_focus"),
            "outcome_expectations": context.get("outcome_expectations"),
        }
    except Exception as exc:
        return {"error": str(exc)}


def _record_brief(record: dict | None) -> dict | None:
    if not record:
        return None
    return {
        "action_id": record.get("action_id"),
        "category": record.get("category"),
        "outcome_state": record.get("outcome_state"),
        "evidence_status": record.get("evidence_status"),
        "relevance_status": record.get("relevance_status"),
        "relevance_score": record.get("relevance_score"),
        "expected_result": record.get("expected_result"),
        "observed_result": record.get("observed_result") or record.get("evidence") or "unverified",
        "evidence": record.get("evidence") or "unverified",
        "verification_reason": record.get("verification_reason"),
        "evidence_age": record.get("evidence_age"),
        "checked_at": record.get("last_checked_at"),
    }


def build_executive_evidence(report: dict, executive_context: dict | None = None) -> dict:
    records = report.get("records", [])
    relevant = [record for record in records if record.get("relevance_status") == "relevant"]
    relevant_recent = [
        record for record in relevant
        if record.get("outcome_state") not in {"stale", "unrelated"}
    ]
    successes = [record for record in relevant_recent if record.get("outcome_state") == "verified_success"]
    failures = [record for record in relevant_recent if record.get("outcome_state") == "verified_failure"]
    unresolved = [
        record for record in relevant_recent
        if record.get("outcome_state") in {"in_progress", "blocked", "pending_review", "unverified"}
    ]
    state_counts = {state: 0 for state in OUTCOME_STATES}
    for record in records:
        state = record.get("outcome_state") or "unverified"
        state_counts[state] = state_counts.get(state, 0) + 1
    summary = report.get("summary", {})

    if failures:
        progress = "blocked_or_regressed"
    elif successes and not unresolved:
        progress = "verified_progress"
    elif successes:
        progress = "partial_verified_progress"
    elif any(record.get("outcome_state") == "blocked" for record in unresolved):
        progress = "blocked"
    elif any(record.get("outcome_state") in {"in_progress", "pending_review"} for record in unresolved):
        progress = "in_progress"
    else:
        progress = "unverified"

    relevant_scored = len(successes) + len(failures)
    if relevant_scored:
        confidence = len(successes) / relevant_scored
    elif unresolved:
        confidence = 0.25
    else:
        confidence = 0.0

    evidence_sources = [str(REPORT_JSON.relative_to(BASE)), str(REPORT_MD.relative_to(BASE))]
    if executive_context:
        for key in ("current_objective", "active_task", "current_focus", "outcome_expectations"):
            if executive_context.get(key):
                evidence_sources.append(f"executive_context.{key}")

    evidence_summary = (
        f"outcomes: raw_succeeded={summary.get('succeeded', 0)} "
        f"raw_failed={summary.get('failed', 0)} raw_unknown={summary.get('unknown', 0)} "
        f"relevant={len(relevant)} verified_success={len(successes)} "
        f"verified_failure={len(failures)} pending_review={state_counts.get('pending_review', 0)} "
        f"unrelated={state_counts.get('unrelated', 0)} unverified={state_counts.get('unverified', 0)} "
        f"evidence_status_counts={summary.get('evidence_status_counts', {})}"
    )

    payload = {
        "last_verified_success": _record_brief(successes[-1] if successes else None),
        "last_verified_failure": _record_brief(failures[-1] if failures else None),
        "objective_progress": progress,
        "evidence_summary": evidence_summary,
        "evidence_sources": sorted(set(evidence_sources)),
        "outcome_confidence": round(confidence, 3),
        "last_outcome_checked_at": report.get("updated_at") or utcnow(),
    }
    signature_payload = {k: v for k, v in payload.items() if k != "last_outcome_checked_at"}
    for key in ("last_verified_success", "last_verified_failure"):
        if isinstance(signature_payload.get(key), dict):
            signature_payload[key] = {
                item_key: item_value
                for item_key, item_value in signature_payload[key].items()
                if item_key not in {"checked_at", "evidence_age"}
            }
    signature_raw = json.dumps(signature_payload, sort_keys=True, default=str)
    payload["outcome_evidence_signature"] = hashlib.sha256(signature_raw.encode()).hexdigest()[:16]
    return payload


def sync_executive_context(report: dict, executive_context: dict | None = None, dry_run: bool = False) -> dict:
    evidence = build_executive_evidence(report, executive_context=executive_context)
    if dry_run:
        return evidence
    try:
        from core.executive_context import load_context, safe_update

        current = load_context(create=True)
        updates = evidence
        if current.get("outcome_evidence_signature") == evidence.get("outcome_evidence_signature"):
            updates = {"last_outcome_checked_at": evidence["last_outcome_checked_at"]}

        safe_update(
            updates,
            source="outcome_loop",
            reason="outcome_loop recorded verified outcome evidence",
        )
    except Exception as exc:
        log(f"executive_context outcome evidence sync failed: {exc}")
    return evidence


def write_markdown(report: dict) -> None:
    summary = report["summary"]
    lines = [
        "# Echo Outcome Loop",
        f"_updated {report['updated_at']}_",
        "",
        "## Summary",
        f"- total: {summary['total']}",
        f"- raw_succeeded: {summary['succeeded']}",
        f"- raw_failed: {summary['failed']}",
        f"- unknown: {summary['unknown']}",
        f"- success_rate: {summary['success_rate']}",
        f"- evidence_status_counts: {summary.get('evidence_status_counts', {})}",
        "",
        "## Recent Records",
    ]
    for record in report["records"][-20:]:
        lines.append(
            f"- {record['outcome_state']} / {record.get('evidence_status')} "
            f"({record['status']}): {record['action_id']} -> "
            f"{record.get('evidence_backed_summary') or record['evidence']}"
        )
    REPORT_MD.write_text("\n".join(lines) + "\n")


def run(dry_run: bool = False, seed: bool = True) -> dict:
    executive_context = load_executive_context_snapshot()
    if seed and not dry_run:
        seed_current_expectations()
    records = evaluate_pending(include_resolved=True)
    report = build_report(records, executive_context=executive_context)
    report["executive_context"] = executive_context
    executive_evidence = sync_executive_context(report, executive_context=executive_context, dry_run=dry_run)
    report["executive_evidence"] = executive_evidence
    try:
        from core.experience_layer import promote_from_outcome_report

        report["experience"] = promote_from_outcome_report(
            report,
            executive_context=executive_context,
            dry_run=dry_run,
        )
    except Exception as exc:
        report["experience"] = {"error": str(exc), "promoted_count": 0}
    if not dry_run:
        write_json(REPORT_JSON, report)
        write_markdown(report)
        try:
            from core.event_ledger import log_event

            log_event(
                "outcome_loop",
                "outcome_loop",
                f"outcomes: succeeded={report['summary']['succeeded']} failed={report['summary']['failed']} unknown={report['summary']['unknown']}",
                score=report["summary"].get("success_rate") or 0.0,
                data=report["summary"],
            )
        except Exception:
            pass
    log(
        "outcome_loop "
        f"succeeded={report['summary']['succeeded']} "
        f"failed={report['summary']['failed']} "
        f"unknown={report['summary']['unknown']} dry_run={dry_run}"
    )
    return {
        "dry_run": dry_run,
        "json_path": str(REPORT_JSON),
        "md_path": str(REPORT_MD),
        "report": report,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--no-seed", action="store_true")
    parser.add_argument("--print", action="store_true")
    args = parser.parse_args()
    result = run(dry_run=args.dry_run, seed=not args.no_seed)
    if args.print:
        print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
