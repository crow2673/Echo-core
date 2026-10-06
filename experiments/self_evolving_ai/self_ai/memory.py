from __future__ import annotations

import json
from pathlib import Path


class Memory:
    def __init__(self, root: Path):
        self.path = root / "memory.json"
        self.path.parent.mkdir(parents=True, exist_ok=True)
        if not self.path.exists():
            self.path.write_text("[]", encoding="utf-8")

    def read(self) -> list[dict]:
        return json.loads(self.path.read_text(encoding="utf-8"))

    def remember(self, kind: str, content: str) -> None:
        data = self.read()
        data.append({"kind": kind, "content": content})
        self.path.write_text(json.dumps(data, indent=2), encoding="utf-8")

    def recent(self, limit: int = 20) -> list[dict]:
        return self.read()[-limit:]
