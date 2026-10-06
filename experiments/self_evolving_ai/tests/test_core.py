from pathlib import Path

from self_ai.memory import Memory
from self_ai.self_improve import ImprovementEngine
from self_ai.tool_builder import ToolBuilder


def test_memory_round_trip(tmp_path: Path):
    memory = Memory(tmp_path)
    memory.remember("test", "hello")
    assert memory.recent(1)[0]["content"] == "hello"


def test_improvement_proposal(tmp_path: Path):
    proposal = ImprovementEngine(tmp_path).propose("memory is too limited")
    assert proposal.observation == "memory is too limited"
    assert proposal.change


def test_tool_builder_syntax_checks(tmp_path: Path):
    builder = ToolBuilder(tmp_path)
    path = builder.create_candidate(
        "calculator",
        "def calculate(a, b):\n    return a + b\n",
    )
    assert path.exists()
    assert "calculator.py" in builder.list_candidates()
