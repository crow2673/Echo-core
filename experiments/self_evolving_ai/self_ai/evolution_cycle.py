from __future__ import annotations

import json
import subprocess
import sys
from dataclasses import asdict, dataclass
from pathlib import Path

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


class SelfEvolutionCycle:
    """One complete observe -> hypothesize -> build -> test -> decide cycle.

    v0.2 still requires promotion to be explicit. The important experiment is
    that the AI itself can reason about a missing capability and produce a
    tested candidate rather than merely answering a request.
    """

    def __init__(self, root: Path, model: OllamaModel):
        self.root = root
        self.memory = Memory(root)
        self.builder = ToolBuilder(root / "workspace")
        self.model = model
        self.workspace = (root / "workspace").resolve()

    def _ask(self, prompt: str) -> str:
        return self.model.generate(prompt).strip()

    def run(self) -> CycleResult:
        observation = self._ask(
            """Inspect this self-model conceptually. Identify ONE capability
that is currently missing from this runtime and would most improve its
ability to operate as a persistent AI. Do not pick a cosmetic feature.
Return one concise limitation."""
        )

        hypothesis = self._ask(
            f"""We observed this limitation in our current AI:
{observation}

Form one falsifiable hypothesis about a small architectural change that
could improve this limitation. Prefer something we can test locally."""
        )

        action = self._ask(
            f"""Limitation:
{observation}

Hypothesis:
{hypothesis}

Design the smallest candidate change that would test the hypothesis.
Describe exactly what should be built and what success would mean."""
        )

        # The AI must produce a candidate artifact, but we don't blindly
        # execute arbitrary generated code. The candidate is syntax-checked.
        candidate_source = self._ask(
            f"""Create a minimal Python candidate tool that tests this idea.

Limitation: {observation}
Hypothesis: {hypothesis}
Proposed change: {action}

Output ONLY Python source. It must define at least one function, have no
network access, no subprocess calls, no filesystem deletion, and be safe to
syntax-check without executing it."""
        )

        try:
            path = self.builder.create_candidate("evolution_candidate", candidate_source)
            result = subprocess.run(
                [sys.executable, "-m", "py_compile", str(path)],
                capture_output=True,
                text=True,
                timeout=30,
                cwd=self.workspace,
            )
            test_result = (result.stdout + result.stderr).strip() or "syntax check passed"
            passed = result.returncode == 0
        except Exception as exc:
            test_result = f"candidate rejected: {exc}"
            passed = False

        decision = self._ask(
            f"""Evaluate this self-improvement attempt.

Limitation: {observation}
Hypothesis: {hypothesis}
Action: {action}
Candidate test result: {test_result}

Should this candidate be considered an improvement? Answer with:
DECISION: KEEP_CANDIDATE or REJECT
REASON: one sentence

A syntax pass alone does not prove capability improvement."""
        )

        final = "KEEP_CANDIDATE" if passed and "KEEP_CANDIDATE" in decision else "REJECT"
        cycle = CycleResult(observation, hypothesis, action, test_result, final)
        self.memory.remember("evolution_cycle", json.dumps(asdict(cycle), indent=2))
        return cycle
