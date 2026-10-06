from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from .benchmark import BenchmarkResult, compare
from .candidate_runner import CandidateRun, run_candidate
from .evolution_journal import EvolutionJournal, EvolutionRecord
from .evidence import EvidenceLedger
from .promotion import PromotionGate
from .safety import inspect_candidate


@dataclass(frozen=True)
class Measurement:
    baseline: BenchmarkResult
    candidate: BenchmarkResult
    promoted: bool
    reason: str
    candidate_sha256: str


class MeasuredEvolution:
    """Turn a built candidate into a measured, reversible evolution decision."""

    def __init__(self, root: Path):
        self.root = root.resolve()
        self.promotion = PromotionGate(self.root)
        self.journal = EvolutionJournal(self.root)

    @staticmethod
    def _score(candidate: Path, cases: list[object], expected: list[float]) -> BenchmarkResult:
        scores: list[float] = []
        for payload, target in zip(cases, expected):
            result: CandidateRun = run_candidate(candidate, payload)
            if not result.ok or result.value is None:
                return BenchmarkResult(0.0, False, result.error or "candidate failed")
            scores.append(1.0 if abs(result.value - float(target)) < 1e-9 else 0.0)
        score = sum(scores) / len(scores) if scores else 0.0
        return BenchmarkResult(score, score == 1.0, f"{sum(scores):.0f}/{len(scores)} cases correct")

    def evaluate_and_promote(self, candidate: Path, target: Path, baseline: Path, cases: list[object], expected: list[float]) -> Measurement:
        inspect_candidate(candidate.read_text(encoding="utf-8"))
        baseline_result = self._score(baseline, cases, expected)
        candidate_result = self._score(candidate, cases, expected)
        passed, reason = compare(baseline_result, candidate_result)

        evidence = self.promotion.evaluate(candidate, baseline_result, candidate_result)
        if passed:
            self.promotion.promote(candidate, target, evidence)
        else:
            self.promotion.ledger.record(evidence)

        sha = EvidenceLedger.sha256(candidate)
        self.journal.record(EvolutionRecord(
            candidate=str(candidate),
            baseline_score=baseline_result.score,
            candidate_score=candidate_result.score,
            promoted=passed,
            reason=reason,
            candidate_sha256=sha,
        ))
        return Measurement(baseline_result, candidate_result, passed, reason, sha)
