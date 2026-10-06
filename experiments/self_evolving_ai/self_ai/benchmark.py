from __future__ import annotations

from dataclasses import dataclass
from typing import Callable


@dataclass(frozen=True)
class BenchmarkResult:
    score: float
    passed: bool
    details: str


class Benchmark:
    """Small deterministic benchmark interface.

    Each capability supplies a callable that returns a numeric score. This
    keeps 'better' measurable and lets future evolution add domain-specific
    tests without changing the promotion protocol.
    """

    def __init__(self, name: str, run: Callable[[], float], minimum: float = 1.0):
        self.name = name
        self.run = run
        self.minimum = minimum

    def execute(self) -> BenchmarkResult:
        score = float(self.run())
        return BenchmarkResult(
            score=score,
            passed=score >= self.minimum,
            details=f"{self.name}: score={score:.3f}, minimum={self.minimum:.3f}",
        )


def compare(baseline: BenchmarkResult, candidate: BenchmarkResult) -> tuple[bool, str]:
    if not candidate.passed:
        return False, "candidate failed its minimum benchmark"
    if candidate.score <= baseline.score:
        return False, "candidate did not beat the baseline"
    return True, f"candidate improved score from {baseline.score:.3f} to {candidate.score:.3f}"
