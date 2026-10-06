from __future__ import annotations

import json
import subprocess
import sys
from dataclasses import asdict, dataclass
from pathlib import Path

from .evidence import EvidenceLedger
from .memory import Memory
from .model import OllamaModel
from .tool_builder import ToolBuilder


@dataclass
class CycleResult:
    observation: str
    hypothesis: str
    action: str
    test_result: str
    decision: str
    candidate_sha256: str | None = None


class SelfEvolutionCycle:
    """Observe -> hypothesize -> build -> safety-check -> test -> decide -> remember."""

    def __init__(self, root: Path, model: OllamaModel):
        self.root = root
        self.memory = Memory(root)
        self.builder = ToolBuilder(root / "workspace")
        self.evidence = EvidenceLedger(root)
        self.model = model
        self.workspace = (root / "workspace").resolve()

    def _ask(self, prompt: str) -> str:
        return self.model.generate(prompt).strip()

    def run(self) -> CycleResult:
        observation = self._ask(
            """Identify ONE missing capability that would materially improve this
persistent AI. Do not pick a cosmetic feature. Return one concise limitation."""
        )

        hypothesis = self._ask(
            f"""Current limitation:
{observation}

Form one falsifiable hypothesis about a small architectural change that could
improve it. Prefer something measurable locally."""
        )

        action = self._ask(
            f"""Limitation:
{observation}

Hypothesis:
{hypothesis}

Design the smallest candidate change that tests the hypothesis. State exactly
what should be built and what measurable result would count as success."""
        )

        candidate_source = self._ask(
            f"""Create a minimal Python candidate tool for this experiment.

Limitation: {observation}
Hypothesis: {hypothesis}
Proposed change: {action}

Output ONLY Python source. It must define at least one function. It must not
use network access, subprocesses, dynamic execution, filesystem deletion, or
arbitrary host access. The source must be safe to statically inspect."""
        )

        candidate_sha = None
        try:
            path = self.builder.create_candidate("evolution_candidate", candidate_source)
            candidate_sha = self.evidence.sha256(path)
            result = subprocess.run(
                [sys.executable, "-m", "py_compile", str(path)],
                capture_output=True,
                text=True,
                timeout=30,
                cwd=self.workspace,
            )
            test_result = (result.stdout + result.stderr).strip() or "syntax and safety checks passed"
            passed = result.returncode == 0
        except Exception as exc:
            test_result = f"candidate rejected: {exc}"
            passed = False

        decision = self._ask(
            f"""Evaluate this self-improvement attempt.

Limitation: {observation}
Hypothesis: {hypothesis}
Action: {action}
Candidate checks: {test_result}

Answer:
DECISION: KEEP_CANDIDATE or REJECT
REASON: one sentence

Important: passing syntax/static checks does NOT prove improvement. A real
promotion requires a measurable benchmark beating the baseline."""
        )

        final = "KEEP_CANDIDATE" if passed and "KEEP_CANDIDATE" in decision else "REJECT"
        cycle = CycleResult(
            observation, hypothesis, action, test_result, final, candidate_sha
        )
        self.memory.remember("evolution_cycle", json.dumps(asdict(cycle), indent=2))
        return cycle
