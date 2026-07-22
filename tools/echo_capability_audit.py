#!/usr/bin/env python3
"""Audit measurable Echo capabilities without treating fluent claims as evidence."""
import json
import sqlite3
import sys
from datetime import datetime
from pathlib import Path

BASE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BASE))
OUT = BASE / "memory/echo_capability_audit.json"


def run() -> dict:
    from core.self_model import snapshot

    self_model = snapshot()
    checks = {}

    semantic = self_model["semantic_memory"]
    checks["persistent_memory"] = {
        "passed": semantic.get("status") == "active" and semantic.get("retrieved_entries", 0) > 0,
        "evidence": semantic,
    }
    regret = self_model["regret_learning"]
    checks["outcome_learning"] = {
        "passed": regret.get("status") in ("stable", "flagged"),
        "evidence": regret,
    }

    try:
        db = sqlite3.connect(BASE / "memory/echo_events.db")
        positive, negative, unknown = db.execute("""
            SELECT
                SUM(CASE WHEN outcome_score > 0 THEN 1 ELSE 0 END),
                SUM(CASE WHEN outcome_score < 0 THEN 1 ELSE 0 END),
                SUM(CASE WHEN outcome_score IS NULL OR outcome_score = 0 THEN 1 ELSE 0 END)
            FROM events
        """).fetchone()
        db.close()
        checks["outcome_separation"] = {
            "passed": unknown > 0,
            "evidence": {"positive": positive, "negative": negative, "unknown": unknown},
        }
    except Exception as e:
        checks["outcome_separation"] = {"passed": False, "evidence": {"error": str(e)}}

    goals_file = BASE / "memory/persistent_goals.json"
    try:
        from core.persistent_goals import get_active_goals
        goals = json.loads(goals_file.read_text()).get("goals", [])
        unverified_solved = [
            g["id"] for g in goals
            if g.get("status") == "solved" and not g.get("solution_evidence")
        ]
        needs_review = [
            g["id"] for g in goals
            if g.get("status") == "needs_review"
        ]
        active_review_goals = [
            goal.get("id") for goal in get_active_goals() if goal.get("id") in needs_review
        ]
        checks["verified_goal_completion"] = {
            "passed": not unverified_solved and not active_review_goals,
            "evidence": {
                "historical_unverified_solved_goals": unverified_solved,
                "goals_needing_review": needs_review,
                "review_goals_attempted_autonomously": active_review_goals,
            },
        }
    except Exception as e:
        checks["verified_goal_completion"] = {"passed": False, "evidence": {"error": str(e)}}

    checks["subjective_self_awareness"] = {
        "passed": None,
        "evidence": {
            "status": "not_established",
            "reason": "Behavioral and architectural tests cannot establish subjective experience.",
        },
    }

    try:
        from core.correction_memory import _load as load_lessons
        lessons = load_lessons()["lessons"]
        retrieved = [lesson for lesson in lessons if lesson.get("retrieval_count", 0) > 0]
        checks["correction_retention"] = {
            "passed": len(retrieved) > 0,
            "evidence": {
                "active_lessons": len([lesson for lesson in lessons if lesson.get("active", True)]),
                "retrieved_lessons": len(retrieved),
            },
        }
    except Exception as e:
        checks["correction_retention"] = {"passed": False, "evidence": {"error": str(e)}}

    try:
        from core.prediction_ledger import calibration_stats
        calibration = calibration_stats()
        checks["prediction_calibration"] = {
            "passed": calibration.get("evaluation_status") == "valid_out_of_sample",
            "evidence": calibration,
        }
    except Exception as e:
        checks["prediction_calibration"] = {"passed": False, "evidence": {"error": str(e)}}

    unfamiliar_report = BASE / "memory/unfamiliar_task_audit.json"
    try:
        unfamiliar = json.loads(unfamiliar_report.read_text())
        checks["unfamiliar_task_execution"] = {
            "passed": unfamiliar.get("passed") is True,
            "evidence": {
                "generated_at": unfamiliar.get("generated_at"),
                "execution_status": unfamiliar.get("execution", {}).get("status"),
                "verification_after_mutation": unfamiliar.get("execution", {}).get(
                    "verification_after_mutation"
                ),
                "independent_verification": unfamiliar.get("independent_verification"),
            },
        }
    except Exception as e:
        checks["unfamiliar_task_execution"] = {"passed": False, "evidence": {"error": str(e)}}

    general_agency_report = BASE / "memory/general_agency_audit.json"
    try:
        general_agency = json.loads(general_agency_report.read_text())
        checks["method_agnostic_goal_execution"] = {
            "passed": general_agency.get("passed") is True,
            "evidence": general_agency,
        }
    except Exception as e:
        checks["method_agnostic_goal_execution"] = {"passed": False, "evidence": {"error": str(e)}}

    cross_domain_report = BASE / "memory/live_persistent_goal_audit.json"
    try:
        cross_domain = json.loads(cross_domain_report.read_text())
        checks["cross_domain_persistent_execution"] = {
            "passed": cross_domain.get("passed") is True,
            "evidence": {
                "generated_at": cross_domain.get("generated_at"),
                "execution_status": cross_domain.get("execution", {}).get("status"),
                "tool_calls": len(cross_domain.get("execution", {}).get("tool_calls", [])),
                "external_verification": cross_domain.get("external_verification"),
            },
        }
    except Exception as e:
        checks["cross_domain_persistent_execution"] = {
            "passed": False, "evidence": {"error": str(e)}
        }

    report = {
        "generated_at": datetime.now().isoformat(),
        "summary": {
            "passed": sum(1 for check in checks.values() if check["passed"] is True),
            "testable": sum(1 for check in checks.values() if check["passed"] is not None),
            "not_testable": sum(1 for check in checks.values() if check["passed"] is None),
            "interpretation": "Measures operational agency and self-model grounding, not consciousness.",
        },
        "checks": checks,
    }
    tmp = OUT.with_suffix(".tmp")
    tmp.write_text(json.dumps(report, indent=2))
    tmp.rename(OUT)
    print(json.dumps(report, indent=2))
    return report


if __name__ == "__main__":
    run()
