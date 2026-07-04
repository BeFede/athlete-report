"""Proveedor COROS vía dumps crudos del MCP.

Modelo de operación: un cliente MCP (p.ej. Claude con el conector COROS)
descarga respuestas crudas y las deja como JSON en `data/raw/coros/`.
Este proveedor lee esos dumps, los mapea a modelos Raw* y filtra por ventana.
Así el CLI queda 100% determinista y sin dependencia de un LLM en runtime.

Formato de dump (un JSON por archivo):

    {
      "kind": "activities" | "daily_metrics" | "training_status" | "activity_detail",
      "provider": "coros",
      "fetched_at": "2026-07-03T10:00:00-03:00",
      "items": [ ...objetos nativos del MCP... ]
    }

Los archivos se procesan ordenados por nombre; ante ids/fechas repetidos gana
el último dump (permite correcciones tardías de COROS).
"""

from __future__ import annotations

import json
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

from ..config import tz
from ..models import RawActivity, RawActivityDetail, RawDailyMetrics, RawTrainingStatus

PROVIDER = "coros"


def _first(item: dict[str, Any], *keys: str) -> Any:
    for k in keys:
        if k in item and item[k] is not None:
            return item[k]
    return None


def _num(value: Any) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _parse_date(value: Any) -> date | None:
    if value is None:
        return None
    if isinstance(value, date) and not isinstance(value, datetime):
        return value
    if isinstance(value, int):  # formato COROS YYYYMMDD
        s = str(value)
        if len(s) == 8:
            return date(int(s[:4]), int(s[4:6]), int(s[6:8]))
        return None
    if isinstance(value, str):
        s = value.strip()
        if len(s) == 8 and s.isdigit():
            return date(int(s[:4]), int(s[4:6]), int(s[6:8]))
        try:
            return date.fromisoformat(s[:10])
        except ValueError:
            return None
    return None


def _parse_datetime(value: Any) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=tz())
    if isinstance(value, (int, float)):  # epoch en segundos o milisegundos
        ts = float(value)
        if ts > 1e12:
            ts /= 1000.0
        return datetime.fromtimestamp(ts, tz=timezone.utc).astimezone(tz())
    if isinstance(value, str):
        try:
            dt = datetime.fromisoformat(value)
            return dt if dt.tzinfo else dt.replace(tzinfo=tz())
        except ValueError:
            d = _parse_date(value)
            if d:
                return datetime(d.year, d.month, d.day, tzinfo=tz())
            return None
    return None


