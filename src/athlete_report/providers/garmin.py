"""Placeholder: Garmin Connect.

Futuro: implementar contra Garmin Connect API (requiere programa de
desarrolladores) o export de Garmin Connect. Mismo contrato AthleteProvider.
"""

from __future__ import annotations

from datetime import date, datetime

from ..models import RawActivity, RawActivityDetail, RawDailyMetrics, RawTrainingStatus

_MSG = "GarminProvider no está implementado todavía."


class GarminProvider:
    provider_name = "garmin"
    provider_version = "unimplemented"

    def fetch_activities(self, start: datetime, end: datetime) -> list[RawActivity]:
        raise NotImplementedError(_MSG)

    def fetch_daily_metrics(self, start: date, end: date) -> list[RawDailyMetrics]:
        raise NotImplementedError(_MSG)

    def fetch_training_status(self, start: date, end: date) -> list[RawTrainingStatus]:
        raise NotImplementedError(_MSG)

    def fetch_activity_detail(self, activity_id: str) -> RawActivityDetail | None:
        raise NotImplementedError(_MSG)
