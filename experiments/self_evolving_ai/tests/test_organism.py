from pathlib import Path

from self_ai.organism import SelfEvolvingAI


def test_organism_is_single_runtime(tmp_path: Path):
    ai = SelfEvolvingAI(root=tmp_path)
    snapshot = ai.observe()
    assert snapshot["identity"]["name"] == "Self-Evolving AI"
    assert snapshot["identity"]["version"] == "0.6.0"
    assert "memory_entries" in snapshot
    assert "generated_tools" in snapshot
    assert hasattr(ai, "evolution")
