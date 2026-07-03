"""Persistencia de datos normalizados canónicos (parquet) y sync_state.

Upsert idempotente:
- actividades por (provider, external_activity_id)
- métricas diarias por (provider, date)
- training status por (provider, date)
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Any

import pandas as pd

from .config import ProjectPaths
from .models import RawActivity, RawDailyMetrics, RawTrainingStatus

ACTIVITY_COLUMNS = [
    "provider",
    "external_activity_id",
    "name",
    "sport",
    "start_time",
    "local_date",
    "duration_s",
    "distance_m",
    "avg_hr",
    "max_hr",
    "training_load",
    "elevation_gain_m",
    "calories",
    "source_updated_at",
    "ingested_at",
]

DAILY_COLUMNS = [
    "provider",
    "date",
    "hrv",
    "rhr",
    "sleep_duration_s",
    "sleep_score",
    "stress_avg",
    "steps",
    "ingested_at",
]

STATUS_COLUMNS = [
    "provider",
    "date",
    "daily_load",
    "fitness",
    "fatigue",
    "status",
    "ingested_at",
]


def _clean(value: Any) -> Any:
    """NaN/NaT/numpy -> tipos python planos, None para faltantes."""
    if value is None:
        return None
    if isinstance(value, float) and pd.isna(value):
        return None
    if pd.api.types.is_scalar(value) and pd.isna(value):
        return None
    if hasattr(value, "item"):
        return value.item()
    return value


def _same(a: Any, b: Any) -> bool:
    a, b = _clean(a), _clean(b)
    if a is None and b is None:
        return True
    if isinstance(a, (int, float)) and isinstance(b, (int, float)):
        return float(a) == float(b)
    return a == b


@dataclass
class UpsertResult:
    inserted: int = 0
    updated: int = 0
    unchanged: int = 0

    def __str__(self) -> str:
        return f"{self.inserted} nuevas, {self.updated} actualizadas, {self.unchanged} sin cambios"


class Store:
    """Acceso a los parquet normalizados. Filas como dicts planos (fechas ISO string)."""

    def __init__(self, paths: ProjectPaths):
        self.paths = paths

    # ------------------------------------------------------------------ util
    def _load(self, path: Path, columns: list[str]) -> list[dict[str, Any]]:
        if not path.exists():
            return []
        df = pd.read_parquet(path)
        rows = []
        for rec in df.to_dict(orient="records"):
            rows.append({c: _clean(rec.get(c)) for c in columns})
        return rows

    def _write(self, path: Path, rows: list[dict[str, Any]], columns: list[str]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        df = pd.DataFrame(rows, columns=columns)
        df.to_parquet(path, index=False)

    def _upsert(
        self,
        path: Path,
        columns: list[str],
        key_fields: tuple[str, ...],
        records: list[dict[str, Any]],
        ingested_at: str,
    ) -> UpsertResult:
        rows = self._load(path, columns)
        index = {tuple(r[k] for k in key_fields): i for i, r in enumerate(rows)}
        result = UpsertResult()
        compare_fields = [c for c in columns if c != "ingested_at"]
        for rec in records:
            rec = dict(rec)
            rec["ingested_at"] = ingested_at
            key = tuple(rec[k] for k in key_fields)
            if key in index:
                current = rows[index[key]]
                if all(_same(current.get(f), rec.get(f)) for f in compare_fields):
                    result.unchanged += 1
                else:
                    # la fuente corrigió datos: actualizar fila existente
                    rows[index[key]] = rec
                    result.updated += 1
            else:
                index[key] = len(rows)
                rows.append(rec)
                result.inserted += 1
        if records or rows:
            self._write(path, rows, columns)
        return result

    # ------------------------------------------------------------ activities
    def load_activities(self) -> list[dict[str, Any]]:
        return self._load(self.paths.activities_parquet, ACTIVITY_COLUMNS)

    def upsert_activities(self, items: list[RawActivity], ingested_at: str) -> UpsertResult:
        records = []
        for a in items:
            records.append(
                {
                    "provider": a.provider,
                    "external_activity_id": str(a.external_activity_id),
                    "name": a.name,
                    "sport": a.sport,
                    "start_time": a.start_time.isoformat() if a.start_time else None,
                    "local_date": a.local_date.isoformat() if a.local_date else None,
                    "duration_s": a.duration_s,
                    "distance_m": a.distance_m,
                    "avg_hr": a.avg_hr,
                    "max_hr": a.max_hr,
                    "training_load": a.training_load,
                    "elevation_gain_m": a.elevation_gain_m,
                    "calories": a.calories,
                    "source_updated_at": a.source_updated_at,
                }
            )
        return self._upsert(
            self.paths.activities_parquet,
            ACTIVITY_COLUMNS,
            ("provider", "external_activity_id"),
            records,
            ingested_at,
        )

    # --------------------------------------------------------- daily metrics
    def load_daily_metrics(self) -> list[dict[str, Any]]:
        return self._load(self.paths.daily_metrics_parquet, DAILY_COLUMNS)

    def upsert_daily_metrics(self, items: list[RawDailyMetrics], ingested_at: str) -> UpsertResult:
        records = []
        for m in items:
            records.append(
                {
                    "provider": m.provider,
                    "date": m.date.isoformat(),
                    "hrv": m.hrv,
                    "rhr": m.rhr,
                    "sleep_duration_s": m.sleep_duration_s,
                    "sleep_score": m.sleep_score,
                    "stress_avg": m.stress_avg,
                    "steps": m.steps,
                }
            )
        return self._upsert(
            self.paths.daily_metrics_parquet,
            DAILY_COLUMNS,
            ("provider", "date"),
            records,
            ingested_at,
        )

    # ------------------------------------------------------- training status
    def load_training_status(self) -> list[dict[str, Any]]:
        return self._load(self.paths.training_status_parquet, STATUS_COLUMNS)

    def upsert_training_status(self, items: list[RawTrainingStatus], ingested_at: str) -> UpsertResult:
        records = []
        for s in items:
            records.append(
                {
                    "provider": s.provider,
                    "date": s.date.isoformat(),
                    "daily_load": s.daily_load,
                    "fitness": s.fitness,
                    "fatigue": s.fatigue,
                    "status": s.status,
                }
            )
        return self._upsert(
            self.paths.training_status_parquet,
            STATUS_COLUMNS,
            ("provider", "date"),
            records,
            ingested_at,
        )

    # ------------------------------------------------------------ sync state
    def read_sync_state(self) -> dict[str, Any]:
        if not self.paths.sync_state.exists():
            return {}
        return json.loads(self.paths.sync_state.read_text())

    def write_sync_state(self, state: dict[str, Any]) -> None:
        self.paths.sync_state.parent.mkdir(parents=True, exist_ok=True)
        self.paths.sync_state.write_text(json.dumps(state, indent=2, ensure_ascii=False) + "\n")
