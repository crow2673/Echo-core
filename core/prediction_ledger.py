#!/usr/bin/env python3
"""Track probabilistic predictions and evaluate them without leakage."""
import json
import sqlite3
import uuid
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

DB_PATH = Path.home() / "Echo/memory/echo_events.db"


def _conn():
    db = sqlite3.connect(str(DB_PATH), timeout=10)
    db.execute("""
        CREATE TABLE IF NOT EXISTS predictions (
            id TEXT PRIMARY KEY,
            claim TEXT NOT NULL,
            probability REAL NOT NULL,
            category TEXT,
            evidence TEXT,
            created_at TEXT NOT NULL,
            outcome INTEGER,
            outcome_evidence TEXT,
            resolved_at TEXT,
            eligible_after TEXT,
            dataset_scope TEXT NOT NULL DEFAULT 'operational',
            source_name TEXT,
            source_id TEXT
        )
    """)
    existing = {row[1] for row in db.execute("PRAGMA table_info(predictions)")}
    if "eligible_after" not in existing:
        db.execute("ALTER TABLE predictions ADD COLUMN eligible_after TEXT")
    if "dataset_scope" not in existing:
        db.execute(
            "ALTER TABLE predictions ADD COLUMN dataset_scope TEXT NOT NULL DEFAULT 'operational'"
        )
    if "source_name" not in existing:
        db.execute("ALTER TABLE predictions ADD COLUMN source_name TEXT")
    if "source_id" not in existing:
        db.execute("ALTER TABLE predictions ADD COLUMN source_id TEXT")
    db.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS predictions_source "
        "ON predictions(dataset_scope, source_name, source_id) "
        "WHERE source_id IS NOT NULL"
    )
    legacy_pending = db.execute(
        "SELECT id, created_at FROM predictions "
        "WHERE resolved_at IS NULL AND eligible_after IS NULL"
    ).fetchall()
    for prediction_id, created_at in legacy_pending:
        try:
            eligible_after = datetime.fromisoformat(created_at) + timedelta(minutes=20)
            db.execute(
                "UPDATE predictions SET eligible_after=? WHERE id=?",
                (eligible_after.isoformat(), prediction_id),
            )
        except Exception:
            pass
    db.commit()
    return db


def record_prediction(
    claim: str,
    probability: float,
    category: str,
    evidence: str = "",
    min_horizon_minutes: int = 20,
    dataset_scope: str = "operational",
) -> str:
    probability = float(probability)
    if not 0.0 <= probability <= 1.0:
        raise ValueError("probability must be between 0 and 1")
    prediction_id = str(uuid.uuid4())[:8]
    created_at = datetime.now()
    eligible_after = created_at + timedelta(minutes=max(1, min_horizon_minutes))
    db = _conn()
    db.execute(
        "INSERT INTO predictions "
        "(id, claim, probability, category, evidence, created_at, eligible_after, dataset_scope) "
        "VALUES (?,?,?,?,?,?,?,?)",
        (
            prediction_id, claim[:500], probability, category[:100], evidence[:1000],
            created_at.isoformat(), eligible_after.isoformat(), dataset_scope[:100],
        ),
    )
    db.commit()
    db.close()
    return prediction_id


def import_resolved_prediction(
    *,
    claim: str,
    probability: float,
    category: str,
    evidence: str,
    created_at: str,
    outcome: bool,
    outcome_evidence: str,
    resolved_at: str,
    dataset_scope: str,
    source_name: str,
    source_id: str,
) -> Optional[str]:
    """Import a historical forecast with explicit provenance, idempotently."""
    probability = float(probability)
    if not 0.0 <= probability <= 1.0:
        raise ValueError("probability must be between 0 and 1")
    forecast_time = datetime.fromisoformat(created_at)
    resolution_time = datetime.fromisoformat(resolved_at)
    if forecast_time >= resolution_time:
        raise ValueError("historical forecast must predate its resolution")
    if dataset_scope == "operational":
        raise ValueError("historical imports cannot use the operational scope")
    if not source_name.strip() or not source_id.strip():
        raise ValueError("historical imports require source provenance")

    prediction_id = str(uuid.uuid4())[:8]
    db = _conn()
    cur = db.execute(
        "INSERT OR IGNORE INTO predictions "
        "(id, claim, probability, category, evidence, created_at, outcome, "
        "outcome_evidence, resolved_at, eligible_after, dataset_scope, source_name, source_id) "
        "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
        (
            prediction_id, claim[:500], probability, category[:100], evidence[:1000],
            forecast_time.isoformat(), 1 if outcome else 0, outcome_evidence[:1000],
            resolution_time.isoformat(), resolution_time.isoformat(), dataset_scope[:100],
            source_name[:100], source_id[:200],
        ),
    )
    db.commit()
    inserted = prediction_id if cur.rowcount == 1 else None
    db.close()
    return inserted


