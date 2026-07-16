#!/usr/bin/env python3
"""Asset task creation and tracking."""
from __future__ import annotations

from datetime import datetime
from typing import Any

from assets.asset_database import AssetDatabase
from assets.asset_types import AssetTask


class TaskManager:
    def __init__(self, database: AssetDatabase | None = None):
        self.db = database or AssetDatabase()

    def add_task(self, task: AssetTask) -> int:
        return self.db.add_task(
            asset_id=task.asset,
            priority=task.priority,
            task=task.task,
            status=task.status,
            created=task.created,
            completed=task.completed,
        )

    def create_from_approved_proposal(self, proposal: dict[str, Any]) -> int:
        if proposal.get("status") not in {"approved", "created"}:
            raise RuntimeError(f"proposal is not approved: {proposal.get('status')}")
        if proposal.get("resulting_task_id"):
            return int(proposal["resulting_task_id"])
        title = proposal["proposed_title"]
        description = proposal.get("proposed_description", "")
        due = proposal.get("suggested_due_window") or ""
        task_text = title if not description else f"{title}\n\n{description}"
        metadata = {
            "source_observation_id": proposal["source_observation_id"],
            "source_proposal_id": proposal["proposal_id"],
            "title": title,
            "description": description,
            "due_window": due,
            "created_by": "approved_asset_bridge",
            "provenance": (proposal.get("metadata") or {}).get("source_provenance", {}),
            "confidence": proposal.get("confidence"),
            "human_reviewer": proposal.get("reviewer"),
            "review_notes": proposal.get("review_notes"),
            "facts_used": proposal.get("facts_used", {}),
            "inferences_used": proposal.get("inferences_used", {}),
        }
        return self.db.add_task(
            asset_id=proposal["asset_id"],
            priority=proposal["priority"],
            task=task_text,
            status="OPEN",
            created=datetime.now().isoformat(),
            metadata=metadata,
        )

    def open_tasks(self, asset_id: str | None = None) -> list[dict]:
        return self.db.open_tasks(asset_id)

    def quick_task(self, *, asset: str, priority: str, task: str, status: str = "OPEN") -> int:
        return self.add_task(
            AssetTask(asset=asset, priority=priority, task=task, status=status, created=datetime.now().isoformat())
        )
