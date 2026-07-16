import json
from pathlib import Path

import pytest

from core import companion_session, structured_facts


def start_fixture(db: Path):
    return companion_session.start_session(
        title="Fixture maintenance session",
        purpose="Preserve exact state for a fixture repair.",
        current_step="Inspecting fixture connector",
        next_action="Inspect fixture connector",
        related_asset_ids=["FIXTURE-TOOL-01"],
        privacy_scope="owner_private",
        db_path=db,
    )


def current_fact(fact_db: Path):
    candidate = structured_facts.create_candidate(
        subject="Fixture drill batteries",
        predicate="stored_at",
        object_value="Fixture shelf B",
        object_type="location",
        fact_type="item_location",
        confidence=1.0,
        privacy_scope="owner_private",
        source_type="fixture",
        source_reference="fixture-memory-1",
        actor="Fixture",
        reason="fixture candidate",
        db_path=fact_db,
    )
    return structured_facts.approve_current(
        candidate["fact_id"],
        reviewer="FixtureReviewer",
        reason="fixture approval",
        db_path=fact_db,
    )


def test_only_one_active_session_allowed(tmp_path):
    db = tmp_path / "sessions.sqlite"
    start_fixture(db)
    with pytest.raises(companion_session.CompanionSessionError, match="active companion session"):
        start_fixture(db)


def test_parked_session_survives_new_process_style_read(tmp_path):
    db = tmp_path / "sessions.sqlite"
    session = start_fixture(db)
    companion_session.park_session(
        session["session_id"],
        reason="Fixture interruption",
        resume_cue="Return to fixture bench",
        next_action="Inspect fixture connector",
        db_path=db,
    )

    reread = companion_session.get_session(session["session_id"], db_path=db)

    assert reread["status"] == "parked"
    assert reread["resume_cue"] == "Return to fixture bench"
    assert reread["next_action"] == "Inspect fixture connector"


def test_resume_brief_preserves_purpose_and_exact_next_action(tmp_path):
    db = tmp_path / "sessions.sqlite"
    session = start_fixture(db)
    companion_session.record_update(
        session["session_id"],
        completed_step="Opened fixture case",
        current_step="Connector exposed",
        next_action="Inspect fixture connector",
        db_path=db,
    )
    companion_session.park_session(
        session["session_id"],
        reason="Fixture interruption",
        resume_cue="Return to fixture bench",
        next_action="Inspect fixture connector",
        db_path=db,
    )

    resumed = companion_session.resume_session(session["session_id"], db_path=db)

    brief = resumed["resume_brief"]
    assert brief["purpose"] == "Preserve exact state for a fixture repair."
    assert brief["last_completed_action"] == "Opened fixture case"
    assert brief["next_action"] == "Inspect fixture connector"


def test_silence_does_not_mark_session_complete(tmp_path):
    db = tmp_path / "sessions.sqlite"
    session = start_fixture(db)
    reread = companion_session.get_session(session["session_id"], db_path=db)
    assert reread["status"] == "active"
    assert reread["ended_at"] is None


def test_observations_are_referenced_not_duplicated(tmp_path):
    db = tmp_path / "sessions.sqlite"
    session = start_fixture(db)
    updated = companion_session.record_observation_reference(
        session["session_id"],
        observation_id="obs-fixture-001",
        source="assets.observation_manager",
        notes="fixture reference only",
        db_path=db,
    )

    assert updated["observation_references"] == [
        {"observation_id": "obs-fixture-001", "source": "assets.observation_manager", "notes": "fixture reference only"}
    ]
    assert "raw_text" not in json.dumps(updated["observation_references"])


def test_candidate_facts_are_not_presented_as_reviewed_truth(tmp_path, monkeypatch):
    session_db = tmp_path / "sessions.sqlite"
    fact_db = tmp_path / "facts.sqlite"
    monkeypatch.setattr(structured_facts, "DEFAULT_DB_PATH", fact_db)
    session = start_fixture(session_db)
    candidate = structured_facts.create_candidate(
        subject="Fixture drill batteries",
        predicate="stored_at",
        object_value="Fixture shelf B",
        object_type="location",
        fact_type="item_location",
        confidence=0.7,
        privacy_scope="owner_private",
        source_type="fixture",
        actor="Fixture",
        reason="candidate only",
        db_path=fact_db,
    )

    with pytest.raises(companion_session.CompanionSessionError, match="only current reviewed"):
        companion_session.record_structured_fact_reference(session["session_id"], fact_id=candidate["fact_id"], db_path=session_db)


