"""Placeholder: Strava API v3.

Futuro: OAuth2 + /athlete/activities por rango. Strava no expone HRV/sueño,
así que fetch_daily_metrics devolvería lista vacía y se combinaría con otro
proveedor de métricas diarias.
"""

from __future__ import annotations

from datetime import date, datetime

from ..models import RawActivity, RawActivityDetail, RawDailyMetrics, RawTrainingStatus

_MSG = "StravaProvider no está implementado todavía."


class StravaProvider:
    provider_name = "strava"
    provider_version = "unimplemented"

    def fetch_activities(self, start: datetime, end: datetime) -> list[RawActivity]:
        raise NotImplementedError(_MSG)

    def fetch_daily_metrics(self, start: date, end: date) -> list[RawDailyMetrics]:
        raise NotImplementedError(_MSG)

    def fetch_training_status(self, start: date, end: date) -> list[RawTrainingStatus]:
        raise NotImplementedError(_MSG)

    def fetch_activity_detail(self, activity_id: str) -> RawActivityDetail | None:
        raise NotImplementedError(_MSG)
