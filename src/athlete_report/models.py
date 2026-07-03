"""Modelos crudos normalizados que devuelven los providers."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Any


@dataclass
class RawActivity:
    provider: str
    external_activity_id: str
    name: str | None = None
    sport: str | None = None
    start_time: datetime | None = None
    local_date: date | None = None
    duration_s: float | None = None
    distance_m: float | None = None
    avg_hr: float | None = None
    max_hr: float | None = None
    training_load: float | None = None
    elevation_gain_m: float | None = None
    calories: float | None = None
    source_updated_at: str | None = None


@dataclass
class RawDailyMetrics:
    provider: str
    date: date
    hrv: float | None = None
    rhr: float | None = None
    sleep_duration_s: float | None = None
    sleep_score: float | None = None
    stress_avg: float | None = None
    steps: float | None = None


@dataclass
class RawTrainingStatus:
    provider: str
    date: date
    daily_load: float | None = None
    fitness: float | None = None
    fatigue: float | None = None
    status: str | None = None


@dataclass
class RawActivityDetail:
    provider: str
    external_activity_id: str
    payload: dict[str, Any] = field(default_factory=dict)
