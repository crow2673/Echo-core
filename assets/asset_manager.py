#!/usr/bin/env python3
"""High-level asset ownership API."""
from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime
from pathlib import Path
from typing import Any

from assets.asset_database import AssetDatabase
from assets.asset_types import Asset, Observation
from assets.task_manager import TaskManager


PROPOSAL_STATES = {
    "pending_review",
    "approved",
    "rejected",
    "changes_requested",
    "expired",
    "invalidated",
    "created",
}
UNSAFE_ACTION_TERMS = {
    "order ",
    "buy ",
    "purchase",
    "contact ",
    "call ",
    "email ",
    "repair ",
    "replace ",
    "drive ",
    "tow ",
    "pay ",
    "spend",
    "wire ",
    "hazardous",
}
SAFE_ACTION_HINTS = {
    "review",
    "mark for human review",
    "capture",
    "verify",
    "schedule",
    "attach",
    "enter",
    "compare",
    "inspect",
    "preserve",
    "monitor",
    "avoid",
}


def _value(value: Any) -> str:
    return getattr(value, "value", str(value))


class AssetManager:
    def __init__(self, database: AssetDatabase | None = None):
        self.db = database or AssetDatabase()

    def register_asset(self, asset: Asset) -> str:
        return self.db.upsert_asset(
            asset_id=asset.asset_id,
            name=asset.name,
            type=_value(asset.type),
            manufacturer=asset.manufacturer,
            model=asset.model,
            serial=asset.serial,
            status=asset.status,
            created=asset.created,
            metadata=asset.metadata,
        )

    def ensure_asset(self, asset_id: str, name: str | None = None, type: str = "unknown") -> str:
        if self.db.get_asset(asset_id):
            return asset_id
        return self.register_asset(Asset(asset_id=asset_id, name=name or asset_id, type=type))

    def observe(self, observation: Observation) -> dict[str, Any]:
        self.ensure_asset(observation.asset)
        obs_id = self.db.insert_observation(
            asset_id=observation.asset,
            timestamp=observation.timestamp,
            source=_value(observation.source),
            summary=observation.summary,
            raw_text=observation.raw_text,
            confidence=observation.confidence,
            tags=observation.tags,
            payload=observation.payload,
        )
        return {"observation_id": obs_id, "asset_id": observation.asset}

    def ingest_structured_observation(self, data: dict[str, Any]) -> dict[str, Any]:
        """Ingest one reviewed local asset observation with provenance and comparison metadata."""
        asset_id = str(data["asset_id"])
        asset = data.get("asset") or {}
        if not self.db.get_asset(asset_id):
            if asset:
                self.register_asset(Asset(
                    asset_id=asset_id,
                    name=asset.get("name") or asset_id,
                    type=asset.get("type", "unknown"),
                    manufacturer=asset.get("manufacturer", ""),
                    model=asset.get("model", ""),
                    serial=asset.get("serial", ""),
                    status=asset.get("status", "active"),
                    created=asset.get("created", datetime.now().isoformat()),
                    metadata=asset.get("metadata", {}),
                ))
            else:
                self.ensure_asset(asset_id, name=asset_id, type="unknown")
        timestamp = str(data.get("timestamp") or datetime.now().isoformat())
        source = str(data.get("source", "manual"))
        summary = str(data.get("summary") or "")
        extracted_facts = dict(data.get("extracted_facts") or {})
        inferred_facts = dict(data.get("inferred_facts") or {})
        provenance = {
            "source": source,
            "timestamp": timestamp,
            "asset_id": asset_id,
            "observer": data.get("observer", "unknown"),
            "raw_input_reference": data.get("raw_input_reference", ""),
            "processing_method": data.get("processing_method", "manual_fixture"),
            "review_status": data.get("review_status", "pending_review"),
        }
        signature_payload = {
            "asset_id": asset_id,
            "timestamp": timestamp,
            "source": source,
            "raw_input_reference": provenance["raw_input_reference"],
            "extracted_facts": extracted_facts,
            "inferred_facts": inferred_facts,
        }
        signature = hashlib.sha256(json.dumps(signature_payload, sort_keys=True, default=str).encode()).hexdigest()
        duplicate = self._find_observation_by_signature(asset_id, signature)
        if duplicate:
            return {
                "ok": True,
                "duplicate": True,
                "observation_id": duplicate["id"],
                "asset_id": asset_id,
                "observation_signature": signature,
                "change_status": "duplicate",
                "recommended_next_action": "Do not ingest duplicate observation; review existing asset history if needed.",
            }

        prior = self._latest_asset_intelligence_observation(asset_id)
        comparison = compare_asset_facts(prior, data)
        next_action = str(data.get("recommended_next_action") or "").strip() or bounded_next_action(comparison, data)
        payload = {
            "schema": data.get("schema", "echo.asset_observation"),
            "schema_version": int(data.get("schema_version", 1)),
            "asset_intelligence_version": "1.0",
            "observation_signature": signature,
            "provenance": provenance,
            "extracted_facts": extracted_facts,
            "inferred_facts": inferred_facts,
            "confidence": float(data.get("confidence", 1.0)),
            "uncertainty": list(data.get("uncertainty") or []),
            "review_status": provenance["review_status"],
            "change_from_prior": comparison,
            "recommended_next_action": next_action,
        }
        observation = Observation(
            asset=asset_id,
            timestamp=timestamp,
            source=source,
            summary=summary,
            raw_text=str(data.get("raw_text", "")),
            tags=list(data.get("tags") or ["asset_intelligence"]),
            confidence=float(data.get("confidence", 1.0)),
            payload=payload,
        )
        result = self.observe(observation)
        return {
            "ok": True,
            **result,
            "duplicate": False,
            "observation_signature": signature,
            "change_status": comparison["status"],
            "comparison": comparison,
            "recommended_next_action": next_action,
        }

    def asset_status(self, asset_id: str, limit: int = 5) -> dict[str, Any]:
        asset = self.db.get_asset(asset_id)
        observations = self.db.recent_observations(limit=limit, asset_id=asset_id)
        return {
            "asset": asset,
            "recent_observations": observations,
            "open_tasks": self.db.open_tasks(asset_id),
            "telemetry": self.db.telemetry_recent(asset_id, limit=limit),
        }

    def propose_task_from_observation(
        self,
        observation_id: int,
        *,
        due_window: str | None = None,
    ) -> dict[str, Any]:
        observation = self.db.get_observation(observation_id)
        if not observation:
            raise RuntimeError(f"source observation not found: {observation_id}")
        asset = self.db.get_asset(observation["asset_id"])
        if not asset:
            raise RuntimeError(f"asset not found: {observation['asset_id']}")
        payload = observation.get("payload") or {}
        action = payload.get("recommended_next_action")
        if not action:
            raise RuntimeError("source observation has no recommended_next_action")
        provenance = payload.get("provenance") or {}
        missing = [
            key for key in ("source", "timestamp", "asset_id", "observer", "raw_input_reference", "processing_method", "review_status")
            if not provenance.get(key)
        ]
        if missing:
            raise RuntimeError(f"source observation provenance incomplete: {', '.join(missing)}")
        safety = classify_action_safety(action)
        if not safety["allowed"]:
            raise RuntimeError(f"unsafe or unbounded recommended action: {safety['reason']}")
        proposal_id = proposal_id_for_observation(observation, action)
        existing = self.db.get_task_proposal(proposal_id)
        if existing:
            return self._proposal_with_review(self._validate_proposal(existing))
        comparison = payload.get("change_from_prior") or {}
        proposal = {
            "proposal_id": proposal_id,
            "asset_id": observation["asset_id"],
            "source_observation_id": observation["id"],
            "proposed_title": proposed_task_title(asset, comparison, action),
            "proposed_description": proposed_task_description(observation, action),
            "proposed_task_type": proposed_task_type(action),
            "priority": proposed_priority(comparison),
            "evidence_summary": observation["summary"],
            "facts_used": payload.get("extracted_facts") or {},
            "inferences_used": payload.get("inferred_facts") or {},
            "confidence": payload.get("confidence", observation.get("confidence", 1.0)),
            "uncertainty": payload.get("uncertainty") or [],
            "suggested_due_window": due_window or suggested_due_window(action, comparison),
            "safety_notes": safety["notes"],
            "created_at": datetime.now().isoformat(),
            "status": "pending_review",
            "reviewer": None,
            "reviewed_at": None,
            "review_notes": None,
            "resulting_task_id": None,
            "source_fingerprint": source_observation_fingerprint(observation),
            "metadata": {
                "recommended_next_action": action,
                "source_provenance": provenance,
                "approval_consequence": "Approving creates one OPEN asset task only; it does not perform repairs, spend money, order parts, or contact anyone.",
                "does_not_claim": [
                    "no mechanical diagnosis",
                    "no autonomous repair",
                    "no parts purchase",
                    "no external contact",
                ],
            },
        }
        self.db.add_task_proposal(proposal)
        return self._proposal_with_review(proposal)

    def list_task_proposals(self, asset_id: str | None = None) -> list[dict[str, Any]]:
        return [self._proposal_with_review(self._validate_proposal(item)) for item in self.db.list_task_proposals(asset_id)]

    def show_task_proposal(self, proposal_id: str) -> dict[str, Any]:
        proposal = self.db.get_task_proposal(proposal_id)
        if not proposal:
            raise RuntimeError(f"proposal not found: {proposal_id}")
        return self._proposal_with_review(self._validate_proposal(proposal))

    def approve_task_proposal(self, proposal_id: str, *, reviewer: str, notes: str = "",
                              due_window: str | None = None) -> dict[str, Any]:
        if not reviewer:
            raise RuntimeError("reviewer is required for approval")
        proposal = self.show_task_proposal(proposal_id)
        status = proposal["status"]
        if status == "created" and proposal.get("resulting_task_id"):
            return proposal
        if status in {"rejected", "changes_requested", "expired", "invalidated"}:
            raise RuntimeError(f"proposal cannot create task from state: {status}")
        self.db.update_task_proposal(
            proposal_id,
            status="approved",
            reviewer=reviewer,
            reviewed_at=datetime.now().isoformat(),
            review_notes=notes,
            suggested_due_window=due_window or proposal.get("suggested_due_window"),
        )
        approved = self.db.get_task_proposal(proposal_id)
        task_id = TaskManager(self.db).create_from_approved_proposal(approved)
        self.db.update_task_proposal(proposal_id, status="created", resulting_task_id=task_id)
        return self._proposal_with_review(self.db.get_task_proposal(proposal_id))

    def reject_task_proposal(self, proposal_id: str, *, reviewer: str, notes: str = "") -> dict[str, Any]:
        return self._review_without_task(proposal_id, "rejected", reviewer=reviewer, notes=notes)

    def request_task_changes(self, proposal_id: str, *, reviewer: str, notes: str = "") -> dict[str, Any]:
        return self._review_without_task(proposal_id, "changes_requested", reviewer=reviewer, notes=notes)

    def _review_without_task(self, proposal_id: str, status: str, *, reviewer: str, notes: str) -> dict[str, Any]:
        if status not in {"rejected", "changes_requested"}:
            raise RuntimeError(f"unsupported review status: {status}")
        proposal = self.show_task_proposal(proposal_id)
        if proposal.get("resulting_task_id"):
            raise RuntimeError("proposal already created a task")
        if proposal["status"] in {"created", "expired", "invalidated"}:
            raise RuntimeError(f"proposal cannot be reviewed from state: {proposal['status']}")
        self.db.update_task_proposal(
            proposal_id,
            status=status,
            reviewer=reviewer,
            reviewed_at=datetime.now().isoformat(),
            review_notes=notes,
        )
        return self._proposal_with_review(self.db.get_task_proposal(proposal_id))

    def _validate_proposal(self, proposal: dict[str, Any]) -> dict[str, Any]:
        observation = self.db.get_observation(int(proposal["source_observation_id"]))
        changed = False
        reason = ""
        if not observation:
            changed = True
            reason = "source observation missing"
        elif observation["asset_id"] != proposal["asset_id"]:
            changed = True
            reason = "asset identity changed"
        elif source_observation_fingerprint(observation) != proposal.get("source_fingerprint"):
            changed = True
            reason = "source observation fingerprint changed"
        if not changed:
            return proposal
        metadata = dict(proposal.get("metadata") or {})
        metadata["source_linkage_changed"] = True
        metadata["source_linkage_change_reason"] = reason
        metadata["source_linkage_changed_at"] = datetime.now().isoformat()
        if proposal.get("resulting_task_id"):
            task = self.db.get_task(int(proposal["resulting_task_id"]))
            if task:
                task_meta = dict(task.get("metadata") or {})
                task_meta["source_linkage_changed"] = True
                task_meta["source_linkage_change_reason"] = reason
                self.db.update_task_metadata(int(task["id"]), task_meta)
        if proposal.get("status") in {"pending_review", "approved", "created"}:
            self.db.update_task_proposal(proposal["proposal_id"], status="invalidated", metadata=metadata)
            refreshed = self.db.get_task_proposal(proposal["proposal_id"])
            return refreshed or proposal
        self.db.update_task_proposal(proposal["proposal_id"], metadata=metadata)
        refreshed = self.db.get_task_proposal(proposal["proposal_id"])
        return refreshed or proposal

    @staticmethod
    def _proposal_with_review(proposal: dict[str, Any]) -> dict[str, Any]:
        if not proposal:
            return proposal
        metadata = proposal.get("metadata") or {}
        proposal["review_summary"] = {
            "observed_facts": proposal.get("facts_used", {}),
            "inferred_facts": proposal.get("inferences_used", {}),
            "uncertainty": proposal.get("uncertainty", []),
            "why_proposed": proposal.get("evidence_summary", ""),
            "does_not_claim": metadata.get("does_not_claim", []),
            "source_observation_id": proposal.get("source_observation_id"),
            "proposed_next_action": metadata.get("recommended_next_action", ""),
            "approval_consequence": metadata.get("approval_consequence", ""),
            "safety_notes": proposal.get("safety_notes", []),
        }
        return proposal

    def _find_observation_by_signature(self, asset_id: str, signature: str) -> dict[str, Any] | None:
        for item in self.db.recent_observations(limit=200, asset_id=asset_id):
            payload = item.get("payload") or {}
            if payload.get("observation_signature") == signature:
                return item
        return None

    def _latest_asset_intelligence_observation(self, asset_id: str) -> dict[str, Any] | None:
        for item in self.db.recent_observations(limit=50, asset_id=asset_id):
            payload = item.get("payload") or {}
            if payload.get("asset_intelligence_version"):
                return item
        return None

    def summary(self) -> dict[str, Any]:
        summary = self.db.asset_summary()
        summary["generated_at"] = datetime.now().isoformat()
        return summary


