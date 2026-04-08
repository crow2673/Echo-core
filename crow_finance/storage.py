import json
from pathlib import Path
from typing import Any, Dict

class LocalStore:
    def __init__(self, data_dir: Path):
        self.data_dir = data_dir
        self.tokens_path = data_dir / "tokens.json"
        self.snapshot_path = data_dir / "snapshot.json"

    def has_item(self) -> bool:
        data = self.read_tokens()
        return bool(data.get("access_token"))

    def read_tokens(self) -> Dict[str, Any]:
        if not self.tokens_path.exists():
            return {}
        return json.loads(self.tokens_path.read_text())

    def write_tokens(self, payload: Dict[str, Any]) -> None:
        self.tokens_path.write_text(json.dumps(payload, indent=2))

    def read_snapshot(self) -> Dict[str, Any]:
        if not self.snapshot_path.exists():
            return {"accounts": [], "transactions": [], "meta": {}}
        return json.loads(self.snapshot_path.read_text())

    def write_snapshot(self, payload: Dict[str, Any]) -> None:
        self.snapshot_path.write_text(json.dumps(payload, indent=2))
