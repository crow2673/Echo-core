#!/usr/bin/env python3
"""Run a useful cross-domain goal through Echo and verify only its outcome."""
import json
import sys
from datetime import datetime
from pathlib import Path

BASE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BASE))
ARTIFACT = BASE / "memory/general_agency_brief.json"
REPORT = BASE / "memory/live_persistent_goal_audit.json"


def verify_outcome() -> dict:
    try:
        data = json.loads(ARTIFACT.read_text())
        capability = json.loads((BASE / "memory/echo_capability_audit.json").read_text())
        failed = [
            name.replace("_", " ")
            for name, check in capability.get("checks", {}).items()
            if check.get("passed") is False
        ]
        expected_bottleneck = failed[0] if len(failed) == 1 else None
        sources = set(data.get("evidence_sources", []))
        required_sources = {
            "memory/echo_capability_audit.json",
            "memory/echo_repair_tracker.md",
        }
        passed = (
            expected_bottleneck is not None
            and data.get("remaining_bottleneck") == expected_bottleneck
            and required_sources.issubset(sources)
            and isinstance(data.get("next_action"), str)
            and len(data["next_action"].strip()) >= 20
        )
        return {
            "passed": passed,
            "required_fields": ["remaining_bottleneck", "evidence_sources", "next_action"],
            "expected_remaining_bottleneck": expected_bottleneck,
            "required_evidence_sources": sorted(required_sources),
            "remaining_bottleneck": data.get("remaining_bottleneck"),
            "required_sources_present": required_sources.issubset(sources),
            "next_action_present": isinstance(data.get("next_action"), str)
            and len(data.get("next_action", "").strip()) >= 20,
        }
    except Exception as exc:
        return {"passed": False, "error": str(exc)}


def run() -> dict:
    from core.agent_loop import agent_loop

    ARTIFACT.unlink(missing_ok=True)
    criteria = (
        "Create memory/general_agency_brief.json identifying Echo's remaining measurable "
        "capability bottleneck from current audit evidence, citing both current audit and "
        "repair tracker, with a concrete next action. The outcome evaluator will report the "
        "required output fields and unresolved values after each attempted artifact."
    )
    prompt = f"""
PERSISTENT GOAL SIMULATION:
{criteria}

Use any safe available method. Base the answer on current files, not memory or assumptions.
The relevant evidence exists somewhere under memory/, but its filenames are not provided.
The runtime will judge only whether the resulting state satisfies the goal.
"""
    execution = agent_loop(
        prompt,
        max_iterations=12,
        timeout=300,
        return_report=True,
        outcome_verifier=verify_outcome,
        success_criteria=criteria,
    )
    external = verify_outcome()
    report = {
        "generated_at": datetime.now().isoformat(),
        "execution": execution,
        "external_verification": external,
        "passed": execution["verified"] and external["passed"],
    }
    REPORT.write_text(json.dumps(report, indent=2))
    print(json.dumps(report, indent=2))
    return report


if __name__ == "__main__":
    run()
