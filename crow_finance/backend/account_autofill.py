import json
import os
from pathlib import Path
from typing import Any, Dict, List


DATA_DIR = Path(os.getenv("CROW_DATA_DIR", "./data"))
SNAPSHOT_PATH = DATA_DIR / "snapshot.json"
REGISTRY_PATH = DATA_DIR / "accounts_registry.json"
HISTORY_PATH = DATA_DIR / "account_history.jsonl"


def _read_json(path: Path, default):
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text())
    except Exception:
        return default


def _write_json(path: Path, payload):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2))


def _read_history() -> List[Dict[str, Any]]:
    if not HISTORY_PATH.exists():
        return []
    rows = []
    for line in HISTORY_PATH.read_text().splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            rows.append(json.loads(line))
        except Exception:
            continue
    return rows


def _append_history(row: Dict[str, Any]):
    HISTORY_PATH.parent.mkdir(parents=True, exist_ok=True)
    with HISTORY_PATH.open("a") as f:
        f.write(json.dumps(row) + "\n")


def materialize_from_snapshot() -> Dict[str, Any]:
    snapshot = _read_json(SNAPSHOT_PATH, {})
    accounts = snapshot.get("accounts", []) or []
    meta = snapshot.get("meta", {}) or {}
    timestamp = meta.get("last_sync") or "unknown"

    registry = _read_json(REGISTRY_PATH, [])
    by_id = {a.get("account_id"): a for a in registry if a.get("account_id")}

    normalized_accounts = []
    for acct in accounts:
        account_id = acct.get("account_id")
        if not account_id:
            continue

        balance = acct.get("available_balance")
        if balance is None:
            balance = acct.get("current_balance")
        if balance is None:
            balance = 0

        normalized = {
            "account_id": account_id,
            "name": acct.get("name") or acct.get("official_name") or "Unnamed Account",
            "official_name": acct.get("official_name"),
            "type": acct.get("type"),
            "subtype": acct.get("subtype"),
            "mask": acct.get("mask"),
            "balance": round(float(balance), 2),
            "currency": acct.get("iso_currency_code") or "USD",
        }
        by_id[account_id] = normalized
        normalized_accounts.append(normalized)

    merged = sorted(by_id.values(), key=lambda x: (x.get("type") or "", x.get("name") or ""))
    _write_json(REGISTRY_PATH, merged)

    history = _read_history()
    if not history or history[-1].get("timestamp") != timestamp:
        history_row = {
            "timestamp": timestamp,
            "accounts": [
                {
                    "account_id": a["account_id"],
                    "name": a["name"],
                    "type": a.get("type"),
                    "subtype": a.get("subtype"),
                    "balance": a["balance"],
                }
                for a in normalized_accounts
            ],
        }
        _append_history(history_row)

    return {
        "ok": True,
        "timestamp": timestamp,
        "accounts_detected": len(normalized_accounts),
        "registry_size": len(merged),
    }


def build_series_payload() -> Dict[str, Any]:
    registry = _read_json(REGISTRY_PATH, [])
    history = _read_history()

    series_map = {}
    labels = []

    for row in history:
        ts = row.get("timestamp", "unknown")
        labels.append(ts)
        account_lookup = {a.get("account_id"): a for a in row.get("accounts", [])}

        for acct in registry:
            aid = acct.get("account_id")
            if aid not in series_map:
                series_map[aid] = {
                    "account_id": aid,
                    "label": acct.get("name") or "Unnamed Account",
                    "type": acct.get("type"),
                    "subtype": acct.get("subtype"),
                    "points": [],
                }

            bal = None
            if aid in account_lookup:
                bal = account_lookup[aid].get("balance")
            series_map[aid]["points"].append(bal)

    return {
        "ok": True,
        "labels": labels,
        "accounts": registry,
        "series": list(series_map.values()),
    }
