"""FitFileProvider: importa actividades desde archivos FIT locales.

Fallback portable entre marcas: cualquier reloj que exporte FIT sirve.
Lee `*.fit` de un directorio (por defecto data/raw/fit/). Requiere el extra
opcional `fit` (fitdecode):

    uv sync --extra fit

Sólo actividades (mensaje `session`). No provee métricas diarias ni status.
"""

from __future__ import annotations

from datetime import date, datetime
from pathlib import Path

from ..config import tz
from ..models import RawActivity, RawActivityDetail, RawDailyMetrics, RawTrainingStatus


class FitFileProvider:
    provider_name = "fit"
    provider_version = "local"

    def __init__(self, fit_dir: Path):
        self.fit_dir = fit_dir

    def _fitdecode(self):
        try:
            import fitdecode  # noqa: PLC0415
        except ImportError as exc:
            raise RuntimeError(
                "FitFileProvider requiere fitdecode. Instalar con: uv sync --extra fit"
            ) from exc
        return fitdecode

    def _parse_session(self, path: Path) -> RawActivity | None:
        fitdecode = self._fitdecode()
        fields: dict[str, object] = {}
        with fitdecode.FitReader(path) as reader:
            for frame in reader:
                if isinstance(frame, fitdecode.FitDataMessage) and frame.name == "session":
                    for f in frame.fields:
                        fields[f.name] = f.value
                    break
        start = fields.get("start_time")
        if isinstance(start, datetime):
            start = start.astimezone(tz())
        else:
            start = None
        return RawActivity(
            provider=self.provider_name,
            external_activity_id=path.stem,
            name=path.stem,
            sport=str(fields.get("sport")) if fields.get("sport") is not None else None,
            start_time=start,
            local_date=start.date() if start else None,
            duration_s=_maybe_float(fields.get("total_timer_time")),
            distance_m=_maybe_float(fields.get("total_distance")),
            avg_hr=_maybe_float(fields.get("avg_heart_rate")),
            max_hr=_maybe_float(fields.get("max_heart_rate")),
            training_load=_maybe_float(fields.get("training_load_peak")),
            elevation_gain_m=_maybe_float(fields.get("total_ascent")),
            calories=_maybe_float(fields.get("total_calories")),
            source_updated_at=None,
        )

    def fetch_activities(self, start: datetime, end: datetime) -> list[RawActivity]:
        if not self.fit_dir.exists():
            return []
        out = []
        for path in sorted(self.fit_dir.glob("*.fit")):
            act = self._parse_session(path)
            if act and act.start_time and start <= act.start_time <= end:
                out.append(act)
        return out

    def fetch_daily_metrics(self, start: date, end: date) -> list[RawDailyMetrics]:
        return []

    def fetch_training_status(self, start: date, end: date) -> list[RawTrainingStatus]:
        return []

    def fetch_activity_detail(self, activity_id: str) -> RawActivityDetail | None:
        return None


def _maybe_float(value: object) -> float | None:
    if value is None:
        return None
    try:
        return float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None
