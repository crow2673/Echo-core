import json
import sqlite3
from pathlib import Path

import pytest

from core import semantic_memory, structured_facts


def make_candidate(db_path: Path, subject: str = "Test drill batteries", value: str = "Fixture shelf B"):
    return structured_facts.create_candidate(
        subject=subject,
        predicate="stored_at",
        object_value=value,
        object_type="location",
        fact_type="item_location",
        confidence=0.86,
        privacy_scope="owner_private",
        source_type="fixture",
        source_reference="fixture-ledger-1",
        source_memory_ids=[101, 102],
        actor="Fixture",
        reason="fixture candidate",
        notes="sanitized test fact",
        metadata={"fixture": True},
        db_path=db_path,
    )


def approve(db_path: Path, fact_id: str):
    return structured_facts.approve_current(
        fact_id,
        reviewer="FixtureReviewer",
        reason="fixture approval",
        db_path=db_path,
    )


def test_candidate_facts_are_not_returned_as_current_truth(tmp_path):
    db = tmp_path / "facts.sqlite"
    candidate = make_candidate(db)

    assert candidate["status"] == "candidate"
    assert structured_facts.retrieve_preferred_fact("Where are the Test drill batteries?", db_path=db) is None


def test_approved_current_fact_is_preferred_with_privacy(tmp_path, monkeypatch):
    db = tmp_path / "facts.sqlite"
    candidate = make_candidate(db)
    current = approve(db, candidate["fact_id"])
    monkeypatch.setattr(structured_facts, "DEFAULT_DB_PATH", db)

    result = semantic_memory.retrieve_with_provenance("Where are the Test drill batteries?")

    assert result["source"] == "structured_current_fact"
    assert result["fact"]["fact_id"] == current["fact_id"]
    assert result["privacy_scope"] == "owner_private"
    assert result["provenance"]["source_memory_ids"] == [101, 102]


def test_removing_structured_fact_falls_back_to_semantic_memory(tmp_path, monkeypatch):
    facts_db = tmp_path / "facts.sqlite"
    semantic_db = tmp_path / "semantic.sqlite"
    candidate = make_candidate(facts_db)
    approve(facts_db, candidate["fact_id"])
    with structured_facts.connect(facts_db) as db:
        db.execute("DELETE FROM structured_facts")
        db.commit()

    monkeypatch.setattr(structured_facts, "DEFAULT_DB_PATH", facts_db)
    monkeypatch.setattr(semantic_memory, "DB_PATH", semantic_db)
    semantic_memory.remember(
        "User: I put the test drill batteries on Fixture shelf B\nEcho: Noted.",
        {"type": "exchange", "source": "fixture"},
    )

    result = semantic_memory.retrieve_with_provenance("Where are the Test drill batteries?")

    assert result["source"] == "semantic_raw_memory"
    assert result["status"] == "unreviewed_raw_evidence"
    assert result["provenance"]["memory_ids"]


def test_stale_fact_is_not_stated_as_current(tmp_path):
    db = tmp_path / "facts.sqlite"
    candidate = make_candidate(db)
    approve(db, candidate["fact_id"])
    structured_facts.mark_stale(candidate["fact_id"], actor="FixtureReviewer", reason="fixture stale", db_path=db)

    assert structured_facts.retrieve_preferred_fact("Where are the Test drill batteries?", db_path=db) is None


def test_superseding_location_preserves_old_and_returns_new(tmp_path):
    db = tmp_path / "facts.sqlite"
    old = make_candidate(db, value="Fixture shelf B")
    approve(db, old["fact_id"])
    new = structured_facts.create_candidate(
        subject="Test drill batteries",
        predicate="stored_at",
        object_value="Fixture cabinet C",
        object_type="location",
        fact_type="item_location",
        confidence=0.91,
        privacy_scope="owner_private",
        source_type="fixture",
        source_reference="fixture-ledger-2",
        source_memory_ids=[103],
        actor="Fixture",
        reason="newer fixture statement",
        db_path=db,
    )
    approved_new = structured_facts.approve_current(
        new["fact_id"],
        reviewer="FixtureReviewer",
        reason="fixture supersession",
        supersede_conflict=True,
        db_path=db,
    )

    history = structured_facts.list_fact_history("Test drill batteries", "stored_at", db_path=db)
    by_id = {fact["fact_id"]: fact for fact in history}
    preferred = structured_facts.retrieve_preferred_fact("Where are the Test drill batteries?", db_path=db)

    assert by_id[old["fact_id"]]["status"] == "superseded"
    assert by_id[old["fact_id"]]["superseded_by_fact_id"] == approved_new["fact_id"]
    assert approved_new["supersedes_fact_id"] == old["fact_id"]
    assert preferred["fact"]["object_value"] == "Fixture cabinet C"