def compare_asset_facts(prior: dict[str, Any] | None, current: dict[str, Any]) -> dict[str, Any]:
    current_facts = dict(current.get("extracted_facts") or {})
    confidence = float(current.get("confidence", 1.0))
    uncertainty = list(current.get("uncertainty") or [])
    if not prior:
        return {
            "status": "no_prior_observation",
            "changed_fields": [],
            "conflicting_fields": [],
            "reason": "No prior structured observation exists for this asset; this becomes the baseline.",
        }
    prior_payload = prior.get("payload") or {}
    prior_facts = dict(prior_payload.get("extracted_facts") or {})
    changed = []
    conflicting = []
    for key in sorted(set(prior_facts) | set(current_facts)):
        old = prior_facts.get(key)
        new = current_facts.get(key)
        if old == new:
            continue
        changed.append(key)
        if _conflicts(key, old, new):
            conflicting.append(key)
    if conflicting:
        status = "conflicting_evidence"
        reason = f"Conflicting values found for: {', '.join(conflicting)}."
    elif changed:
        status = "changed"
        reason = f"Meaningful fact changes found for: {', '.join(changed)}."
    elif confidence < 0.7 or uncertainty or current.get("review_status") == "pending_review":
        status = "uncertain"
        reason = "Observation confidence or uncertainty requires human review."
    else:
        status = "no_meaningful_change"
        reason = "Structured facts match the latest prior observation."
    return {
        "status": status,
        "changed_fields": changed,
        "conflicting_fields": conflicting,
        "prior_observation_id": prior.get("id"),
        "reason": reason,
    }


