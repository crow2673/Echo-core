#!/usr/bin/env python3
"""Maintenance records for physical assets."""
from __future__ import annotations

from datetime import datetime

from assets.asset_database import AssetDatabase
from assets.task_manager import TaskManager


class MaintenanceEngine:
    def __init__(self, database: AssetDatabase | None = None):
        self.db = database or AssetDatabase()
        self.tasks = TaskManager(self.db)

    def record(self, *, asset: str, task: str, completed: bool = False,
               notes: str = "", mileage: float | None = None,
               hours: float | None = None, date: str | None = None) -> int:
        return self.db.add_maintenance(
            asset_id=asset,
            date=date or datetime.now().isoformat(),
            task=task,
            completed=completed,
            notes=notes,
            mileage=mileage,
            hours=hours,
        )

    def recommend_task(self, *, asset: str, priority: str, task: str) -> int:
        return self.tasks.quick_task(asset=asset, priority=priority, task=task)
