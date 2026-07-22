#!/usr/bin/env python3
"""Build safe, declarative outcome verifiers for persistent goals."""
import json
import subprocess
from pathlib import Path

BASE = Path(__file__).resolve().parents[1]


def _inside_base(relative_path: str) -> Path:
    path = (BASE / relative_path).resolve()
    if not path.is_relative_to(BASE):
        raise ValueError("verification path must be inside Echo")
    return path


def verify(spec: dict) -> dict:
    """Evaluate an observable goal outcome without trusting agent prose."""
    kind = spec.get("type")
    if kind == "file":
        path = _inside_base(spec["path"])
        if not path.is_file():
            return {"passed": False, "type": kind, "reason": "file missing", "path": spec["path"]}
        content = path.read_text()
        missing = [text for text in spec.get("contains", []) if text not in content]
        minimum_bytes = int(spec.get("minimum_bytes", 1))
        return {
            "passed": not missing and len(content.encode()) >= minimum_bytes,
            "type": kind,
            "path": spec["path"],
            "bytes": len(content.encode()),
            "missing_required_text": missing,
        }
    if kind == "json":
        path = _inside_base(spec["path"])
        try:
            data = json.loads(path.read_text())
        except Exception as exc:
            return {"passed": False, "type": kind, "path": spec["path"], "error": str(exc)}
        equals = spec.get("equals", {})
        mismatches = {
            key: {"expected": expected, "actual": data.get(key)}
            for key, expected in equals.items()
            if data.get(key) != expected
        }
        required = spec.get("required_keys", [])
        missing = [key for key in required if key not in data]
        return {
            "passed": not mismatches and not missing,
            "type": kind,
            "path": spec["path"],
            "mismatches": mismatches,
            "missing_keys": missing,
        }
    if kind == "service_active":
        unit = spec.get("unit", "")
        if not unit.startswith("echo-") or not unit.endswith((".service", ".timer")):
            return {"passed": False, "type": kind, "reason": "unit outside Echo allowlist"}
        result = subprocess.run(
            ["systemctl", "--user", "is-active", unit],
            capture_output=True, text=True, timeout=10,
        )
        observed = result.stdout.strip()
        return {"passed": observed == "active", "type": kind, "unit": unit, "observed": observed}
    return {"passed": False, "reason": "no supported outcome verifier", "type": kind}


def build(goal: dict):
    """Return a verifier callable only when a goal has a supported specification."""
    spec = goal.get("verification")
    if not isinstance(spec, dict) or spec.get("type") not in {"file", "json", "service_active"}:
        return None
    return lambda: verify(spec)