class CorosMcpProvider:
    provider_name = PROVIDER
    provider_version = "mcp"

    def __init__(self, raw_dir: Path):
        self.raw_dir = raw_dir
        self._cache: dict[str, list[dict[str, Any]]] = {}
        self._detail_index: dict[str, dict[str, Any]] | None = None

    # ------------------------------------------------------------------ raw
    def _items(self, kind: str) -> list[dict[str, Any]]:
        if kind in self._cache:
            return self._cache[kind]
        if not self.raw_dir.exists():
            return []
        items: list[dict[str, Any]] = []
        for path in sorted(self.raw_dir.glob("*.json")):
            try:
                payload = json.loads(path.read_text())
            except (json.JSONDecodeError, OSError):
                continue
            if isinstance(payload, dict) and payload.get("kind") == kind:
                batch = payload.get("items") or []
                if isinstance(batch, list):
                    items.extend(i for i in batch if isinstance(i, dict))
        self._cache[kind] = items
        return items

    # ------------------------------------------------------------ interface
    def fetch_activities(self, start: datetime, end: datetime) -> list[RawActivity]:
        by_id: dict[str, RawActivity] = {}
        for item in self._items("activities"):
            act = self._map_activity(item)
            if act is None or act.start_time is None:
                continue
            if start <= act.start_time <= end:
                by_id[act.external_activity_id] = act  # último dump gana
        return sorted(by_id.values(), key=lambda a: a.start_time or datetime.min.replace(tzinfo=tz()))

    def fetch_daily_metrics(self, start: date, end: date) -> list[RawDailyMetrics]:
        by_date: dict[date, RawDailyMetrics] = {}
        for item in self._items("daily_metrics"):
            m = self._map_daily(item)
            if m and start <= m.date <= end:
                by_date[m.date] = m
        return [by_date[d] for d in sorted(by_date)]

    def fetch_training_status(self, start: date, end: date) -> list[RawTrainingStatus]:
        by_date: dict[date, RawTrainingStatus] = {}
        for item in self._items("training_status"):
            s = self._map_status(item)
            if s and start <= s.date <= end:
                by_date[s.date] = s
        return [by_date[d] for d in sorted(by_date)]

    def fetch_activity_detail(self, activity_id: str) -> RawActivityDetail | None:
        if self._detail_index is None:
            self._detail_index = {}
            for item in self._items("activity_detail"):
                ext_id = _first(item, "external_activity_id", "activity_id", "activityId", "labelId", "id")
                if ext_id is not None:
                    self._detail_index[str(ext_id)] = item  # último dump gana
        item = self._detail_index.get(str(activity_id))
        if item is None:
            return None
        return RawActivityDetail(provider=PROVIDER, external_activity_id=str(activity_id), payload=item)

    # -------------------------------------------------------------- mapping
    def _map_activity(self, item: dict[str, Any]) -> RawActivity | None:
        ext_id = _first(item, "external_activity_id", "activity_id", "activityId", "labelId", "id")
        if ext_id is None:
            return None
        start_time = _parse_datetime(_first(item, "start_time", "startTime", "startTimestamp", "date"))
        local_date = start_time.date() if start_time else _parse_date(_first(item, "local_date", "date", "day"))
        return RawActivity(
            provider=PROVIDER,
            external_activity_id=str(ext_id),
            name=_first(item, "name", "label", "title"),
            sport=_first(item, "sport", "sportType", "mode", "type"),
            start_time=start_time,
            local_date=local_date,
            duration_s=_num(_first(item, "duration_s", "duration", "totalTime", "workoutTime")),
            distance_m=_num(_first(item, "distance_m", "distance")),
            avg_hr=_num(_first(item, "avg_hr", "avgHeartRate", "averageHr", "avgHr")),
            max_hr=_num(_first(item, "max_hr", "maxHeartRate", "maxHr")),
            training_load=_num(_first(item, "training_load", "trainingLoad", "tl", "load")),
            elevation_gain_m=_num(_first(item, "elevation_gain_m", "elevGain", "totalAscent", "ascent")),
            calories=_num(_first(item, "calories", "calorie", "kcal")),
            source_updated_at=_first(item, "updated_at", "updatedAt", "modifiedAt"),
        )

    def _map_daily(self, item: dict[str, Any]) -> RawDailyMetrics | None:
        d = _parse_date(_first(item, "date", "day", "dateStr", "happenDay"))
        if d is None:
            return None
        return RawDailyMetrics(
            provider=PROVIDER,
            date=d,
            hrv=_num(_first(item, "hrv", "sleepHrv", "avgHrv", "hrvValue")),
            rhr=_num(_first(item, "rhr", "resting_hr", "restingHeartRate", "restingHr")),
            sleep_duration_s=_num(_first(item, "sleep_duration_s", "sleepDuration", "totalSleepTime", "totalSleepDuration")),
            sleep_score=_num(_first(item, "sleep_score", "sleepScore")),
            stress_avg=_num(_first(item, "stress_avg", "avgStress", "stressAvg", "stress")),
            steps=_num(_first(item, "steps", "step", "totalSteps")),
        )

    def _map_status(self, item: dict[str, Any]) -> RawTrainingStatus | None:
        d = _parse_date(_first(item, "date", "day", "dateStr", "happenDay"))
        if d is None:
            return None
        return RawTrainingStatus(
            provider=PROVIDER,
            date=d,
            daily_load=_num(_first(item, "daily_load", "dailyLoad", "trainingLoad", "load")),
            fitness=_num(_first(item, "fitness", "ctl", "baseFitness")),
            fatigue=_num(_first(item, "fatigue", "atl")),
            status=_first(item, "status", "trainingStatus", "statusLabel"),
        )
