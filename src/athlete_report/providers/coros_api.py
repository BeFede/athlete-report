"""Placeholder documentado: API oficial de COROS.

COROS no ofrece hoy una API pública general para terceros. Si se obtiene
acceso oficial (COROS Open Platform / EvoLab partner API), implementar acá:

- Autenticación: OAuth2 o token de partner según lo que otorgue COROS.
- fetch_activities: GET de actividades resumidas por rango de fechas.
- fetch_daily_metrics: HRV nocturno, RHR, sueño, stress por día.
- fetch_training_status: carga diaria, fitness/fatiga si la API los expone.
- fetch_activity_detail: detalle por id (laps, series temporales) bajo demanda.

Mientras tanto, usar CorosMcpProvider (dumps del MCP) o FitFileProvider
(archivos FIT exportados) como fuentes reales.
"""

from __future__ import annotations

from datetime import date, datetime

from ..models import RawActivity, RawActivityDetail, RawDailyMetrics, RawTrainingStatus

_MSG = "CorosApiProvider no está implementado: requiere acceso oficial a la API de COROS (ver docstring)."


class CorosApiProvider:
    provider_name = "coros"
    provider_version = "api"

    def fetch_activities(self, start: datetime, end: datetime) -> list[RawActivity]:
        raise NotImplementedError(_MSG)

    def fetch_daily_metrics(self, start: date, end: date) -> list[RawDailyMetrics]:
        raise NotImplementedError(_MSG)

    def fetch_training_status(self, start: date, end: date) -> list[RawTrainingStatus]:
        raise NotImplementedError(_MSG)

    def fetch_activity_detail(self, activity_id: str) -> RawActivityDetail | None:
        raise NotImplementedError(_MSG)
