from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from .benchmark import Benchmark
from .evidence import EvidenceLedger
from .memory import Memory
from .model import OllamaModel
from .promotion import PromotionGate
from .tool_builder import ToolBuilder
from .tools import ToolBox

@dataclass(frozen=True)
class OrganismIdentity:
    name: str
    version: str
    architecture: str

class SelfEvolvingAI:
    """The complete AI organism.

    The model is a reasoning substrate inside this object. Identity, memory,
    tools, workspace, evaluation, evidence, and controlled change are all
    part of the same persistent runtime.
    """

    def __init__(self, root: Path | None = None, model: OllamaModel | None = None):
        self.root = (root or Path.home() / ".self-evolving-ai").resolve()
        self.root.mkdir(parents=True, exist_ok=True)

        self.identity = OrganismIdentity(
            name="Self-Evolving AI",
            version="0.4.0",
            architecture="model + memory + tools + workspace + evaluation + evolution",
        )
        self.model = model or OllamaModel()
        self.memory = Memory(self.root)
        self.workspace = self.root / "workspace"
        self.tools = ToolBox(self.workspace)
        self.tool_builder = ToolBuilder(self.workspace)
        self.evidence = EvidenceLedger(self.root)
        self.promotion = PromotionGate(self.root)

    def remember(self, kind: str, content: str) -> None:
        self.memory.remember(kind, content)

    def think(self, prompt: str) -> str:
        return self.model.generate(prompt).strip()

    def observe(self) -> dict:
        return {
            "identity": self.identity.__dict__,
            "model": self.model.model,
            "root": str(self.root),
            "memory_entries": len(self.memory.read()),
            "generated_tools": self.tool_builder.list_candidates(),
            "recent_evidence": self.evidence.recent(5),
        }

    def capability_benchmark(self, name: str, run, minimum: float = 1.0) -> Benchmark:
        return Benchmark(name=name, run=run, minimum=minimum)
