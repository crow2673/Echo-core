from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from pathlib import Path


@dataclass
class Evidence:
    candidate: str
    candidate_sha256: str
    baseline_score: float
    candidate_score: float
    passed: bool
    reason: str


class EvidenceLedger:
    """Persistent evidence for self-modification decisions.

    A candidate is not an improvement merely because it compiles or because
    the model says it is better. Promotion requires an objective score that
    beats the baseline.
    """

    def __init__(self, root: Path):
        self.path = root / "evidence.json"
        self.path.parent.mkdir(parents=True, exist_ok=True)
        if not self.path.exists():
            self.path.write_text("[]", encoding="utf-8")

    @staticmethod
    def sha256(path: Path) -> str:
        return hashlib.sha256(path.read_bytes()).hexdigest()

    def record(self, evidence: Evidence) -> None:
        rows = json.loads(self.path.read_text(encoding="utf-8"))
        rows.append(asdict(evidence))
        self.path.write_text(json.dumps(rows, indent=2), encoding="utf-8")

    def recent(self, limit: int = 20) -> list[dict]:
        return json.loads(self.path.read_text(encoding="utf-8"))[-limit:]