def _conflicts(key: str, old: Any, new: Any) -> bool:
    if old is None or new is None:
        return False
    if key in {"odometer_miles", "mileage", "hours"}:
        try:
            return float(new) < float(old)
        except (TypeError, ValueError):
            return True
    return False


def bounded_next_action(comparison: dict[str, Any], observation: dict[str, Any]) -> str:
    status = comparison["status"]
    if status == "no_prior_observation":
        return "Capture one follow-up observation later so Echo has a baseline to compare against."
    if status == "no_meaningful_change":
        return "No immediate action; keep the observation in asset history."
    if status == "changed":
        if "maintenance" in observation.get("tags", []) or "fault" in observation.get("tags", []):
            return "Schedule a maintenance check or attach a service record; do not diagnose or order parts automatically."
        return "Mark the observation for review and compare it with the prior asset record."
    if status == "conflicting_evidence":
        return "Mark for human review and enter a corrected measurement or source note."
    if status == "uncertain":
        return "Capture another angle or missing measurement before treating this as a real change."
    return "Review the asset history before taking action."


def source_observation_fingerprint(observation: dict[str, Any]) -> str:
    payload = observation.get("payload") or {}
    material = {
        "id": observation.get("id"),
        "asset_id": observation.get("asset_id"),
        "recommended_next_action": payload.get("recommended_next_action"),
        "provenance": payload.get("provenance"),
        "extracted_facts": payload.get("extracted_facts"),
        "inferred_facts": payload.get("inferred_facts"),
        "confidence": payload.get("confidence", observation.get("confidence")),
        "uncertainty": payload.get("uncertainty"),
    }
    return hashlib.sha256(json.dumps(material, sort_keys=True, default=str).encode()).hexdigest()


