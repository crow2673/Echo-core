#!/usr/bin/env python3
"""
echo_verify.py — Outcome validator for echo_planner.py
After each step executes, checks: did it actually work?
Feeds success/failure back to planner for retry/escalate/continue.
Part of the Architecture Leap: Planner → Verify → Reach
"""
import json
import re
import subprocess
from pathlib import Path
from datetime import datetime

BASE = Path(__file__).resolve().parent
LOG = BASE / "logs/verifier.log"
MAX_RETRIES = 2

def log(msg):
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    line = f"{ts} — {msg}"
    print(f"[verify] {msg}")
    try:
        with open(LOG, "a") as f:
            f.write(line + "\n")
    except Exception:
        pass

# ── Verification rules per intent ─────────────────────────────────────
VERIFY_RULES = {
    "publish": {
        "check": "stdout_contains",
        "pattern": "Published:",
        "description": "Article published to dev.to"
    },
    "trade": {
        "check": "stdout_contains",
        "pattern": "trade_brain v2 done",
        "description": "Trade brain cycle completed"
    },
    "crypto": {
        "check": "stdout_contains",
        "pattern": "crypto_brain done",
        "description": "Crypto brain cycle completed"
    },
    "brief": {
        "check": "stdout_contains",
        "pattern": "Spoken successfully",
        "description": "Briefing spoken aloud"
    },
    "checkpoint": {
        "check": "file_updated",
        "path": "memory/session_summary.json",
        "max_age_seconds": 120,
        "description": "Session summary written"
    },
    "governor": {
        "check": "file_updated",
        "path": "memory/echo_state.json",
        "max_age_seconds": 60,
        "description": "Echo state updated"
    },
    "notify": {
        "check": "always_pass",
        "description": "Notification sent"
    },
    "shell": {
        "check": "exit_code",
        "description": "Shell command succeeded"
    },
    "file_read": {
        "check": "stdout_not_empty",
        "description": "File content returned"
    },
    "file_write": {
        "check": "always_pass",
        "description": "File written"
    },
    "memory": {
        "check": "always_pass",
        "description": "Memory operation done"
    },
}

def verify_step(intent, result):
    """
    Verify a step outcome.
    Returns dict with: passed, confidence, reason, suggestion
    """
    rule = VERIFY_RULES.get(intent)
    if not rule:
        return {
            "passed": result.get("success", False),
            "confidence": 0.5,
            "reason": f"No verification rule for intent: {intent}",
            "suggestion": None
        }

    check_type = rule["check"]

    # Exit code check
    if check_type == "exit_code":
        passed = result.get("success", False)
        return {
            "passed": passed,
            "confidence": 0.9,
            "reason": rule["description"] if passed else f"Command failed: {result.get('stderr', '')}",
            "suggestion": "retry" if not passed else None
        }

    # Stdout contains pattern
    if check_type == "stdout_contains":
        stdout = result.get("stdout", "")
        pattern = rule["pattern"]
        passed = pattern.lower() in stdout.lower()
        return {
            "passed": passed,
            "confidence": 0.95 if passed else 0.8,
            "reason": f"Found '{pattern}' in output" if passed else f"Pattern '{pattern}' not found in output",
            "suggestion": "retry" if not passed else None
        }

    # Stdout not empty
    if check_type == "stdout_not_empty":
        stdout = result.get("stdout", "").strip()
        passed = len(stdout) > 0
        return {
            "passed": passed,
            "confidence": 0.9,
            "reason": "Output received" if passed else "Empty output",
            "suggestion": "retry" if not passed else None
        }

    # File updated recently
    if check_type == "file_updated":
        path = BASE / rule["path"]
        max_age = rule.get("max_age_seconds", 120)
        if not path.exists():
            return {
                "passed": False,
                "confidence": 0.95,
                "reason": f"File not found: {path}",
                "suggestion": "escalate"
            }
        age = (datetime.now().timestamp() - path.stat().st_mtime)
        passed = age <= max_age
        return {
            "passed": passed,
            "confidence": 0.9 if passed else 0.7,
            "reason": f"File updated {age:.0f}s ago" if passed else f"File too old ({age:.0f}s > {max_age}s)",
            "suggestion": "retry" if not passed else None
        }

    # Always pass
    if check_type == "always_pass":
        return {
            "passed": True,
            "confidence": 1.0,
            "reason": rule["description"],
            "suggestion": None
        }

    return {
        "passed": False,
        "confidence": 0.0,
        "reason": f"Unknown check type: {check_type}",
        "suggestion": "escalate"
    }


