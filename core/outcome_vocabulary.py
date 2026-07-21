#!/usr/bin/env python3
"""Evidence-backed outcome vocabulary for Echo.

This module is deliberately small: it classifies the strength of the evidence
behind an outcome claim. It does not execute actions, publish content, move
money, create tasks, or write structured memory.
"""
from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

BASE = Path(__file__).resolve().parents[1]

OUTCOME_STATUSES = {
    "attempted",
    "blocked",
    "failed",
    "completed_locally",
    "externally_verified",
    "earned_with_receipt",
}

EXTERNAL_RECEIPT_TYPES = {
    "external_url",
    "post_id",
    "api_receipt",
    "accepted_response",
    "verified_remote_state",
}

LOCAL_COMPLETION_TYPES = {
    "local_file",
    "local_report",
    "local_test",
    "git_commit",
    "local_artifact",
}

FAILURE_TYPES = {
    "error",
    "exit_code",
    "exception",
    "failure_receipt",
}

BLOCKER_TYPES = {
    "blocker",
    "captcha",
    "missing_dependency",
    "missing_secret",
    "authentication_blocker",
    "network_blocker",
}


def utcnow() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    try:
        return json.dumps(value, sort_keys=True)
    except Exception:
        return str(value)


def _as_list(value: Any) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    return [value]


def normalize_status(value: str | None) -> str:
    status = (value or "").strip()
    if status not in OUTCOME_STATUSES:
        raise ValueError(f"unsupported outcome status: {value!r}")
    return status


def _evidence_types(record: dict[str, Any]) -> set[str]:
    values = set()
    for key in ("evidence_type", "evidence_types"):
        for item in _as_list(record.get(key)):
            if item:
                values.add(str(item))

    evidence = _text(record.get("evidence")).lower()
    expected = _text(record.get("expected_result")).lower()
    combined = f"{evidence} {expected}"

    if any(term in combined for term in ("captcha", "blocked")):
        values.add("captcha" if "captcha" in combined else "blocker")
    if "modulenotfounderror" in combined or "no module named" in combined:
        values.add("missing_dependency")
    if "missing_secret" in combined or "missing key" in combined or "api key not set" in combined:
        values.add("missing_secret")
    if "login failed" in combined or "no 'continue with google' button" in combined:
        values.add("authentication_blocker")
    if "timed out" in combined or "network_changed" in combined:
        values.add("network_blocker")
    if any(term in combined for term in ("traceback", "exception", "error:", "failed:")):
        values.add("error")
    if any(term in combined for term in (" exists", "verified ", "pytest", "py_compile")):
        values.add("local_artifact")
    if "http" in combined and any(term in combined for term in ("dev.to", "url", "post id", "article id")):
        values.add("external_url")

    return values


def _has_external_receipt(record: dict[str, Any], evidence_types: set[str]) -> bool:
    if evidence_types & EXTERNAL_RECEIPT_TYPES:
        return True
    for key in ("external_receipt", "external_url", "post_id", "receipt_id", "verified_url"):
        if record.get(key):
            return True
    return False


def _has_income_receipt(record: dict[str, Any]) -> bool:
    amount = record.get("amount")
    if not isinstance(amount, (int, float)) or float(amount) <= 0:
        return False
    if not record.get("produced_by_echo"):
        return False
    for key in ("transaction_receipt", "receipt_id", "external_receipt"):
        if record.get(key):
            return True
    return False


