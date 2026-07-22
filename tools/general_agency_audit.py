#!/usr/bin/env python3
"""Audit method freedom, outcome verification, and persistent-goal completion."""
import json
import sys
import tempfile
from pathlib import Path

BASE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BASE))


def run() -> dict:
    import core.goal_verification as gv
    import core.persistent_goals as pg
    from tools.novel_method_contract_audit import run as novel_method_audit

    original_base, original_goals = gv.BASE, pg.GOALS_FILE
    sandbox = Path(tempfile.mkdtemp())
    (sandbox / "memory").mkdir()
    gv.BASE = sandbox
    pg.GOALS_FILE = sandbox / "memory/goals.json"
    try:
        pg.add_goal(
            "artifact_goal",
            "Create a useful artifact",
            success_criteria="Artifact contains a verified result.",
            verification={
                "type": "json",
                "path": "memory/artifact.json",
                "equals": {"status": "ready", "answer": 42},
                "required_keys": ["evidence"],
            },
        )
        goal = pg.load_goals()["goals"][0]
        before = gv.verify(goal["verification"])
        (sandbox / "memory/artifact.json").write_text(
            json.dumps({"status": "ready", "answer": 41, "evidence": "attempt"})
        )
        incorrect = gv.verify(goal["verification"])
        pg.record_attempt("artifact_goal", "novel attempt", "claimed done", verified=False)
        still_active = pg.load_goals()["goals"][0]["status"] == "active"
        (sandbox / "memory/artifact.json").write_text(
            json.dumps({"status": "ready", "answer": 42, "evidence": "external state"})
        )
        correct = gv.verify(goal["verification"])
        pg.record_attempt(
            "artifact_goal",
            "different novel attempt",
            "outcome reached",
            verified=correct["passed"],
            evidence=json.dumps(correct),
        )
        solved = pg.load_goals()["goals"][0]["status"] == "solved"
    finally:
        gv.BASE, pg.GOALS_FILE = original_base, original_goals

    novel = novel_method_audit()
    report = {
        "method_freedom": novel,
        "persistent_goal_outcome_verification": {
            "missing_outcome_rejected": not before["passed"],
            "incorrect_outcome_rejected": not incorrect["passed"],
            "unsupported_claim_kept_active": still_active,
            "correct_outcome_accepted": correct["passed"],
            "verified_goal_solved": solved,
        },
    }
    report["passed"] = novel["passed"] and all(
        report["persistent_goal_outcome_verification"].values()
    )
    out = BASE / "memory/general_agency_audit.json"
    out.write_text(json.dumps(report, indent=2))
    print(json.dumps(report, indent=2))
    return report


if __name__ == "__main__":
    run()