def verify_plan(plan):
    """
    Verify all steps in a plan.
    Returns enriched plan with verification results.
    """
    verified_results = []
    plan_passed = True

    for i, result_entry in enumerate(plan.get("results", [])):
        intent = result_entry.get("intent")
        result = result_entry.get("result", {})
        step_num = result_entry.get("step", i + 1)

        verification = verify_step(intent, result)
        log(f"Step {step_num} ({intent}): {'✅ PASS' if verification['passed'] else '❌ FAIL'} — {verification['reason']}")

        verified_results.append({
            **result_entry,
            "verification": verification
        })

        if not verification["passed"]:
            plan_passed = False

    plan["results"] = verified_results
    plan["verified"] = True
    plan["all_passed"] = plan_passed
    plan["verified_at"] = datetime.now().isoformat()

    # Determine overall recommendation
    if plan_passed:
        plan["recommendation"] = "complete"
        log("Plan verified — all steps passed")
    else:
        failed = [r for r in verified_results if not r["verification"]["passed"]]
        suggestions = set(r["verification"].get("suggestion") for r in failed)
        if "escalate" in suggestions:
            plan["recommendation"] = "escalate"
            log("Plan has failures requiring escalation to Andrew")
        elif "retry" in suggestions:
            plan["recommendation"] = "retry"
            log("Plan has retryable failures")
        else:
            plan["recommendation"] = "failed"

    return plan


def run_verified_plan(goal_text, max_retries=MAX_RETRIES):
    """
    Run a plan with verification and retry logic.
    This is the main entry point that combines planner + verifier.
    """
    from echo_planner import run_plan

    attempt = 0
    plan = None

    while attempt <= max_retries:
        attempt += 1
        log(f"Attempt {attempt}/{max_retries + 1} for goal: {goal_text[:60]}")

        plan = run_plan(goal_text, use_ollama=(attempt == 1))
        plan = verify_plan(plan)

        if plan["recommendation"] == "complete":
            log("Goal achieved successfully")
            return plan

        if plan["recommendation"] == "escalate":
            log("Escalating to Andrew — cannot retry automatically")
            # Send ntfy alert
            try:
                import urllib.request
                msg = f"Echo needs help: {goal_text[:100]}"
                req = urllib.request.Request(
                    "https://ntfy.sh/echo-alerts",
                    data=msg.encode(),
                    method="POST"
                )
                urllib.request.urlopen(req, timeout=5)
            except Exception:
                pass
            return plan

        if plan["recommendation"] == "retry" and attempt <= max_retries:
            log(f"Retrying... ({attempt}/{max_retries})")
            continue

        break

    log(f"Goal incomplete after {attempt} attempts")
    return plan


if __name__ == "__main__":
    import sys

    # Test verification logic without running real steps
    print("Testing verifier with mock results:\n")

    mock_tests = [
        ("publish",    {"success": True,  "stdout": "✅ Published: https://dev.to/crow/test"}),
        ("trade",      {"success": True,  "stdout": "=== trade_brain v2 done ==="}),
        ("brief",      {"success": False, "stdout": "[briefing] Failed to generate briefing"}),
        ("governor",   {"success": True,  "stdout": "echo_state.json written"}),
        ("notify",     {"success": True,  "message": "test"}),
    ]

    for intent, result in mock_tests:
        v = verify_step(intent, result)
        status = "✅ PASS" if v["passed"] else "❌ FAIL"
        print(f"  {intent:12} {status} — {v['reason']}")
