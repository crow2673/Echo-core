from pathlib import Path

import pytest

from self_ai.benchmark import BenchmarkResult, compare
from self_ai.safety import CandidateRejected, inspect_candidate
from self_ai.evidence import Evidence, EvidenceLedger


def test_safety_rejects_network_import():
    with pytest.raises(CandidateRejected):
        inspect_candidate("import requests\ndef tool():\n    return 1")


def test_safety_allows_small_pure_tool():
    inspect_candidate("def tool(value):\n    return value + 1")


def test_compare_requires_real_improvement():
    baseline = BenchmarkResult(score=1.0, passed=True, details="")
    equal = BenchmarkResult(score=1.0, passed=True, details="")
    better = BenchmarkResult(score=1.1, passed=True, details="")
    assert compare(baseline, equal)[0] is False
    assert compare(baseline, better)[0] is True


def test_evidence_ledger_round_trip(tmp_path: Path):
    ledger = EvidenceLedger(tmp_path)
    candidate = tmp_path / "candidate.py"
    candidate.write_text("def tool():\n    return 1\n", encoding="utf-8")
    evidence = Evidence(
        candidate=str(candidate),
        candidate_sha256=ledger.sha256(candidate),
        baseline_score=1.0,
        candidate_score=2.0,
        passed=True,
        reason="improved",
    )
    ledger.record(evidence)
    assert ledger.recent(1)[0]["passed"] is True
