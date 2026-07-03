"""Interfaz de proveedor de datos de atleta.

La lógica del sistema (cálculos, normalización, dedupe, persistencia, render)
NO depende de MCP ni de ningún LLM. Cualquier fuente que implemente este
Protocol puede alimentar el pipeline.
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Protocol, runtime_checkable

from ..models import RawActivity, RawActivityDetail, RawDailyMetrics, RawTrainingStatus


@runtime_checkable
class AthleteProvider(Protocol):
    provider_name: str
    provider_version: str

    def fetch_activities(self, start: datetime, end: datetime) -> list[RawActivity]:
        ...

    def fetch_daily_metrics(self, start: date, end: date) -> list[RawDailyMetrics]:
        ...

    def fetch_training_status(self, start: date, end: date) -> list[RawTrainingStatus]:
        ...

    def fetch_activity_detail(self, activity_id: str) -> RawActivityDetail | None:
        ...
