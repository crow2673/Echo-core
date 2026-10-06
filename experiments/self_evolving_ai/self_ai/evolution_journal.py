from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path


@dataclass(frozen=True)
class EvolutionRecord:
    candidate: str
    baseline_score: float
    candidate_score: float
    promoted: bool
    reason: str
    candidate_sha256: str


class EvolutionJournal:
    """Append-only human-readable lineage for measured evolution decisions."""

    def __init__(self, root: Path):
        self.path = root / "evolution_journal.json"
        self.path.parent.mkdir(parents=True, exist_ok=True)
        if not self.path.exists():
            self.path.write_text("[]", encoding="utf-8")

    def record(self, entry: EvolutionRecord) -> None:
        data = json.loads(self.path.read_text(encoding="utf-8"))
        data.append(asdict(entry))
        self.path.write_text(json.dumps(data, indent=2), encoding="utf-8")

    def recent(self, limit: int = 20) -> list[dict]:
        return json.loads(self.path.read_text(encoding="utf-8"))[-limit:]