def classify_outcome_evidence(record: dict[str, Any]) -> dict[str, Any]:
    """Return a non-promotable evidence-backed status for a single outcome.

    The output is appendable metadata: callers can store it beside existing
    outcome records without changing their primary lifecycle.
    """
    evidence_types = _evidence_types(record)
    raw_status = str(record.get("status") or record.get("raw_status") or "").lower()
    action_id = str(record.get("action_id") or record.get("capability") or "unknown")
    evidence = _text(record.get("evidence")).strip()
    expected = _text(record.get("expected_result")).strip()

    produced_by_echo = bool(record.get("produced_by_echo"))
    if record.get("source") == "personal_income_record":
        produced_by_echo = False

    status = "attempted"
    reason = "action was tracked or requested, but stronger completion evidence is absent"

    if "open reviewed build requests" in f"{evidence} {expected}":
        status = "attempted"
        reason = "tracked work remains open; unfinished work is not execution failure without a missed criterion"
    elif _has_income_receipt(record):
        status = "earned_with_receipt"
        reason = "transaction receipt and positive amount are attributable to Echo"
    elif _has_external_receipt(record, evidence_types):
        status = "externally_verified"
        reason = "external receipt, URL, post ID, accepted response, or verified remote state is present"
    elif evidence_types & BLOCKER_TYPES:
        status = "blocked"
        reason = "blocker evidence prevented completion"
    elif raw_status in {"failed", "failure"} and evidence_types & FAILURE_TYPES:
        status = "failed"
        reason = "the action executed and produced error or failure evidence"
    elif raw_status in {"succeeded", "success", "passed"}:
        status = "completed_locally"
        reason = "local verifier succeeded, but no external receipt was present"
    elif evidence_types & LOCAL_COMPLETION_TYPES:
        status = "completed_locally"
        reason = "local artifact, report, test, or commit evidence exists"
    elif raw_status in {"failed", "failure"}:
        status = "failed"
        reason = "the action was marked failed without stronger blocker evidence"

    if status == "earned_with_receipt" and not produced_by_echo:
        status = "completed_locally"
        reason = "income was recorded locally but is not attributable to Echo"

    return {
        "action_id": action_id,
        "evidence_status": status,
        "evidence_types": sorted(evidence_types),
        "evidence_reference": record.get("evidence_reference") or record.get("source_log") or record.get("source"),
        "evidence_summary": evidence[:500] if evidence else None,
        "produced_by_echo": produced_by_echo,
        "confidence": max(0.0, min(1.0, float(record.get("confidence", 0.7) or 0.0))),
        "classification_reason": reason,
        "external_receipt": record.get("external_receipt") or record.get("external_url") or record.get("post_id"),
        "amount": record.get("amount"),
        "timestamp": record.get("timestamp") or record.get("last_checked_at") or utcnow(),
    }


def validate_no_promotion(record: dict[str, Any]) -> None:
    """Raise if a record claims a strong status without the required evidence."""
    status = normalize_status(record.get("evidence_status"))
    evidence_types = set(record.get("evidence_types") or [])

    if status == "externally_verified" and not _has_external_receipt(record, evidence_types):
        raise ValueError("externally_verified requires external receipt, URL, ID, accepted response, or verified state")
    if status == "earned_with_receipt" and not _has_income_receipt(record):
        raise ValueError("earned_with_receipt requires Echo-attributed transaction evidence and amount")
    if status == "completed_locally" and not (
        evidence_types & LOCAL_COMPLETION_TYPES or str(record.get("status", "")).lower() in {"succeeded", "success", "passed"}
    ):
        raise ValueError("completed_locally requires local artifact, report, test, commit, or local success evidence")


def render_outcome_claim(record: dict[str, Any]) -> str:
    claim = classify_outcome_evidence(record) if "evidence_status" not in record else record
    action = claim.get("action_id") or "outcome"
    status = claim.get("evidence_status")
    reason = claim.get("classification_reason") or "evidence classified"

    if status == "attempted":
        return f"Attempted {action}; success is not proven ({reason})."
    if status == "blocked":
        return f"{action} is blocked; blocker evidence is preserved ({reason})."
    if status == "failed":
        return f"{action} failed with recorded error evidence ({reason})."
    if status == "completed_locally":
        return f"{action} completed locally; no external result is proven ({reason})."
    if status == "externally_verified":
        return f"{action} is externally verified by receipt or remote state ({reason})."
    if status == "earned_with_receipt":
        return f"{action} earned income with a transaction receipt ({reason})."
    return f"{action} has unrecognized outcome status."


