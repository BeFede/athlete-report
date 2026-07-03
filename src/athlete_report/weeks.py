"""Cálculo de semanas (lunes a domingo)."""

from __future__ import annotations

from datetime import date, timedelta


def week_start_for(d: date) -> date:
    """Lunes de la semana que contiene `d`."""
    return d - timedelta(days=d.weekday())


def week_end_for(week_start: date) -> date:
    """Domingo de la semana que empieza en `week_start`."""
    return week_start + timedelta(days=6)


def is_monday(d: date) -> bool:
    return d.weekday() == 0


def last_complete_week_start(today: date) -> date:
    """Lunes de la última semana completa.

    Una semana está completa cuando su domingo es estrictamente anterior a hoy
    (el domingo en curso todavía no terminó).
    """
    current = week_start_for(today)
    prev = current - timedelta(days=7)
    if week_end_for(current) < today:  # imposible por definición, defensivo
        return current
    return prev


def mondays_between(from_week: date, to_week: date) -> list[date]:
    """Lunes consecutivos en [from_week, to_week], ambos inclusive."""
    if not is_monday(from_week) or not is_monday(to_week):
        raise ValueError("from/to deben ser lunes (YYYY-MM-DD)")
    if from_week > to_week:
        raise ValueError("--from debe ser <= --to")
    out = []
    d = from_week
    while d <= to_week:
        out.append(d)
        d += timedelta(days=7)
    return out


def bootstrap_range(history_weeks: int, today: date, warmup_days: int) -> tuple[date, date, list[date]]:
    """(data_start, data_end, semanas) para bootstrap.

    Descarga history_weeks*7 + warmup_days días para que la semana más vieja
    tenga fitness/baselines/bloques correctos.
    """
    if history_weeks < 1:
        raise ValueError("--history-weeks debe ser >= 1")
    last = last_complete_week_start(today)
    first = last - timedelta(days=7 * (history_weeks - 1))
    data_start = first - timedelta(days=warmup_days)
    data_end = week_end_for(last)
    weeks = mondays_between(first, last)
    return data_start, data_end, weeks