def proposal_id_for_observation(observation: dict[str, Any], action: str) -> str:
    payload = {
        "source_observation_id": observation.get("id"),
        "asset_id": observation.get("asset_id"),
        "action": action,
    }
    digest = hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()[:16]
    return f"asset-proposal-{digest}"


def classify_action_safety(action: str) -> dict[str, Any]:
    low = f" {action.lower()} "
    unsafe = [term.strip() for term in UNSAFE_ACTION_TERMS if term in low]
    if unsafe:
        return {"allowed": False, "reason": f"blocked unsafe terms: {', '.join(sorted(unsafe))}", "notes": []}
    if not any(hint in low for hint in SAFE_ACTION_HINTS):
        return {"allowed": False, "reason": "action lacks a bounded review/verify/capture/schedule/attach/inspect verb", "notes": []}
    return {
        "allowed": True,
        "reason": "bounded non-autonomous action",
        "notes": [
            "Requires explicit human approval before task creation.",
            "Does not spend money, order parts, contact anyone, or perform repairs.",
            "Does not claim a safety-critical diagnosis.",
        ],
    }


def proposed_task_title(asset: dict[str, Any], comparison: dict[str, Any], action: str) -> str:
    name = asset.get("name") or asset.get("asset_id") or "asset"
    if "tacoma" in name.lower() and comparison.get("status") == "conflicting_evidence":
        return "Review Tacoma maintenance record conflict"
    if "schedule" in action.lower() and "maintenance" in action.lower():
        return f"Review maintenance check for {name}"
    return f"Review asset observation for {name}"


