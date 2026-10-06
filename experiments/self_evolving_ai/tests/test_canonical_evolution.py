from pathlib import Path

from self_ai.evolution_cycle import EvolutionSpec, SelfEvolutionCycle


class FakeModel:
    def generate(self, prompt: str) -> str:
        return "def evaluate(payload):\n    return len(payload)\n"


def test_canonical_cycle_promotes_measured_improvement(tmp_path: Path):
    baseline = tmp_path / "baseline.py"
    target = tmp_path / "target.py"
    baseline.write_text("def evaluate(payload):\n    return 0\n", encoding="utf-8")

    cycle = SelfEvolutionCycle(tmp_path / "state", FakeModel())
    result = cycle.run(EvolutionSpec(
        name="payload length",
        baseline=baseline,
        target=target,
        cases=["a", "bb", "ccc"],
        expected=[1, 2, 3],
    ))

    assert result.promoted
    assert target.read_text(encoding="utf-8").startswith("def evaluate")
    assert result.candidate.score > result.baseline.score
