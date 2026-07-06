"""Construcción y persistencia de snapshots semanales congelados.

Cada semana tiene data/reports/YYYY-MM-DD/report.json (lunes de la semana).
El HTML se renderiza SIEMPRE desde el snapshot, nunca desde datos actuales.
Los snapshots cerrados no se modifican salvo --overwrite o rebuild explícito.
"""

from __future__ import annotations

import json
from datetime import date, datetime, timedelta
from typing import Any

from .config import SCHEMA_VERSION, ProjectPaths
from .metrics import (
    baselines,
    block_comparison,
    daily_load_series,
    fitness_fatigue,
    week_averages,
)
from .storage import Store
from .weeks import week_end_for


class SnapshotExistsError(Exception):
    """Ya existe un snapshot para esa semana y no se pidió --overwrite."""


def _week_rows(rows: list[dict[str, Any]], date_field: str, start: date, end: date) -> list[dict[str, Any]]:
    out = []
    for r in rows:
        if not r.get(date_field):
            continue
        d = date.fromisoformat(str(r[date_field])[:10])
        if start <= d <= end:
            out.append(r)
    return out


def _coverage(week_activities, week_daily, week_start: date) -> dict[str, int]:
    activity_days = len({a["local_date"] for a in week_activities if a.get("local_date")})

    def days_with(field: str) -> int:
        return len({m["date"] for m in week_daily if m.get(field) is not None})

    return {
        "activity_days": activity_days,
        "hrv_days": days_with("hrv"),
        "sleep_days": days_with("sleep_duration_s"),
        "rhr_days": days_with("rhr"),
    }


DETAIL_PUBLIC_FIELDS = (
    "training_load", "elevation_gain_m", "elevation_loss_m", "aerobic_te",
    "anaerobic_te", "training_focus", "avg_power_w", "avg_cadence_spm",
    "adjusted_pace_s", "best_km_s", "splits", "workout_laps",
)


def _activity_public(a: dict[str, Any], detail: dict[str, Any] | None) -> dict[str, Any]:
    """Campos que van al reporte. Nunca coordenadas ni payloads crudos."""
    out = {
        "date": a.get("local_date"),
        "name": a.get("name"),
        "sport": a.get("sport"),
        "duration_s": a.get("duration_s"),
        "distance_m": a.get("distance_m"),
        "avg_hr": a.get("avg_hr"),
        "max_hr": a.get("max_hr"),
        "training_load": a.get("training_load"),
        "elevation_gain_m": a.get("elevation_gain_m"),
    }
    if detail:
        out["detail"] = {
            k: detail.get(k) for k in DETAIL_PUBLIC_FIELDS if detail.get(k) not in (None, [], {})
        }
    return out


LATEST_RECOVERY_MAX_LAG_DAYS = 3


def _latest_recovery_after(daily: list[dict[str, Any]], week_end: date) -> dict[str, Any] | None:
    """Métrica diaria más reciente posterior al cierre de la semana.

    No forma parte de la semana (que sigue Mon-Dom, congelada); es un dato
    suelto de recuperación para cuando el reporte se envía pocos días después
    del cierre y ya hay una noche más de HRV/sueño registrada. Acotado a unos
    pocos días de margen: si se reconstruye una semana vieja mucho después,
    no debe aparecer el dato de "hoy" como si fuera reciente.
    """
    lag_limit = week_end + timedelta(days=LATEST_RECOVERY_MAX_LAG_DAYS)
    candidates = [
        m for m in daily
        if m.get("date") and week_end < date.fromisoformat(m["date"]) <= lag_limit
    ]
    if not candidates:
        return None
    latest = max(candidates, key=lambda m: m["date"])
    if latest.get("hrv") is None and latest.get("rhr") is None and latest.get("sleep_duration_s") is None:
        return None
    return {
        "date": latest["date"],
        "hrv": latest.get("hrv"),
        "rhr": latest.get("rhr"),
        "sleep_duration_s": latest.get("sleep_duration_s"),
    }


def _fitness_for_week(
    status: list[dict[str, Any]], loads: dict, week_end: date
) -> dict[str, Any]:
    """Fitness/fatiga al cierre de semana.

    Preferir los valores oficiales del proveedor (COROS: long/short-term load)
    si existen para ese día; si no, EWMA propio (42 d / 7 d) sobre carga diaria.
    """
    row = next((s for s in status if s.get("date") == week_end.isoformat()), None)
    if row and row.get("fitness") is not None and row.get("fatigue") is not None:
        fitness = float(row["fitness"])
        fatigue = float(row["fatigue"])
        return {
            "fitness_42d": round(fitness, 1),
            "fatigue_7d": round(fatigue, 1),
            "form": round(fitness - fatigue, 1),
            "status": row.get("status"),
            "source": "provider",
        }
    computed = fitness_fatigue(loads, week_end)
    computed["status"] = None
    computed["source"] = "computed"
    return computed