def test_current_structured_fact_can_be_referenced_with_provenance(tmp_path, monkeypatch):
    session_db = tmp_path / "sessions.sqlite"
    fact_db = tmp_path / "facts.sqlite"
    monkeypatch.setattr(structured_facts, "DEFAULT_DB_PATH", fact_db)
    session = start_fixture(session_db)
    fact = current_fact(fact_db)

    updated = companion_session.record_structured_fact_reference(session["session_id"], fact_id=fact["fact_id"], db_path=session_db)

    ref = updated["structured_fact_references"][0]
    assert ref["fact_id"] == fact["fact_id"]
    assert ref["status"] == "current"
    assert ref["privacy_scope"] == "owner_private"
    assert ref["source_reference"] == "fixture-memory-1"


def test_rejected_or_stale_facts_are_not_current_references(tmp_path, monkeypatch):
    session_db = tmp_path / "sessions.sqlite"
    fact_db = tmp_path / "facts.sqlite"
    monkeypatch.setattr(structured_facts, "DEFAULT_DB_PATH", fact_db)
    session = start_fixture(session_db)
    fact = current_fact(fact_db)
    structured_facts.mark_stale(fact["fact_id"], actor="FixtureReviewer", reason="fixture stale", db_path=fact_db)

    with pytest.raises(companion_session.CompanionSessionError):
        companion_session.record_structured_fact_reference(session["session_id"], fact_id=fact["fact_id"], db_path=session_db)


def test_session_completion_requires_explicit_action(tmp_path):
    db = tmp_path / "sessions.sqlite"
    session = start_fixture(db)
    companion_session.record_decision(session["session_id"], decision="Use fixture driver", db_path=db)
    assert companion_session.get_session(session["session_id"], db_path=db)["status"] == "active"

    completed = companion_session.complete_session(session["session_id"], outcome="Fixture session complete", db_path=db)

    assert completed["status"] == "completed"
    assert completed["outcome"] == "Fixture session complete"


def test_abandoned_sessions_remain_auditable(tmp_path):
    db = tmp_path / "sessions.sqlite"
    session = start_fixture(db)
    abandoned = companion_session.abandon_session(session["session_id"], reason="Fixture no longer needed", db_path=db)
    events = companion_session.list_events(session["session_id"], db_path=db)

    assert abandoned["status"] == "abandoned"
    assert events[-1]["operation"] == "abandon_session"
    assert events[-1]["previous_state"]["status"] == "active"


def test_privacy_scope_persists(tmp_path):
    db = tmp_path / "sessions.sqlite"
    session = start_fixture(db)
    assert companion_session.get_session(session["session_id"], db_path=db)["privacy_scope"] == "owner_private"


def test_reviewed_session_history_cannot_be_silently_overwritten(tmp_path):
    db = tmp_path / "sessions.sqlite"
    session = start_fixture(db)
    companion_session.record_decision(session["session_id"], decision="Decision one", db_path=db)
    companion_session.record_decision(session["session_id"], decision="Decision two", db_path=db)
    events = companion_session.list_events(session["session_id"], db_path=db)

    assert [event["operation"] for event in events] == ["start_session", "record_decision", "record_decision"]
    assert events[1]["resulting_state"]["decisions"][0]["decision"] == "Decision one"
    assert events[2]["resulting_state"]["decisions"][1]["decision"] == "Decision two"


def test_executive_context_fields_remain_protected(tmp_path, monkeypatch):
    db = tmp_path / "sessions.sqlite"
    before = {"current_focus": "Fixture focus", "system_health": "OK"}
    monkeypatch.setattr(companion_session, "_exec_focus", lambda: before["current_focus"])
    session = start_fixture(db)
    companion_session.record_update(session["session_id"], current_step="Still fixture", db_path=db)

    assert session["related_executive_focus"] == "Fixture focus"
    assert before == {"current_focus": "Fixture focus", "system_health": "OK"}
