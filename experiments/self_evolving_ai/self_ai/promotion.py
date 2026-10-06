from __future__ import annotations

import shutil
from pathlib import Path

from .benchmark import BenchmarkResult, compare
from .evidence import Evidence, EvidenceLedger


class PromotionGate:
    """Promote only candidates with objective evidence of improvement."""

    def __init__(self, root: Path):
        self.root = root.resolve()
        self.rollback_dir = self.root / "rollback"
        self.rollback_dir.mkdir(parents=True, exist_ok=True)
        self.ledger = EvidenceLedger(self.root)

    def evaluate(self, candidate: Path, baseline: BenchmarkResult, candidate_result: BenchmarkResult) -> Evidence:
        passed, reason = compare(baseline, candidate_result)
        return Evidence(
            candidate=str(candidate),
            candidate_sha256=EvidenceLedger.sha256(candidate),
            baseline_score=baseline.score,
            candidate_score=candidate_result.score,
            passed=passed,
            reason=reason,
        )

    def promote(self, candidate: Path, target: Path, evidence: Evidence) -> None:
        if not evidence.passed:
            raise ValueError("promotion denied: evidence does not prove improvement")
        target.parent.mkdir(parents=True, exist_ok=True)
        if target.exists():
            backup = self.rollback_dir / f"{target.name}.{evidence.candidate_sha256[:12]}.rollback"
            shutil.copy2(target, backup)
        shutil.copy2(candidate, target)
        self.ledger.record(evidence)