def build_snapshot(
    store: Store,
    week_start: date,
    generated_at: datetime,
    data_as_of: str,
    provider_versions: dict[str, str],
) -> dict[str, Any]:
    week_end = week_end_for(week_start)
    activities = store.load_activities()
    daily = store.load_daily_metrics()
    status = store.load_training_status()

    week_acts = sorted(
        _week_rows(activities, "local_date", week_start, week_end),
        key=lambda a: (a.get("start_time") or "", a.get("external_activity_id") or ""),
    )
    week_daily = sorted(_week_rows(daily, "date", week_start, week_end), key=lambda m: m["date"])

    loads = daily_load_series(activities, status)
    load_by_day = {d.isoformat(): round(v, 1) for d, v in sorted(loads.items()) if week_start <= d <= week_end}

    def _sum_or_none(field: str) -> float | None:
        values = [float(a[field]) for a in week_acts if a.get(field) is not None]
        return round(sum(values), 1) if values else None

    totals = {
        "sessions": len(week_acts),
        "duration_s": _sum_or_none("duration_s"),
        "distance_m": _sum_or_none("distance_m"),
        "training_load": _sum_or_none("training_load"),
        "elevation_gain_m": _sum_or_none("elevation_gain_m"),
    }

    by_sport: dict[str, dict[str, Any]] = {}
    for a in week_acts:
        sport = a.get("sport") or "otro"
        agg = by_sport.setdefault(sport, {"sessions": 0, "duration_s": 0.0, "distance_m": 0.0, "training_load": 0.0})
        agg["sessions"] += 1
        agg["duration_s"] = round(agg["duration_s"] + float(a.get("duration_s") or 0), 1)
        agg["distance_m"] = round(agg["distance_m"] + float(a.get("distance_m") or 0), 1)
        agg["training_load"] = round(agg["training_load"] + float(a.get("training_load") or 0), 1)

    report_data = {
        "totals": totals,
        "by_sport": by_sport,
        "activities": [
            _activity_public(a, store.load_detail(a["provider"], a["external_activity_id"]))
            for a in week_acts
        ],
        "daily": [
            {
                "date": m["date"],
                "hrv": m.get("hrv"),
                "rhr": m.get("rhr"),
                "sleep_duration_s": m.get("sleep_duration_s"),
                "sleep_score": m.get("sleep_score"),
                "training_load": load_by_day.get(m["date"]),
            }
            for m in week_daily
        ],
        "load_by_day": load_by_day,
        "fitness": _fitness_for_week(status, loads, week_end),
        "block_comparison": block_comparison(activities, week_end),
        "baselines_28d": baselines(daily, week_end),
        "week_averages": week_averages(daily, week_start, week_end),
        "latest_recovery": _latest_recovery_after(daily, week_end),
    }

    return {
        "schema_version": SCHEMA_VERSION,
        "week_start": week_start.isoformat(),
        "week_end": week_end.isoformat(),
        "generated_at": generated_at.isoformat(),
        "data_as_of": data_as_of,
        "provider_versions": provider_versions,
        "coverage": _coverage(week_acts, week_daily, week_start),
        "report_data": report_data,
    }


def _dump(obj: dict[str, Any]) -> str:
    return json.dumps(obj, indent=2, ensure_ascii=False, sort_keys=True) + "\n"


def snapshot_exists(paths: ProjectPaths, week_start: date) -> bool:
    return paths.report_json(week_start).exists()


def load_snapshot(paths: ProjectPaths, week_start: date) -> dict[str, Any]:
    return json.loads(paths.report_json(week_start).read_text())


def load_meta(paths: ProjectPaths, week_start: date) -> dict[str, Any]:
    p = paths.report_meta(week_start)
    return json.loads(p.read_text()) if p.exists() else {}


def write_snapshot(
    paths: ProjectPaths,
    snapshot: dict[str, Any],
    *,
    overwrite: bool = False,
    rebuild: bool = False,
    rebuilt_at: str | None = None,
    rebuild_reason: str | None = None,
) -> None:
    """Persiste snapshot + meta.

    - Sin overwrite/rebuild: falla si ya existe (reportes cerrados congelados).
    - rebuild: conserva generated_at original y registra rebuilt_at/reason.
    """
    week_start = date.fromisoformat(snapshot["week_start"])
    report_path = paths.report_json(week_start)
    exists = report_path.exists()

    if exists and not (overwrite or rebuild):
        raise SnapshotExistsError(
            f"Ya existe snapshot para {week_start}; usar --overwrite o rebuild explícito."
        )

    if rebuild and exists:
        # conservar generated_at original y registrar la reconstrucción
        meta = load_meta(paths, week_start)
        original_generated_at = meta.get("generated_at") or load_snapshot(paths, week_start).get("generated_at")
        if original_generated_at:
            snapshot = dict(snapshot)
            snapshot["generated_at"] = original_generated_at
        meta["rebuilt_at"] = rebuilt_at or snapshot["data_as_of"]
        meta["rebuild_reason"] = rebuild_reason or "manual"
        meta["generated_at"] = snapshot["generated_at"]
    else:
        # generación fresca u overwrite explícito: meta nueva
        meta = {}
        meta["generated_at"] = snapshot["generated_at"]

    meta["schema_version"] = snapshot["schema_version"]
    meta["week_start"] = snapshot["week_start"]
    meta["week_end"] = snapshot["week_end"]
    meta["data_as_of"] = snapshot["data_as_of"]

    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(_dump(snapshot))
    paths.report_meta(week_start).write_text(_dump(meta))


def list_snapshot_weeks(paths: ProjectPaths) -> list[date]:
    if not paths.reports.exists():
        return []
    weeks = []
    for child in sorted(paths.reports.iterdir()):
        if child.is_dir() and (child / "report.json").exists():
            try:
                weeks.append(date.fromisoformat(child.name))
            except ValueError:
                continue
    return weeks
