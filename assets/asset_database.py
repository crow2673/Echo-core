#!/usr/bin/env python3
"""SQLite storage for Echo Asset System v1."""
from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any

BASE = Path.home() / "Echo"
DB_PATH = BASE / "database/assets.db"


def _json(data: Any) -> str:
    return json.dumps(data or {}, sort_keys=True, default=str)


class AssetDatabase:
    def __init__(self, path: Path = DB_PATH):
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._init()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self.path), timeout=15)
        conn.row_factory = sqlite3.Row
        return conn

    def _init(self) -> None:
        with self._connect() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS assets (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    asset_id TEXT NOT NULL UNIQUE,
                    name TEXT NOT NULL,
                    type TEXT NOT NULL,
                    manufacturer TEXT,
                    model TEXT,
                    serial TEXT,
                    status TEXT NOT NULL DEFAULT 'active',
                    created TEXT NOT NULL,
                    metadata TEXT NOT NULL DEFAULT '{}'
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS observations (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    asset_id TEXT NOT NULL,
                    timestamp TEXT NOT NULL,
                    source TEXT NOT NULL,
                    summary TEXT NOT NULL,
                    raw_text TEXT,
                    confidence REAL NOT NULL DEFAULT 1.0,
                    tags TEXT NOT NULL DEFAULT '[]',
                    payload TEXT NOT NULL DEFAULT '{}',
                    FOREIGN KEY(asset_id) REFERENCES assets(asset_id)
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS observation_revisions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    observation_id INTEGER NOT NULL,
                    changed_at TEXT NOT NULL,
                    actor TEXT NOT NULL,
                    reason TEXT NOT NULL,
                    changed_fields TEXT NOT NULL DEFAULT '[]',
                    original_payload TEXT NOT NULL DEFAULT '{}',
                    updated_payload TEXT NOT NULL DEFAULT '{}',
                    metadata TEXT NOT NULL DEFAULT '{}',
                    FOREIGN KEY(observation_id) REFERENCES observations(id)
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS maintenance (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    asset_id TEXT NOT NULL,
                    date TEXT NOT NULL,
                    task TEXT NOT NULL,
                    completed INTEGER NOT NULL DEFAULT 0,
                    notes TEXT,
                    mileage REAL,
                    hours REAL,
                    FOREIGN KEY(asset_id) REFERENCES assets(asset_id)
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS parts (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    asset_id TEXT NOT NULL,
                    part_name TEXT NOT NULL,
                    part_number TEXT,
                    manufacturer TEXT,
                    qty REAL NOT NULL DEFAULT 1,
                    location TEXT,
                    installed INTEGER NOT NULL DEFAULT 0,
                    notes TEXT,
                    FOREIGN KEY(asset_id) REFERENCES assets(asset_id)
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS telemetry (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    asset_id TEXT NOT NULL,
                    timestamp TEXT NOT NULL,
                    sensor TEXT NOT NULL,
                    value REAL NOT NULL,
                    units TEXT,
                    FOREIGN KEY(asset_id) REFERENCES assets(asset_id)
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS tasks (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    asset_id TEXT NOT NULL,
                    priority TEXT NOT NULL,
                    task TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'OPEN',
                    created TEXT NOT NULL,
                    completed TEXT,
                    metadata TEXT NOT NULL DEFAULT '{}',
                    FOREIGN KEY(asset_id) REFERENCES assets(asset_id)
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS task_proposals (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    proposal_id TEXT NOT NULL UNIQUE,
                    asset_id TEXT NOT NULL,
                    source_observation_id INTEGER NOT NULL,
                    proposed_title TEXT NOT NULL,
                    proposed_description TEXT NOT NULL,
                    proposed_task_type TEXT NOT NULL,
                    priority TEXT NOT NULL,
                    evidence_summary TEXT NOT NULL,
                    facts_used TEXT NOT NULL DEFAULT '{}',
                    inferences_used TEXT NOT NULL DEFAULT '{}',
                    confidence REAL NOT NULL DEFAULT 1.0,
                    uncertainty TEXT NOT NULL DEFAULT '[]',
                    suggested_due_window TEXT,
                    safety_notes TEXT NOT NULL DEFAULT '[]',
                    created_at TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'pending_review',
                    reviewer TEXT,
                    reviewed_at TEXT,
                    review_notes TEXT,
                    resulting_task_id INTEGER,
                    source_fingerprint TEXT NOT NULL,
                    metadata TEXT NOT NULL DEFAULT '{}',
                    FOREIGN KEY(asset_id) REFERENCES assets(asset_id),
                    FOREIGN KEY(source_observation_id) REFERENCES observations(id)
                )
            """)
            self._ensure_column(conn, "tasks", "metadata", "TEXT NOT NULL DEFAULT '{}'")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_assets_asset_id ON assets(asset_id)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_assets_type ON assets(type)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_observations_asset ON observations(asset_id)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_observations_timestamp ON observations(timestamp)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_observation_revisions_observation ON observation_revisions(observation_id)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_telemetry_asset_sensor ON telemetry(asset_id, sensor)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_tasks_asset_status ON tasks(asset_id, status)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_task_proposals_asset_status ON task_proposals(asset_id, status)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_task_proposals_source ON task_proposals(source_observation_id)")

    @staticmethod
    def _ensure_column(conn: sqlite3.Connection, table: str, column: str, definition: str) -> None:
        cols = {row["name"] for row in conn.execute(f"PRAGMA table_info({table})").fetchall()}
        if column not in cols:
            conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")

    def upsert_asset(
        self,
        *,
        asset_id: str,
        name: str,
        type: str,
        manufacturer: str = "",
        model: str = "",
        serial: str = "",
        status: str = "active",
        created: str,
        metadata: dict[str, Any] | None = None,
    ) -> str:
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO assets
                    (asset_id, name, type, manufacturer, model, serial, status, created, metadata)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(asset_id) DO UPDATE SET
                    name=excluded.name,
                    type=excluded.type,
                    manufacturer=excluded.manufacturer,
                    model=excluded.model,
                    serial=excluded.serial,
                    status=excluded.status,
                    metadata=excluded.metadata
                """,
                (
                    asset_id, name, type, manufacturer, model, serial, status,
                    created, _json(metadata),
                ),
            )
        return asset_id

    def get_asset(self, asset_id: str) -> dict[str, Any] | None:
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM assets WHERE asset_id=? LIMIT 1", (asset_id,)).fetchone()
        return self._row_to_dict(row) if row else None

    def list_assets(self) -> list[dict[str, Any]]:
        with self._connect() as conn:
            rows = conn.execute("SELECT * FROM assets ORDER BY asset_id").fetchall()
        return [self._row_to_dict(row) for row in rows]

    def insert_observation(
        self,
        *,
        asset_id: str,
        timestamp: str,
        source: str,
        summary: str,
        raw_text: str = "",
        confidence: float = 1.0,
        tags: list[str] | None = None,
        payload: dict[str, Any] | None = None,
    ) -> int:
        with self._connect() as conn:
            cur = conn.execute(
                """
                INSERT INTO observations
                    (asset_id, timestamp, source, summary, raw_text, confidence, tags, payload)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    asset_id, timestamp, source, summary[:1000], raw_text,
                    float(confidence), json.dumps(tags or []), _json(payload),
                ),
            )
            return int(cur.lastrowid)

    def add_task(self, *, asset_id: str, priority: str, task: str, status: str,
                 created: str, completed: str | None = None,
                 metadata: dict[str, Any] | None = None) -> int:
        with self._connect() as conn:
            cur = conn.execute(
                """
                INSERT INTO tasks (asset_id, priority, task, status, created, completed, metadata)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (asset_id, priority, task, status, created, completed, _json(metadata)),
            )
            return int(cur.lastrowid)

    def get_observation(self, observation_id: int) -> dict[str, Any] | None:
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM observations WHERE id=? LIMIT 1", (int(observation_id),)).fetchone()
        return self._row_to_dict(row) if row else None

    def update_observation_payload(
        self,
        observation_id: int,
        payload: dict[str, Any],
        *,
        actor: str | None = None,
        reason: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> int:
        """Update an observation payload with append-only revision tracking.

        Reviewed observations are not allowed to mutate silently. Any caller
        changing a reviewed observation must provide both actor and reason.
        """
        from datetime import datetime

        observation_id = int(observation_id)
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM observations WHERE id=? LIMIT 1", (observation_id,)).fetchone()
            if not row:
                raise RuntimeError(f"observation not found: {observation_id}")
            original = self._row_to_dict(row).get("payload") or {}
            reviewed = (
                original.get("review_status") == "reviewed"
                or (original.get("provenance") or {}).get("review_status") == "reviewed"
            )
            if reviewed and (not actor or not reason):
                raise RuntimeError("reviewed observations require actor and reason for payload revisions")
            actor = actor or "unknown"
            reason = reason or "unspecified payload update"
            changed_fields = _changed_payload_fields(original, payload)
            cur = conn.execute(
                """
                INSERT INTO observation_revisions (
                    observation_id, changed_at, actor, reason, changed_fields,
                    original_payload, updated_payload, metadata
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    observation_id,
                    datetime.now().isoformat(),
                    actor,
                    reason,
                    json.dumps(changed_fields),
                    _json(original),
                    _json(payload),
                    _json(metadata),
                ),
            )
            conn.execute("UPDATE observations SET payload=? WHERE id=?", (_json(payload), observation_id))
            return int(cur.lastrowid)

    def add_observation_revision(
        self,
        observation_id: int,
        *,
        original_payload: dict[str, Any],
        updated_payload: dict[str, Any],
        actor: str,
        reason: str,
        metadata: dict[str, Any] | None = None,
    ) -> int:
        from datetime import datetime

        changed_fields = _changed_payload_fields(original_payload, updated_payload)
        with self._connect() as conn:
            cur = conn.execute(
                """
                INSERT INTO observation_revisions (
                    observation_id, changed_at, actor, reason, changed_fields,
                    original_payload, updated_payload, metadata
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    int(observation_id),
                    datetime.now().isoformat(),
                    actor,
                    reason,
                    json.dumps(changed_fields),
                    _json(original_payload),
                    _json(updated_payload),
                    _json(metadata),
                ),
            )
            return int(cur.lastrowid)

    def list_observation_revisions(self, observation_id: int) -> list[dict[str, Any]]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM observation_revisions WHERE observation_id=? ORDER BY id",
                (int(observation_id),),
            ).fetchall()
        return [self._row_to_dict(row) for row in rows]

    def add_task_proposal(self, proposal: dict[str, Any]) -> int:
        with self._connect() as conn:
            cur = conn.execute(
                """
                INSERT INTO task_proposals (
                    proposal_id, asset_id, source_observation_id, proposed_title,
                    proposed_description, proposed_task_type, priority, evidence_summary,
                    facts_used, inferences_used, confidence, uncertainty,
                    suggested_due_window, safety_notes, created_at, status, reviewer,
                    reviewed_at, review_notes, resulting_task_id, source_fingerprint, metadata
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    proposal["proposal_id"],
                    proposal["asset_id"],
                    int(proposal["source_observation_id"]),
                    proposal["proposed_title"],
                    proposal["proposed_description"],
                    proposal["proposed_task_type"],
                    proposal["priority"],
                    proposal["evidence_summary"],
                    _json(proposal.get("facts_used")),
                    _json(proposal.get("inferences_used")),
                    float(proposal.get("confidence", 1.0)),
                    json.dumps(proposal.get("uncertainty") or []),
                    proposal.get("suggested_due_window"),
                    json.dumps(proposal.get("safety_notes") or []),
                    proposal["created_at"],
                    proposal.get("status", "pending_review"),
                    proposal.get("reviewer"),
                    proposal.get("reviewed_at"),
                    proposal.get("review_notes"),
                    proposal.get("resulting_task_id"),
                    proposal["source_fingerprint"],
                    _json(proposal.get("metadata")),
                ),
            )
            return int(cur.lastrowid)

    def get_task_proposal(self, proposal_id: str) -> dict[str, Any] | None:
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM task_proposals WHERE proposal_id=? LIMIT 1", (proposal_id,)).fetchone()
        return self._row_to_dict(row) if row else None

    def list_task_proposals(self, asset_id: str | None = None) -> list[dict[str, Any]]:
        with self._connect() as conn:
            if asset_id:
                rows = conn.execute(
                    "SELECT * FROM task_proposals WHERE asset_id=? ORDER BY created_at DESC, id DESC",
                    (asset_id,),
                ).fetchall()
            else:
                rows = conn.execute("SELECT * FROM task_proposals ORDER BY created_at DESC, id DESC").fetchall()
        return [self._row_to_dict(row) for row in rows]

    def update_task_proposal(self, proposal_id: str, **fields: Any) -> None:
        if not fields:
            return
        json_fields = {"facts_used", "inferences_used", "metadata"}
        list_fields = {"uncertainty", "safety_notes"}
        assignments = []
        values = []
        for key, value in fields.items():
            assignments.append(f"{key}=?")
            if key in json_fields:
                values.append(_json(value))
            elif key in list_fields:
                values.append(json.dumps(value or []))
            else:
                values.append(value)
        values.append(proposal_id)
        with self._connect() as conn:
            conn.execute(f"UPDATE task_proposals SET {', '.join(assignments)} WHERE proposal_id=?", values)

    def get_task(self, task_id: int) -> dict[str, Any] | None:
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM tasks WHERE id=? LIMIT 1", (int(task_id),)).fetchone()
        return self._row_to_dict(row) if row else None

    def update_task_metadata(self, task_id: int, metadata: dict[str, Any]) -> None:
        with self._connect() as conn:
            conn.execute("UPDATE tasks SET metadata=? WHERE id=?", (_json(metadata), int(task_id)))

    def add_maintenance(self, *, asset_id: str, date: str, task: str,
                        completed: bool = False, notes: str = "",
                        mileage: float | None = None, hours: float | None = None) -> int:
        with self._connect() as conn:
            cur = conn.execute(
                """
                INSERT INTO maintenance (asset_id, date, task, completed, notes, mileage, hours)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (asset_id, date, task, 1 if completed else 0, notes, mileage, hours),
            )
            return int(cur.lastrowid)

    def add_part(self, *, asset_id: str, part_name: str, part_number: str = "",
                 manufacturer: str = "", qty: float = 1, location: str = "",
                 installed: bool = False, notes: str = "") -> int:
        with self._connect() as conn:
            cur = conn.execute(
                """
                INSERT INTO parts
                    (asset_id, part_name, part_number, manufacturer, qty, location, installed, notes)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (asset_id, part_name, part_number, manufacturer, qty, location, 1 if installed else 0, notes),
            )
            return int(cur.lastrowid)

    def add_telemetry(self, *, asset_id: str, timestamp: str, sensor: str,
                      value: float, units: str = "") -> int:
        with self._connect() as conn:
            cur = conn.execute(
                """
                INSERT INTO telemetry (asset_id, timestamp, sensor, value, units)
                VALUES (?, ?, ?, ?, ?)
                """,
                (asset_id, timestamp, sensor, float(value), units),
            )
            return int(cur.lastrowid)

    def recent_observations(self, limit: int = 20, asset_id: str | None = None) -> list[dict[str, Any]]:
        with self._connect() as conn:
            if asset_id:
                rows = conn.execute(
                    "SELECT * FROM observations WHERE asset_id=? ORDER BY timestamp DESC LIMIT ?",
                    (asset_id, limit),
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT * FROM observations ORDER BY timestamp DESC LIMIT ?",
                    (limit,),
                ).fetchall()
        return [self._row_to_dict(row) for row in rows]

    def open_tasks(self, asset_id: str | None = None) -> list[dict[str, Any]]:
        with self._connect() as conn:
            if asset_id:
                rows = conn.execute(
                    "SELECT * FROM tasks WHERE asset_id=? AND status!='DONE' ORDER BY id DESC",
                    (asset_id,),
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT * FROM tasks WHERE status!='DONE' ORDER BY id DESC"
                ).fetchall()
        return [self._row_to_dict(row) for row in rows]

    def telemetry_recent(self, asset_id: str, limit: int = 50) -> list[dict[str, Any]]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM telemetry WHERE asset_id=? ORDER BY timestamp DESC LIMIT ?",
                (asset_id, limit),
            ).fetchall()
        return [self._row_to_dict(row) for row in rows]

    def asset_summary(self) -> dict[str, Any]:
        with self._connect() as conn:
            assets = conn.execute("SELECT COUNT(*) FROM assets").fetchone()[0]
            observations = conn.execute("SELECT COUNT(*) FROM observations").fetchone()[0]
            tasks = conn.execute("SELECT COUNT(*) FROM tasks WHERE status!='DONE'").fetchone()[0]
            by_type = conn.execute("SELECT type, COUNT(*) FROM assets GROUP BY type").fetchall()
        return {
            "assets": assets,
            "observations": observations,
            "open_tasks": tasks,
            "assets_by_type": {row[0]: row[1] for row in by_type},
        }

    @staticmethod
    def _row_to_dict(row: sqlite3.Row) -> dict[str, Any]:
        item = dict(row)
        for key in ("metadata", "payload", "facts_used", "inferences_used", "original_payload", "updated_payload"):
            if key in item:
                try:
                    item[key] = json.loads(item.get(key) or "{}")
                except json.JSONDecodeError:
                    item[key] = {}
        for key in ("tags", "uncertainty", "safety_notes", "changed_fields"):
            if key not in item:
                continue
            try:
                item[key] = json.loads(item.get(key) or "[]")
            except json.JSONDecodeError:
                item[key] = []
        return item


def _changed_payload_fields(original: dict[str, Any], updated: dict[str, Any]) -> list[str]:
    changed = []
    for key in sorted(set(original or {}) | set(updated or {})):
        if (original or {}).get(key) != (updated or {}).get(key):
            changed.append(key)
    return changed
