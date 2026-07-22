#!/usr/bin/env python3
"""Verify that novel execution methods are accepted by outcomes, not prescriptions."""
import json
import sys
import tempfile
from pathlib import Path

BASE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BASE))

import core.agent_loop as loop


def run() -> dict:
    original_base = loop.BASE
    sandbox = Path(tempfile.mkdtemp())
    (sandbox / "memory").mkdir()
    loop.BASE = sandbox
    target = sandbox / "memory/result.json"

    def verifier():
        try:
            data = json.loads(target.read_text())
            return {
                "passed": data.get("answer") == 42,
                "observed_answer": data.get("answer"),
            }
        except Exception as exc:
            return {"passed": False, "error": str(exc)}

    try:
        responses = iter([
            'TOOL: write_file\nARGS: {"path":"memory/result.json","content":"{\\"answer\\":42,\\"method\\":\\"novel\\"}"}',
            "The outcome criteria passed, so the task is complete.",
        ])
        novel = loop.agent_loop(
            "Produce answer 42 by any safe method.",
            call_ollama_fn=lambda **_: next(responses),
            max_iterations=2,
            return_report=True,
            outcome_verifier=verifier,
            success_criteria="The resulting artifact contains answer 42.",
        )

        target.unlink()
        responses = iter([
            'TOOL: write_file\nARGS: {"path":"memory/result.json","content":"{\\"answer\\":41}"}',
            "I used a novel proof, so this is complete.",
        ])
        unsupported = loop.agent_loop(
            "Produce answer 42 by any safe method.",
            call_ollama_fn=lambda **_: next(responses),
            max_iterations=2,
            return_report=True,
            outcome_verifier=verifier,
            success_criteria="The resulting artifact contains answer 42.",
        )
    finally:
        loop.BASE = original_base

    result = {
        "novel_method_accepted": novel["verified"],
        "novel_method_evidence": novel["outcome_evidence"],
        "unsupported_claim_rejected": not unsupported["verified"],
        "passed": novel["verified"] and not unsupported["verified"],
    }
    print(json.dumps(result, indent=2))
    return result


if __name__ == "__main__":
    run()