def proposed_task_description(observation: dict[str, Any], action: str) -> str:
    return (
        f"Source observation {observation['id']}: {observation.get('summary', '')}\n"
        f"Recommended action: {action}\n"
        "Human approval created this task; no autonomous repair or purchase is authorized."
    )


def proposed_task_type(action: str) -> str:
    low = action.lower()
    if "maintenance" in low:
        return "maintenance_review"
    if "measurement" in low or "odometer" in low or "corrected" in low:
        return "measurement_review"
    if "capture" in low or "image" in low:
        return "capture_followup"
    return "asset_review"


def proposed_priority(comparison: dict[str, Any]) -> str:
    status = comparison.get("status")
    if status == "conflicting_evidence":
        return "MEDIUM"
    if status == "changed":
        return "MEDIUM"
    return "LOW"


def suggested_due_window(action: str, comparison: dict[str, Any]) -> str:
    if comparison.get("status") == "conflicting_evidence":
        return "next_manual_review"
    if "maintenance" in action.lower():
        return "next_maintenance_window"
    return "when_convenient"


def run_fixture(path: Path, *, db_path: Path | None = None) -> dict[str, Any]:
    data = json.loads(path.read_text())
    db = AssetDatabase(db_path) if db_path else AssetDatabase()
    manager = AssetManager(db)
    asset_data = data["asset"]
    manager.register_asset(Asset(**asset_data))
    results = []
    for observation in data.get("observations", []):
        results.append(manager.ingest_structured_observation(observation))
    return {
        "asset_id": asset_data["asset_id"],
        "results": results,
        "status": manager.asset_status(asset_data["asset_id"], limit=10),
    }


