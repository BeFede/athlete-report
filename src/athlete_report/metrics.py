"""Cálculo de métricas: fitness/fatiga (EWMA), bloques 28d, baselines 28d.

Todo determinista, sin LLM.
"""

from __future__ import annotations

from datetime import date, timedelta
from typing import Any

from .config import BASELINE_WINDOW, BLOCK_WINDOW, FATIGUE_WINDOW, FITNESS_WINDOW


def _r(value: float | None, digits: int = 1) -> float | None:
    return None if value is None else round(float(value), digits)


def daily_load_series(
    activities: list[dict[str, Any]],
    training_status: list[dict[str, Any]],
) -> dict[date, float]:
    """Carga diaria: usa daily_load del training status si existe para ese día,
    si no, suma de training_load de actividades del día."""
    from_acts: dict[date, float] = {}
    for a in activities:
        if not a.get("local_date") or a.get("training_load") is None:
            continue
        d = date.fromisoformat(a["local_date"])
        from_acts[d] = from_acts.get(d, 0.0) + float(a["training_load"])
    series = dict(from_acts)
    for s in training_status:
        if not s.get("date") or s.get("daily_load") is None:
            continue
        d = date.fromisoformat(s["date"])
        series[d] = float(s["daily_load"])
    return series


def ewma_at(loads: dict[date, float], as_of: date, time_constant: float) -> float:
    """EWMA clásico de carga (CTL/ATL): v += (load - v) / tc, día a día desde
    el primer dato disponible. Días sin datos cuentan como carga 0."""
    if not loads:
        return 0.0
    first = min(loads)
    if first > as_of:
        return 0.0
    value = 0.0
    k = 1.0 / time_constant
    d = first
    while d <= as_of:
        value += (loads.get(d, 0.0) - value) * k
        d += timedelta(days=1)
    return value


def fitness_fatigue(loads: dict[date, float], as_of: date) -> dict[str, float | None]:
    if not loads or min(loads) > as_of:
        return {"fitness_42d": None, "fatigue_7d": None, "form": None}
    fitness = ewma_at(loads, as_of, FITNESS_WINDOW)
    fatigue = ewma_at(loads, as_of, FATIGUE_WINDOW)
    return {
        "fitness_42d": _r(fitness),
        "fatigue_7d": _r(fatigue),
        "form": _r(fitness - fatigue),
    }


def _window_totals(activities: list[dict[str, Any]], start: date, end: date) -> dict[str, Any]:
    sessions = 0
    sums: dict[str, float | None] = {"duration_s": None, "distance_m": None, "training_load": None}
    for a in activities:
        if not a.get("local_date"):
            continue
        d = date.fromisoformat(a["local_date"])
        if start <= d <= end:
            sessions += 1
            for field in sums:
                if a.get(field) is not None:
                    sums[field] = (sums[field] or 0.0) + float(a[field])
    return {
        "start": start.isoformat(),
        "end": end.isoformat(),
        "sessions": sessions,
        "duration_s": _r(sums["duration_s"]),
        "distance_m": _r(sums["distance_m"]),
        "training_load": _r(sums["training_load"]),
    }


def _delta_pct(current: float | None, previous: float | None) -> float | None:
    if current is None or previous is None or previous == 0:
        return None
    return round((current - previous) / previous * 100.0, 1)


def block_comparison(activities: list[dict[str, Any]], as_of: date) -> dict[str, Any]:
    """Bloque actual de 28 días vs bloque anterior de 28 días."""
    cur_start = as_of - timedelta(days=BLOCK_WINDOW - 1)
    prev_end = cur_start - timedelta(days=1)
    prev_start = prev_end - timedelta(days=BLOCK_WINDOW - 1)
    current = _window_totals(activities, cur_start, as_of)
    previous = _window_totals(activities, prev_start, prev_end)
    return {
        "current_28d": current,
        "previous_28d": previous,
        "delta_pct": {
            "sessions": _delta_pct(current["sessions"], previous["sessions"]),
            "duration_s": _delta_pct(current["duration_s"], previous["duration_s"]),
            "distance_m": _delta_pct(current["distance_m"], previous["distance_m"]),
            "training_load": _delta_pct(current["training_load"], previous["training_load"]),
        },
    }


def _mean_in_window(
    daily: list[dict[str, Any]], field: str, start: date, end: date
) -> float | None:
    values = []
    for m in daily:
        if not m.get("date") or m.get(field) is None:
            continue
        d = date.fromisoformat(m["date"])
        if start <= d <= end:
            values.append(float(m[field]))
    if not values:
        return None
    return sum(values) / len(values)


def baselines(daily: list[dict[str, Any]], as_of: date) -> dict[str, float | None]:
    start = as_of - timedelta(days=BASELINE_WINDOW - 1)
    return {
        "window_days": BASELINE_WINDOW,
        "hrv": _r(_mean_in_window(daily, "hrv", start, as_of)),
        "rhr": _r(_mean_in_window(daily, "rhr", start, as_of)),
        "sleep_duration_s": _r(_mean_in_window(daily, "sleep_duration_s", start, as_of), 0),
    }


def week_averages(daily: list[dict[str, Any]], week_start: date, week_end: date) -> dict[str, float | None]:
    return {
        "hrv": _r(_mean_in_window(daily, "hrv", week_start, week_end)),
        "rhr": _r(_mean_in_window(daily, "rhr", week_start, week_end)),
        "sleep_duration_s": _r(_mean_in_window(daily, "sleep_duration_s", week_start, week_end), 0),
    }
