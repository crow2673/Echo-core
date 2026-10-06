from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass
class ImprovementProposal:
    observation: str
    hypothesis: str
    change: str
    expected_gain: str


class ImprovementEngine:
    """Turns observed limitations into testable improvement proposals.

    v0.1 deliberately stops before automatic replacement. The candidate
    generation and evaluation boundary comes first.
    """

    def __init__(self, workspace: Path):
        self.workspace = workspace

    def propose(self, observation: str) -> ImprovementProposal:
        return ImprovementProposal(
            observation=observation,
            hypothesis="A targeted architectural change may improve the measured limitation.",
            change="Create an isolated candidate and test it without replacing the current runtime.",
            expected_gain="A measurable improvement on the affected capability without regressions.",
        )
