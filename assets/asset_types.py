#!/usr/bin/env python3
"""Shared types for Echo Asset System v1."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from typing import Any


class AssetType(StrEnum):
    VEHICLE = "vehicle"
    AI_SYSTEM = "ai_system"
    WORKSHOP = "workshop"
    FURNACE = "furnace"
    HOME = "home"
    IMAGE = "image"
    SENSOR = "sensor"
    VOICE = "voice"
    PART = "part"
    UNKNOWN = "unknown"


class ObservationSource(StrEnum):
    MANUAL = "manual"
    VOICE = "voice"
    IMAGE = "image"
    OBD = "obd"
    SENSOR = "sensor"
    TELEMETRY = "telemetry"
    SYSTEM = "system"


@dataclass(frozen=True)
class Asset:
    asset_id: str
    name: str
    type: AssetType | str
    manufacturer: str = ""
    model: str = ""
    serial: str = ""
    status: str = "active"
    created: str = field(default_factory=lambda: datetime.now().isoformat())
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class Observation:
    asset: str
    summary: str
    source: ObservationSource | str = ObservationSource.MANUAL
    raw_text: str = ""
    tags: list[str] = field(default_factory=list)
    confidence: float = 1.0
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())
    payload: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class AssetTask:
    asset: str
    priority: str
    task: str
    status: str = "OPEN"
    created: str = field(default_factory=lambda: datetime.now().isoformat())
    completed: str | None = None