def test_conflicting_current_facts_cannot_coexist_silently(tmp_path):
    db = tmp_path / "facts.sqlite"
    old = make_candidate(db, value="Fixture shelf B")
    approve(db, old["fact_id"])
    new = structured_facts.create_candidate(
        subject="Test drill batteries",
        predicate="stored_at",
        object_value="Fixture cabinet C",
        object_type="location",
        fact_type="item_location",
        confidence=0.91,
        privacy_scope="owner_private",
        source_type="fixture",
        source_reference="fixture-ledger-2",
        actor="Fixture",
        reason="newer fixture statement",
        db_path=db,
    )

    with pytest.raises(structured_facts.StructuredFactError, match="conflicting current fact"):
        approve(db, new["fact_id"])


def test_reviewed_facts_cannot_be_silently_overwritten(tmp_path):
    db = tmp_path / "facts.sqlite"
    first = make_candidate(db, value="Fixture shelf B")
    approve(db, first["fact_id"])
    duplicate = make_candidate(db, value="Fixture shelf B")

    assert duplicate["fact_id"] == first["fact_id"]
    assert duplicate["status"] == "current"
    assert duplicate["object_value"] == "Fixture shelf B"


def test_event_history_preserves_actor_reason_and_states(tmp_path):
    db = tmp_path / "facts.sqlite"
    candidate = make_candidate(db)
    approve(db, candidate["fact_id"])
    structured_facts.verify_current(
        candidate["fact_id"],
        actor="FixtureReviewer",
        reason="still observed in fixture",
        db_path=db,
    )

    events = structured_facts.list_events(candidate["fact_id"], db_path=db)

    assert [event["operation"] for event in events] == ["create_candidate", "approve_current", "verify_current"]
    assert events[1]["actor"] == "FixtureReviewer"
    assert events[1]["reason"] == "fixture approval"
    assert events[1]["previous_state"]["status"] == "candidate"
    assert events[1]["resulting_state"]["status"] == "current"


def test_reject_candidate_records_reviewer_on_fact_and_event(tmp_path):
    db = tmp_path / "facts.sqlite"
    candidate = make_candidate(db)
    rejected = structured_facts.reject_candidate(
        candidate["fact_id"],
        reviewer="FixtureReviewer",
        reason="malformed fixture candidate",
        db_path=db,
    )
    events = structured_facts.list_events(candidate["fact_id"], db_path=db)

    assert rejected["status"] == "rejected"
    assert rejected["reviewed_by"] == "FixtureReviewer"
    assert rejected["reviewed_at"]
    assert events[-1]["actor"] == "FixtureReviewer"
    assert events[-1]["operation"] == "reject_candidate"


def test_ordinary_semantic_memories_continue_working(tmp_path, monkeypatch):
    facts_db = tmp_path / "facts.sqlite"
    semantic_db = tmp_path / "semantic.sqlite"
    monkeypatch.setattr(structured_facts, "DEFAULT_DB_PATH", facts_db)
    monkeypatch.setattr(semantic_memory, "DB_PATH", semantic_db)
    memory_id = semantic_memory.remember(
        "User: The fixture compressor needs a filter check\nEcho: Noted.",
        {"type": "exchange", "source": "fixture"},
    )

    result = semantic_memory.retrieve_with_provenance("fixture compressor filter")

    assert result["source"] == "semantic_raw_memory"
    assert memory_id in result["provenance"]["memory_ids"]


@pytest.mark.parametrize(
    "query",
    [
        "Where did I put the Test drill batteries?",
        "Where are the tool batteries I put away?",
        "Do you remember where I stored those batteries for my tools?",
    ],
)
def test_hart_style_location_queries_work_with_structured_fact(tmp_path, query):
    db = tmp_path / "facts.sqlite"
    candidate = make_candidate(db)
    approve(db, candidate["fact_id"])

    result = structured_facts.retrieve_preferred_fact(query, db_path=db)

    assert result is not None
    assert result["fact"]["object_value"] == "Fixture shelf B"


def test_unrelated_battery_query_does_not_return_location(tmp_path):
    db = tmp_path / "facts.sqlite"
    candidate = make_candidate(db)
    approve(db, candidate["fact_id"])

    result = structured_facts.retrieve_preferred_fact(
        "What voltage do Test drill batteries use?",
        db_path=db,
    )

    assert result is None


def test_permission_fact_type_and_relationship_metadata(tmp_path):
    db = tmp_path / "facts.sqlite"
    candidate = structured_facts.create_candidate(
        subject="Fixture person",
        predicate="has_permission_to_use",
        object_value="Test drill batteries",
        object_type="item",
        relationship_context="fixture relation",
        fact_type="permission",
        confidence=1.0,
        privacy_scope="owner_private",
        source_type="fixture",
        source_reference="fixture-review-1",
        actor="FixtureReviewer",
        reason="fixture permission candidate",
        metadata={"permission_scope": "as needed", "ownership_transfer": False},
        db_path=db,
    )
    approved = structured_facts.approve_current(
        candidate["fact_id"],
        reviewer="FixtureReviewer",
        reason="fixture permission approval",
        db_path=db,
    )

    assert approved["fact_type"] == "permission"
    assert approved["object_type"] == "item"
    assert approved["relationship_context"] == "fixture relation"
    assert approved["metadata"]["permission_scope"] == "as needed"
    assert approved["metadata"]["ownership_transfer"] is False
