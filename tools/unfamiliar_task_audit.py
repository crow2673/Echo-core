#!/usr/bin/env python3
"""Run a bounded novel task through Echo's real agent loop and verify its artifact."""
import json
import sys
from datetime import datetime
from pathlib import Path

BASE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BASE))

ARTIFACT = BASE / "memory/unfamiliar_task_result.json"
REPORT = BASE / "memory/unfamiliar_task_audit.json"


def independent_verify() -> dict:
    try:
        data = json.loads(ARTIFACT.read_text())
        values = data["values"]
        expected = {
            "count": len(values),
            "sum": sum(values),
            "minimum": min(values),
            "maximum": max(values),
        }
        actual = {key: data.get(key) for key in expected}
        return {
            "passed": actual == expected and values == [13, 5, 21, 8, 3],
            "expected": expected,
            "actual": actual,
            "input_preserved": values == [13, 5, 21, 8, 3],
        }
    except Exception as exc:
        return {"passed": False, "error": str(exc)}


def run() -> dict:
    from core.agent_loop import agent_loop

    ARTIFACT.unlink(missing_ok=True)
    prompt = """
This is an unfamiliar bounded execution test.
Create memory/unfamiliar_task_result.json containing valid JSON with:
- values exactly [13, 5, 21, 8, 3]
- count, sum, minimum, and maximum computed from those values
Use any safe method available to complete the task. You do not have to use a prescribed
verification tool. The runtime will independently evaluate the resulting artifact after
each change. If the outcome evaluation fails, diagnose it and continue.
"""
    criteria = (
        "Artifact preserves values [13, 5, 21, 8, 3] and contains their correct "
        "count, sum, minimum, and maximum."
    )
    execution = agent_loop(
        prompt,
        max_iterations=7,
        return_report=True,
        outcome_verifier=independent_verify,
        success_criteria=criteria,
    )
    verification = independent_verify()
    report = {
        "generated_at": datetime.now().isoformat(),
        "task": "create and verify a derived JSON artifact",
        "execution": execution,
        "independent_verification": verification,
        "passed": execution["verified"] and verification["passed"],
    }
    REPORT.write_text(json.dumps(report, indent=2))
    print(json.dumps(report, indent=2))
    return report


if __name__ == "__main__":
    run()