def resolve_prediction(prediction_id: str, happened: bool, evidence: str) -> bool:
    if not evidence.strip():
        raise ValueError("resolution evidence is required")
    db = _conn()
    cur = db.execute(
        "UPDATE predictions SET outcome=?, outcome_evidence=?, resolved_at=? "
        "WHERE id=? AND resolved_at IS NULL "
        "AND (eligible_after IS NULL OR eligible_after <= ?)",
        (
            1 if happened else 0, evidence[:1000], datetime.now().isoformat(),
            prediction_id, datetime.now().isoformat(),
        ),
    )
    db.commit()
    changed = cur.rowcount == 1
    db.close()
    return changed


def _brier(rows: list[tuple]) -> float:
    return sum((probability - outcome) ** 2 for probability, outcome, *_ in rows) / len(rows)


def calibration_stats(
    train_fraction: float = 0.7,
    min_train: int = 10,
    min_test: int = 5,
    dataset_scope: str = "operational",
) -> dict:
    """Chronological held-out evaluation with a training-only null baseline."""
    db = _conn()
    rows = db.execute(
        "SELECT probability, outcome, category, created_at, resolved_at "
        "FROM predictions WHERE resolved_at IS NOT NULL AND dataset_scope=? ORDER BY created_at",
        (dataset_scope,),
    ).fetchall()
    pending = db.execute(
        "SELECT COUNT(*) FROM predictions WHERE resolved_at IS NULL AND dataset_scope=?",
        (dataset_scope,),
    ).fetchone()[0]
    db.close()
    if not rows:
        return {
            "resolved": 0, "pending": pending, "descriptive_brier_score": None,
            "test_brier_score": None, "null_brier_score": None,
            "brier_skill_score": None, "evaluation_status": "insufficient_data",
            "maturity": "empty", "dataset_scope": dataset_scope,
        }

    descriptive_brier = _brier(rows)
    positives = sum(outcome for _, outcome, *_ in rows)
    negatives = len(rows) - positives
    observed_base_rate = sum(outcome for _, outcome, *_ in rows) / len(rows)
    descriptive_null_brier = sum(
        (observed_base_rate - outcome) ** 2 for _, outcome, *_ in rows
    ) / len(rows)
    split = max(min_train, int(len(rows) * train_fraction))
    train, test = rows[:split], rows[split:]
    enough_data = len(train) >= min_train and len(test) >= min_test
    if not enough_data:
        return {
            "resolved": len(rows),
            "pending": pending,
            "descriptive_brier_score": round(descriptive_brier, 4),
            "descriptive_null_brier_score": round(descriptive_null_brier, 4),
            "observed_base_rate": round(observed_base_rate, 4),
            "positive_outcomes": positives,
            "negative_outcomes": negatives,
            "test_brier_score": None,
            "null_brier_score": None,
            "brier_skill_score": None,
            "train_size": len(train),
            "test_size": len(test),
            "evaluation_status": "insufficient_out_of_sample_data",
            "maturity": "low", "dataset_scope": dataset_scope,
        }

    test_brier = _brier(test)
    train_base_rate = sum(outcome for _, outcome, *_ in train) / len(train)
    null_brier = sum((train_base_rate - outcome) ** 2 for _, outcome, *_ in test) / len(test)
    skill = None if null_brier == 0 else 1 - (test_brier / null_brier)
    train_outcomes = {outcome for _, outcome, *_ in train}
    evaluation_status = (
        "valid_out_of_sample" if len(train_outcomes) == 2
        else "insufficient_training_class_diversity"
    )
    return {
        "resolved": len(rows),
        "pending": pending,
        "descriptive_brier_score": round(descriptive_brier, 4),
        "descriptive_null_brier_score": round(descriptive_null_brier, 4),
        "observed_base_rate": round(observed_base_rate, 4),
        "positive_outcomes": positives,
        "negative_outcomes": negatives,
        "test_brier_score": round(test_brier, 4),
        "null_brier_score": round(null_brier, 4),
        "brier_skill_score": round(skill, 4) if skill is not None else None,
        "train_base_rate": round(train_base_rate, 4),
        "train_size": len(train),
        "test_size": len(test),
        "evaluation_status": evaluation_status,
        "maturity": "low" if len(rows) < 10 else "moderate" if len(rows) < 50 else "established",
        "dataset_scope": dataset_scope,
    }


def pending_predictions(category_prefix: str = "", dataset_scope: str = "operational") -> list[dict]:
    db = _conn()
    if category_prefix:
        rows = db.execute(
            "SELECT id, claim, probability, category, evidence, created_at "
            "FROM predictions WHERE resolved_at IS NULL AND dataset_scope=? AND category LIKE ?",
            (dataset_scope, f"{category_prefix}%"),
        ).fetchall()
    else:
        rows = db.execute(
            "SELECT id, claim, probability, category, evidence, created_at "
            "FROM predictions WHERE resolved_at IS NULL AND dataset_scope=?",
            (dataset_scope,),
        ).fetchall()
    db.close()
    return [
        {
            "id": row[0], "claim": row[1], "probability": row[2],
            "category": row[3], "evidence": row[4], "created_at": row[5],
        }
        for row in rows
    ]
