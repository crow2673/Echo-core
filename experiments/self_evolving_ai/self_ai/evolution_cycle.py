from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from .evidence import EvidenceLedger
from .measured_evolution import Measurement, MeasuredEvolution
from .memory import Memory
from .model import OllamaModel
from .tool_builder import ToolBuilder


@dataclass(frozen=True)
class EvolutionSpec:
    """A measurable capability experiment."""
    name: str
    baseline: Path
    target: Path
    cases: list[object]
    expected: list[float]


class SelfEvolutionCycle:
    """Canonical evolution controller.

    The model proposes the candidate. MeasuredEvolution is the only authority
    that decides whether the candidate is allowed to replace the target.
    """

    def __init__(self, root: Path, model: OllamaModel | None = None):
        self.root = root.resolve()
        self.root.mkdir(parents=True, exist_ok=True)
        self.memory = Memory(self.root)
        self.model = model or OllamaModel()
        self.builder = ToolBuilder(self.root / "workspace")
        self.measured = MeasuredEvolution(self.root)

    def _ask(self, prompt: str) -> str:
        return self.model.generate(prompt).strip()

    def run(self, spec: EvolutionSpec) -> Measurement:
        if len(spec.cases) != len(spec.expected) or not spec.cases:
            raise ValueError("evolution spec must contain matching, non-empty cases and expected values")
        if not spec.baseline.is_file():
            raise FileNotFoundError(f"baseline does not exist: {spec.baseline}")

        observation = self._ask(
            f"""We are testing capability: {spec.name}.
The current baseline is the known implementation.

Identify one concrete limitation in the baseline that can be tested using
only the supplied benchmark cases. Do not invent a new metric."""
        )

        hypothesis = self._ask(
            f"""Capability: {spec.name}
Limitation: {observation}

State one falsifiable hypothesis for a small implementation change that could
improve the existing benchmark score."""
        )

        candidate_source = self._ask(
            f"""Create the smallest Python candidate implementation for capability
{spec.name}.

Limitation: {observation}
Hypothesis: {hypothesis}

The file MUST define:
    def evaluate(payload) -> float

It must return a numeric answer for a JSON-serializable payload.
Do not use imports, network access, subprocesses, dynamic execution,
filesystem access, or arbitrary host access.
Output ONLY Python source code."""
        )

        candidate = self.builder.create_candidate(
            f"{spec.name.replace(' ', '_').lower()}_candidate",
            candidate_source,
        )

        measurement = self.measured.evaluate_and_promote(
            candidate=candidate,
            target=spec.target,
            baseline=spec.baseline,
            cases=spec.cases,
            expected=spec.expected,
        )

        self.memory.remember(
            "evolution",
            (
                f"{spec.name}: baseline={measurement.baseline.score:.3f}, "
                f"candidate={measurement.candidate.score:.3f}, "
                f"promoted={measurement.promoted}, reason={measurement.reason}, "
                f"candidate_sha256={measurement.candidate_sha256}"
            ),
        )
        return measurement


__all__ = ["EvolutionSpec", "SelfEvolutionCycle"]
