from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class CandidateRun:
    ok: bool
    value: float | None
    output: str
    error: str = ""


_RUNNER = r"""
import importlib.util
import json
import sys

path = sys.argv[1]
payload = json.loads(sys.argv[2])

spec = importlib.util.spec_from_file_location("candidate_module", path)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)

evaluate = getattr(module, "evaluate", None)
if not callable(evaluate):
    raise TypeError("candidate must define evaluate(payload)")

value = evaluate(payload)
print(json.dumps({"value": float(value)}))
"""


def run_candidate(
    candidate: Path,
    payload: object,
    timeout: float = 5.0,
) -> CandidateRun:
    """Run a candidate behind a small, bounded execution contract.

    This is an execution boundary, not a security sandbox. Static safety
    inspection remains mandatory before a candidate reaches this runner.
    """
    candidate = candidate.resolve()
    if not candidate.is_file():
        return CandidateRun(False, None, "", "candidate file does not exist")

    with tempfile.TemporaryDirectory(prefix="self_ai_bench_") as temp_dir:
        env = {"PYTHONIOENCODING": "utf-8", "PATH": os.environ.get("PATH", "")}
        try:
            result = subprocess.run(
                [
                    sys.executable,
                    "-I",
                    "-S",
                    "-c",
                    _RUNNER,
                    str(candidate),
                    json.dumps(payload),
                ],
                cwd=temp_dir,
                env=env,
                capture_output=True,
                text=True,
                timeout=timeout,
                check=False,
            )
        except subprocess.TimeoutExpired:
            return CandidateRun(False, None, "", "candidate timed out")

    output = result.stdout.strip()
    if result.returncode != 0:
        return CandidateRun(False, None, output, result.stderr.strip() or "candidate failed")

    try:
        value = float(json.loads(output)["value"])
    except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
        return CandidateRun(False, None, output, f"invalid candidate result: {exc}")

    return CandidateRun(True, value, output)