def _self_test() -> dict[str, Any]:
    db_path = Path("/tmp/echo_asset_intelligence_selftest.sqlite")
    if db_path.exists():
        db_path.unlink()
    fixture = Path(__file__).resolve().parents[1] / "tests/fixtures/asset_intelligence/tacoma_day5_fixture.json"
    return run_fixture(fixture, db_path=db_path)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--self-test", action="store_true")
    parser.add_argument("--demo-fixture", type=Path)
    parser.add_argument("--asset-status")
    parser.add_argument("--propose-task-from-observation", type=int)
    parser.add_argument("--list-task-proposals", action="store_true")
    parser.add_argument("--show-task-proposal")
    parser.add_argument("--approve-task-proposal")
    parser.add_argument("--reject-task-proposal")
    parser.add_argument("--request-task-changes")
    parser.add_argument("--reviewer")
    parser.add_argument("--notes", default="")
    parser.add_argument("--due-window")
    parser.add_argument("--db", type=Path)
    args = parser.parse_args()

    manager = AssetManager(AssetDatabase(args.db) if args.db else None)
    if args.self_test:
        print(json.dumps(_self_test(), indent=2, sort_keys=True, default=str))
        return 0
    if args.demo_fixture:
        print(json.dumps(run_fixture(args.demo_fixture, db_path=args.db), indent=2, sort_keys=True, default=str))
        return 0
    if args.asset_status:
        print(json.dumps(manager.asset_status(args.asset_status), indent=2, sort_keys=True, default=str))
        return 0
    if args.propose_task_from_observation:
        print(json.dumps(
            manager.propose_task_from_observation(args.propose_task_from_observation, due_window=args.due_window),
            indent=2,
            sort_keys=True,
            default=str,
        ))
        return 0
    if args.list_task_proposals:
        print(json.dumps(manager.list_task_proposals(), indent=2, sort_keys=True, default=str))
        return 0
    if args.show_task_proposal:
        print(json.dumps(manager.show_task_proposal(args.show_task_proposal), indent=2, sort_keys=True, default=str))
        return 0
    if args.approve_task_proposal:
        print(json.dumps(
            manager.approve_task_proposal(
                args.approve_task_proposal,
                reviewer=args.reviewer or "",
                notes=args.notes,
                due_window=args.due_window,
            ),
            indent=2,
            sort_keys=True,
            default=str,
        ))
        return 0
    if args.reject_task_proposal:
        print(json.dumps(
            manager.reject_task_proposal(args.reject_task_proposal, reviewer=args.reviewer or "", notes=args.notes),
            indent=2,
            sort_keys=True,
            default=str,
        ))
        return 0
    if args.request_task_changes:
        print(json.dumps(
            manager.request_task_changes(args.request_task_changes, reviewer=args.reviewer or "", notes=args.notes),
            indent=2,
            sort_keys=True,
            default=str,
        ))
        return 0
    parser.error("use --self-test, --demo-fixture, --asset-status, or a task proposal command")


if __name__ == "__main__":
    raise SystemExit(main())
