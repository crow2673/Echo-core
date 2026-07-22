#!/usr/bin/env python3
"""Evidence-backed self-model and metacognitive calibration for Echo."""
import json
import sqlite3
from pathlib import Path

BASE = Path(__file__).resolve().parents[1]


def snapshot() -> dict:
    """Describe Echo from live evidence, explicitly separating unknowns."""
    result = {
        "identity": "Echo, a local Python/Ollama agent system built by Andrew",
        "consciousness": {
            "status": "unknown_not_established",
            "evidence": "No accepted test here can establish subjective experience.",
        },
        "system_health": "unknown",
        "health_reasons": [],
        "semantic_memory": {"status": "unknown"},
        "regret_learning": {"status": "unknown"},
        "prediction_calibration": {"status": "unknown"},
        "limits": [
            "Cannot establish consciousness from fluent self-reports.",
            "Cannot treat internal activity as proof of external success.",
            "Cannot claim completion without independently checked evidence.",
        ],
    }

    try:
        state = json.loads((BASE / "memory/echo_state.json").read_text())
        result["system_health"] = state.get("system_health", "unknown")
        result["health_reasons"] = state.get("last_errors", [])
        result["regret_learning"] = state.get("regret_index", {"status": "unknown"})
        regret_entries = result["regret_learning"].get("entries", 0)
        result["regret_learning"]["evidence_strength"] = (
            "low" if regret_entries < 5 else "moderate" if regret_entries < 20 else "high"
        )
        result["regret_learning"]["interpretation"] = (
            "Records exist and can be updated. This does not yet prove that regret learning "
            "improves future decisions."
        )
    except Exception as e:
        result["health_reasons"] = [{"state_read_error": str(e)}]

    try:
        db = sqlite3.connect(BASE / "echo_semantic_memory.sqlite")
        total = db.execute("SELECT COUNT(*) FROM memories").fetchone()[0]
        retrieved = db.execute(
            "SELECT COUNT(*) FROM memories WHERE retrieval_count > 0"
        ).fetchone()[0]
        latest = db.execute("SELECT MAX(created_at) FROM memories").fetchone()[0]
        db.close()
        result["semantic_memory"] = {
            "status": "active" if latest else "empty",
            "entries": total,
            "retrieved_entries": retrieved,
            "latest_memory": latest,
        }
    except Exception as e:
        result["semantic_memory"] = {"status": "error", "error": str(e)}

    try:
        from core.prediction_ledger import calibration_stats
        result["prediction_calibration"] = calibration_stats()
    except Exception as e:
        result["prediction_calibration"] = {"status": "error", "error": str(e)}

    return result


def context_block() -> str:
    """Prompt block that prevents self-claims from outrunning evidence."""
    state = snapshot()
    return (
        "EVIDENCE-BACKED SELF-MODEL:\n"
        f"{json.dumps(state, default=str)}\n"
        "METACOGNITIVE RULES:\n"
        "- Separate observed facts, inferences, and unknowns.\n"
        "- Calibrate confidence from the evidence above; never give a numerical confidence "
        "unless a measured calibration procedure produced it.\n"
        "- Do not claim a subsystem is active when its status is inactive, error, or unknown.\n"
        "- A plan is not an action, and an action is not a verified outcome.\n"
        "- Do not claim consciousness or deny its philosophical possibility as a measured fact; "
        "state that subjective experience is not established by available evidence."
    )
