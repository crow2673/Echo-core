#!/usr/bin/env python3
"""
Echo Memory Promotion Layer
Scores memories based on:
- Retrieval frequency (how often Echo pulls this memory)
- Outcome signal (did actions informed by this memory succeed?)
- Recency (newer memories get a small boost)
- Specificity (longer, more detailed memories score higher)

Runs daily to update promotion scores.
High-scoring memories surface first in context retrieval.
"""
import sqlite3, json, math
from pathlib import Path
from datetime import datetime, timezone, timedelta

DB_PATH = Path("/home/andrew/Echo/echo_semantic_memory.sqlite")
LOG = Path("/home/andrew/Echo/logs/memory_promoter.log")

def log(msg):
    ts = datetime.now().strftime("%Y-%m-%d %H:%M")
    line = f"[{ts}] {msg}"
    print(line)
    LOG.parent.mkdir(exist_ok=True)
    with open(LOG, "a") as f:
        f.write(line + "\n")

def migrate_schema(db):
    """Add promotion columns if they don't exist."""
    existing = [row[1] for row in db.execute("PRAGMA table_info(memories)").fetchall()]
    
    if "retrieval_count" not in existing:
        db.execute("ALTER TABLE memories ADD COLUMN retrieval_count INTEGER DEFAULT 0")
        log("added retrieval_count column")
    
    if "last_retrieved" not in existing:
        db.execute("ALTER TABLE memories ADD COLUMN last_retrieved TEXT")
        log("added last_retrieved column")
    
    if "promotion_score" not in existing:
        db.execute("ALTER TABLE memories ADD COLUMN promotion_score REAL DEFAULT 0.0")
        log("added promotion_score column")
    
    if "outcome_score" not in existing:
        db.execute("ALTER TABLE memories ADD COLUMN outcome_score REAL DEFAULT 0.5")
        log("added outcome_score column")
    
    db.commit()

def compute_promotion_score(retrieval_count, last_retrieved, created_at, text, outcome_score):
    """
    Compute composite promotion score 0.0-1.0
    
    Components:
    - Retrieval frequency (40%) — how often this memory is useful
    - Outcome signal (30%) — did actions informed by this succeed
    - Recency (20%) — newer memories get a boost
    - Specificity (10%) — longer memories tend to be more specific
    """
    # Retrieval frequency — log scale so 10 retrievals isn't 10x better than 1
    retrieval_component = min(1.0, math.log1p(retrieval_count) / math.log1p(20))
    
    # Outcome signal — direct from regret index, default 0.5 (neutral)
    outcome_component = max(0.0, min(1.0, (outcome_score + 1.0) / 2.0))
    
    # Recency — memories from last 30 days get full score, older decay
    try:
        created = datetime.fromisoformat(created_at.replace('Z', '+00:00'))
        age_days = (datetime.now(timezone.utc) - created).days
        recency_component = max(0.0, 1.0 - (age_days / 180))  # decay over 6 months
    except Exception:
        recency_component = 0.5
    
    # Specificity — longer text = more specific, cap at 500 chars
    specificity_component = min(1.0, len(text) / 500)
    
    # Weighted composite
    score = (
        retrieval_component * 0.40 +
        outcome_component * 0.30 +
        recency_component * 0.20 +
        specificity_component * 0.10
    )
    
    return round(score, 4)

def run():
    log("memory_promoter started")
    db = sqlite3.connect(str(DB_PATH))
    
    # Migrate schema
    migrate_schema(db)
    
    # Get all memories
    rows = db.execute(
        "SELECT id, text, retrieval_count, last_retrieved, created_at, outcome_score "
        "FROM memories"
    ).fetchall()
    
    log(f"scoring {len(rows)} memories")
    
    updated = 0
    high_scorers = []
    
    for row_id, text, retrieval_count, last_retrieved, created_at, outcome_score in rows:
        retrieval_count = retrieval_count or 0
        outcome_score = outcome_score if outcome_score is not None else 0.5
        created_at = created_at or datetime.now(timezone.utc).isoformat()
        
        score = compute_promotion_score(
            retrieval_count, last_retrieved, created_at, text, outcome_score
        )
        
        db.execute(
            "UPDATE memories SET promotion_score=? WHERE id=?",
            (score, row_id)
        )
        updated += 1
        
        if score > 0.7:
            high_scorers.append((score, text[:60]))
    
    db.commit()
    db.close()
    
    log(f"scored {updated} memories")
    log(f"high scorers (>0.7): {len(high_scorers)}")
    for score, text in sorted(high_scorers, reverse=True)[:5]:
        log(f"  {score:.3f} — {text}")
    
    # Log to event ledger
    try:
        import sys
        sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
        from core.event_ledger import log_event
        log_event("knowledge", "memory_promoter",
            f"scored {updated} memories, {len(high_scorers)} high scorers",
            score=1.0)
    except Exception:
        pass

if __name__ == "__main__":
    run()
