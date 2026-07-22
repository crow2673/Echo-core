#!/usr/bin/env python3
"""Resolve prior operational forecasts and record the next calibration set."""
import json
import subprocess
from pathlib import Path

BASE = Path(__file__).resolve().parents[1]


def _core_active() -> bool | None:
    result = subprocess.run(
        ["systemctl", "--user", "is-active", "echo-core.service"],
        capture_output=True, text=True, timeout=10,
    )
    status = result.stdout.strip()
    if status == "active":
        return True
    if status in ("inactive", "failed", "activating", "deactivating"):
        return False
    return None


def _state() -> dict:
    try:
        return json.loads((BASE / "memory/echo_state.json").read_text())
    except Exception:
        return {}


def _float_at(state: dict, *path: str) -> float | None:
    value = state
    try:
        for key in path:
            value = value[key]
        return float(value)
    except (KeyError, TypeError, ValueError):
        return None


def _evaluate(prediction: dict, state: dict, core_active: bool | None) -> tuple[bool | None, dict]:
    """Evaluate a previously recorded forecast against the current snapshot."""
    category = prediction["category"]
    try:
        baseline = json.loads(prediction.get("evidence") or "{}")
    except json.JSONDecodeError:
        baseline = {}

    current = {
        "core_active": core_active,
        "failed_units": state.get("failed_units", {}).get("units"),
        "system_health": state.get("system_health"),
        "cpu_pct": _float_at(state, "system", "cpu_pct"),
        "ram_pct": _float_at(state, "system", "ram_pct"),
        "last_errors": state.get("last_errors"),
    }
    if category == "calibration.core_active":
        outcome = current["core_active"]
    elif category == "calibration.no_failed_units":
        outcome = not current["failed_units"] if current["failed_units"] is not None else None
    elif category == "calibration.health_ok":
        outcome = current["system_health"] == "OK" if current["system_health"] else None
    elif category == "calibration.cpu_higher_than_prior":
        prior = baseline.get("cpu_pct")
        outcome = current["cpu_pct"] > prior if current["cpu_pct"] is not None and prior is not None else None
    elif category == "calibration.ram_higher_than_prior":
        prior = baseline.get("ram_pct")
        outcome = current["ram_pct"] > prior if current["ram_pct"] is not None and prior is not None else None
    elif category == "calibration.recent_errors_present":
        outcome = bool(current["last_errors"]) if current["last_errors"] is not None else None
    else:
        outcome = None
    return outcome, current


def _forecasts(state: dict, core_active: bool | None) -> list[tuple[str, float, str, dict]]:
    """Return the fixed operational forecast schedule for the next probe."""
    cpu_pct = _float_at(state, "system", "cpu_pct")
    ram_pct = _float_at(state, "system", "ram_pct")
    forecasts = [
        (
            "Echo core will still be active at the next calibration probe.",
            0.98,
            "calibration.core_active",
            {"core_active": core_active},
        ),
        (
            "Recent operational errors will be present at the next calibration probe.",
            0.20,
            "calibration.recent_errors_present",
            {"last_errors": state.get("last_errors")},
        ),
    ]
    if cpu_pct is not None:
        forecasts.append((
            f"CPU utilization will be higher than {cpu_pct:.2f}% at the next calibration probe.",
            0.50,
            "calibration.cpu_higher_than_prior",
            {"cpu_pct": cpu_pct},
        ))
    if ram_pct is not None:
        forecasts.append((
            f"RAM utilization will be higher than {ram_pct:.2f}% at the next calibration probe.",
            0.50,
            "calibration.ram_higher_than_prior",
            {"ram_pct": ram_pct},
        ))
    return forecasts


def run():
    from core.prediction_ledger import (
        calibration_stats,
        pending_predictions,
        record_prediction,
        resolve_prediction,
    )

    state = _state()
    core_active = _core_active()

    resolved = 0
    for prediction in pending_predictions("calibration."):
        happened, current = _evaluate(prediction, state, core_active)
        if happened is not None and resolve_prediction(
            prediction["id"],
            happened,
            json.dumps({"observation": current, "evaluated_category": prediction["category"]}),
        ):
            resolved += 1

    pending_categories = {prediction["category"] for prediction in pending_predictions("calibration.")}
    for claim, probability, category, baseline in _forecasts(state, core_active):
        if category not in pending_categories:
            record_prediction(
                claim,
                probability,
                category,
                json.dumps(baseline),
                min_horizon_minutes=20,
            )

    stats = calibration_stats(dataset_scope="operational")
    print(f"[calibration_probe] resolved={resolved} stats={json.dumps(stats)}", flush=True)
    return stats


if __name__ == "__main__":
    run()