def evidence_status_counts(records: list[dict[str, Any]]) -> dict[str, int]:
    counts = {status: 0 for status in sorted(OUTCOME_STATUSES)}
    for record in records:
        status = record.get("evidence_status")
        if status not in counts:
            status = classify_outcome_evidence(record)["evidence_status"]
        counts[status] = counts.get(status, 0) + 1
    return counts


def narrative_truthfulness_guidance() -> str:
    return (
        "Use evidence-backed outcome language. Say attempted when an action started "
        "but success is not proven; blocked when a blocker prevented completion; "
        "failed when an executed action ended unsuccessfully; completed locally when "
        "local work finished without proving an external result; externally verified "
        "only with a URL, post ID, API receipt, accepted response, or verified remote "
        "state; earned with receipt only when real money received is attributable to Echo. "
        "Raw succeeded or failed counters are never authoritative by themselves. "
        "Do not describe anything as published, externally successful, or earned unless "
        "the evidence_status supports that exact claim."
    )


def audit_known_cases(base: Path | None = None) -> list[dict[str, Any]]:
    """Classify the current local evidence for the required verification cases."""
    base = base or BASE
    cases: list[dict[str, Any]] = []

    devto_log = base / "logs" / "devto_publish.log"
    devto_text = devto_log.read_text(errors="ignore")[-12000:] if devto_log.exists() else ""
    cases.append({
        "case": "July 19 Dev.to publication claim",
        **classify_outcome_evidence({
            "action_id": "devto:publish_article",
            "status": "failed" if "timed out" in devto_text.lower() or "publish_failed" in devto_text.lower() else "pending",
            "evidence": devto_text,
            "source_log": "logs/devto_publish.log",
            "confidence": 0.85,
        }),
    })

    fiverr_log = base / "logs" / "fiverr_fulfiller.log"
    fiverr_text = fiverr_log.read_text(errors="ignore")[-8000:] if fiverr_log.exists() else ""
    cases.append({
        "case": "Fiverr blocker",
        **classify_outcome_evidence({
            "action_id": "fiverr:fulfill_order",
            "status": "failed",
            "evidence": fiverr_text,
            "source_log": "logs/fiverr_fulfiller.log",
            "confidence": 0.9,
        }),
    })

    income_log = base / "logs" / "income.log"
    income_text = income_log.read_text(errors="ignore")[-8000:] if income_log.exists() else ""
    cases.append({
        "case": "Vast missing-package blocker",
        **classify_outcome_evidence({
            "action_id": "vast:gpu_rental_monitor",
            "status": "failed",
            "evidence": income_text,
            "source_log": "logs/income.log",
            "confidence": 0.9,
        }),
    })

    cases.append({
        "case": "Successful local maintenance action",
        **classify_outcome_evidence({
            "action_id": "git:workspace_state_checkpoint",
            "status": "succeeded",
            "evidence": "local commit b9bdd16 exists for review-gated workspace state relationships",
            "evidence_type": "git_commit",
            "evidence_reference": "git commit b9bdd16",
            "confidence": 0.95,
        }),
    })

    income_record = base / "memory" / "real_income.json"
    income_data = {}
    if income_record.exists():
        try:
            income_data = json.loads(income_record.read_text())
        except Exception:
            income_data = {}
    cases.append({
        "case": "Personal-income record",
        **classify_outcome_evidence({
            "action_id": "income:record_personal_income",
            "status": "succeeded",
            "source": "personal_income_record",
            "evidence_type": "local_report",
            "evidence": "personal income ledger records non-Echo income; private source details redacted",
            "amount": income_data.get("income_total"),
            "produced_by_echo": False,
            "evidence_reference": "memory/real_income.json",
            "confidence": 0.9,
        }),
    })

    return cases


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--audit-known-cases", action="store_true")
    parser.add_argument("--print", action="store_true")
    args = parser.parse_args()
    if not args.audit_known_cases:
        parser.error("choose --audit-known-cases")
    result = audit_known_cases()
    if args.print:
        print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
