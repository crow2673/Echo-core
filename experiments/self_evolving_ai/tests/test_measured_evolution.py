from pathlib import Path

from self_ai.candidate_runner import run_candidate
from self_ai.evolution_journal import EvolutionJournal, EvolutionRecord
from self_ai.measured_evolution import MeasuredEvolution


def write_tool(path: Path, body: str) -> None:
    path.write_text(body, encoding="utf-8")


def test_candidate_runner_executes_contract(tmp_path: Path):
    candidate = tmp_path / "candidate.py"
    write_tool(candidate, "def evaluate(payload):\n    return len(payload)\n")
    result = run_candidate(candidate, "hello")
    assert result.ok
    assert result.value == 5.0


def test_measured_evolution_rejects_non_improvement(tmp_path: Path):
    baseline = tmp_path / "baseline.py"
    candidate = tmp_path / "candidate.py"
    target = tmp_path / "target.py"

    write_tool(baseline, "def evaluate(payload):\n    return len(payload)\n")
    write_tool(candidate, "def evaluate(payload):\n    return 0\n")

    measured = MeasuredEvolution(tmp_path / "state")
    result = measured.evaluate_and_promote(
        candidate,
        target,
        baseline,
        ["a", "bb"],
        [1, 2],
    )

    assert not result.promoted
    assert not target.exists()


def test_journal_records_lineage(tmp_path: Path):
    journal = EvolutionJournal(tmp_path)
    journal.record(
        EvolutionRecord(
            candidate="candidate.py",
            baseline_score=0.5,
            candidate_score=1.0,
            promoted=True,
            reason="candidate improved",
            candidate_sha256="abc",
        )
    )
    assert journal.recent(1)[0]["promoted"] is True
