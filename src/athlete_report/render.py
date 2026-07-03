"""Render HTML desde snapshots congelados.

El contenido del reporte sale exclusivamente de report.json. La navegación
(prev/next/selector) se calcula sobre la lista de semanas disponibles al
momento de armar el sitio; el contenido de la semana no se recalcula nunca.
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Any

from jinja2 import Environment, PackageLoader, select_autoescape

MONTHS_ES = [
    "enero", "febrero", "marzo", "abril", "mayo", "junio",
    "julio", "agosto", "septiembre", "octubre", "noviembre", "diciembre",
]
DAYS_ES = ["lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo"]


def _env() -> Environment:
    return Environment(
        loader=PackageLoader("athlete_report", "templates"),
        autoescape=select_autoescape(["html", "j2"]),
    )


def fmt_date_long(d: date) -> str:
    return f"{d.day} de {MONTHS_ES[d.month - 1]} de {d.year}"


def fmt_week_title(week_start: date, week_end: date) -> str:
    if week_start.month == week_end.month and week_start.year == week_end.year:
        return (
            f"Semana del {week_start.day} al {week_end.day} "
            f"de {MONTHS_ES[week_end.month - 1]} de {week_end.year}"
        )
    return (
        f"Semana del {week_start.day} de {MONTHS_ES[week_start.month - 1]} "
        f"al {week_end.day} de {MONTHS_ES[week_end.month - 1]} de {week_end.year}"
    )


def fmt_week_short(week_start: date) -> str:
    return f"{week_start.day} {MONTHS_ES[week_start.month - 1][:3]} {week_start.year}"


def _fmt_ts_date(iso_ts: str | None) -> str:
    if not iso_ts:
        return "—"
    return fmt_date_long(datetime.fromisoformat(iso_ts).date())


def fmt_duration(seconds: float | None) -> str:
    if seconds is None:
        return "—"
    total = int(round(seconds))
    h, rem = divmod(total, 3600)
    m = rem // 60
    return f"{h} h {m:02d} min" if h else f"{m} min"


def fmt_km(meters: float | None) -> str:
    if meters is None:
        return "—"
    return f"{meters / 1000:.1f} km"


def _n(value: Any, suffix: str = "") -> str:
    if value is None:
        return "—"
    if isinstance(value, float) and value.is_integer():
        value = int(value)
    return f"{value}{suffix}"


def _sleep_h(seconds: float | None) -> str:
    if seconds is None:
        return "—"
    return f"{seconds / 3600:.1f} h"


def _delta_fmt(pct: float | None) -> tuple[str, str]:
    if pct is None:
        return "—", ""
    sign = "+" if pct > 0 else ""
    cls = "delta-pos" if pct > 0 else ("delta-neg" if pct < 0 else "")
    return f"{sign}{pct:.1f}%", cls


def _vs_baseline(week_val: float | None, base_val: float | None, fmt) -> str:
    wk = fmt(week_val)
    base = fmt(base_val)
    return f"{wk} (baseline {base})"


def build_nav(all_weeks: list[date], current: date) -> dict[str, Any]:
    """all_weeks ascendente; opciones del selector descendentes."""
    ordered = sorted(all_weeks)
    idx = ordered.index(current)
    return {
        "current": current.isoformat(),
        "prev": ordered[idx - 1].isoformat() if idx > 0 else None,
        "next": ordered[idx + 1].isoformat() if idx < len(ordered) - 1 else None,
        "latest": ordered[-1].isoformat(),
        "weeks": [
            {"value": w.isoformat(), "label": fmt_week_short(w)}
            for w in reversed(ordered)
        ],
    }


def render_report(snapshot: dict[str, Any], nav: dict[str, Any], meta: dict[str, Any] | None = None) -> str:
    week_start = date.fromisoformat(snapshot["week_start"])
    week_end = date.fromisoformat(snapshot["week_end"])
    rd = snapshot["report_data"]
    totals = rd["totals"]
    fit = rd["fitness"]

    def day_label(iso: str) -> str:
        d = date.fromisoformat(iso)
        return f"{DAYS_ES[d.weekday()][:3].capitalize()} {d.day}"

    activities = [
        {
            "day": day_label(a["date"]) if a.get("date") else "—",
            "name": a.get("name") or "Actividad",
            "sport": a.get("sport") or "—",
            "duration": fmt_duration(a.get("duration_s")),
            "distance": fmt_km(a.get("distance_m")),
            "avg_hr": _n(a.get("avg_hr")),
            "load": _n(a.get("training_load")),
        }
        for a in rd["activities"]
    ]

    load_by_day = rd.get("load_by_day", {})
    max_load = max(load_by_day.values(), default=0) or 1
    daily_load = [
        {"day": day_label(d), "load": _n(v), "pct": round(v / max_load * 100)}
        for d, v in sorted(load_by_day.items())
    ]

    daily_rows = [
        {
            "day": day_label(m["date"]),
            "hrv": _n(m.get("hrv")),
            "rhr": _n(m.get("rhr")),
            "sleep": _sleep_h(m.get("sleep_duration_s")),
            "sleep_score": _n(m.get("sleep_score")),
        }
        for m in rd["daily"]
    ]

    base = rd["baselines_28d"]
    wk = rd["week_averages"]
    wk_vs = {
        "hrv": _vs_baseline(wk.get("hrv"), base.get("hrv"), _n),
        "rhr": _vs_baseline(wk.get("rhr"), base.get("rhr"), _n),
        "sleep": _vs_baseline(wk.get("sleep_duration_s"), base.get("sleep_duration_s"), _sleep_h),
    }

    bc = rd["block_comparison"]
    cur, prev, delta = bc["current_28d"], bc["previous_28d"], bc["delta_pct"]
    block_rows = []
    for label, field, fmt in (
        ("Sesiones", "sessions", _n),
        ("Tiempo", "duration_s", fmt_duration),
        ("Distancia", "distance_m", fmt_km),
        ("Carga", "training_load", _n),
    ):
        d_txt, d_cls = _delta_fmt(delta.get(field))
        block_rows.append(
            {
                "label": label,
                "current": fmt(cur.get(field)),
                "previous": fmt(prev.get(field)),
                "delta": d_txt,
                "delta_class": d_cls,
            }
        )

    cov = snapshot.get("coverage", {})
    coverage_line = (
        f"actividades {cov.get('activity_days', 0)}/7 días · "
        f"HRV {cov.get('hrv_days', 0)}/7 · sueño {cov.get('sleep_days', 0)}/7 · "
        f"FC reposo {cov.get('rhr_days', 0)}/7"
    )
    providers_line = ", ".join(
        f"{name} ({version})" for name, version in sorted(snapshot.get("provider_versions", {}).items())
    ) or "—"

    meta = meta or {}
    template = _env().get_template("report.html.j2")
    return template.render(
        week_title=fmt_week_title(week_start, week_end),
        generated_on=_fmt_ts_date(snapshot.get("generated_at")),
        data_as_of_on=_fmt_ts_date(snapshot.get("data_as_of")),
        rebuilt_on=_fmt_ts_date(meta["rebuilt_at"]) if meta.get("rebuilt_at") else None,
        nav=nav,
        totals={
            "sessions": totals.get("sessions", 0),
            "duration": fmt_duration(totals.get("duration_s")),
            "distance": fmt_km(totals.get("distance_m")),
            "load": _n(totals.get("training_load")),
        },
        fitness={
            "fitness": _n(fit.get("fitness_42d")),
            "fatigue": _n(fit.get("fatigue_7d")),
            "form": _n(fit.get("form")),
        },
        activities=activities,
        daily_load=daily_load,
        daily_rows=daily_rows,
        wk_vs=wk_vs,
        block_rows=block_rows,
        coverage_line=coverage_line,
        providers_line=providers_line,
        schema_version=f"schema {snapshot.get('schema_version', '?')}",
    )


def render_archive(entries: list[dict[str, Any]], latest: date) -> str:
    """entries: [{week_start: date, generated_at: iso, rebuilt_at: iso|None}] desc."""
    template = _env().get_template("archive.html.j2")
    view = [
        {
            "value": e["week_start"].isoformat(),
            "label": fmt_week_title(e["week_start"], e["week_end"]),
            "generated_on": _fmt_ts_date(e.get("generated_at")),
            "rebuilt_on": _fmt_ts_date(e["rebuilt_at"]) if e.get("rebuilt_at") else None,
        }
        for e in entries
    ]
    return template.render(entries=view, latest=latest.isoformat())


def render_redirect(latest: date) -> str:
    return _env().get_template("redirect.html.j2").render(latest=latest.isoformat())


def render_unpublished() -> str:
    return _env().get_template("unpublished.html.j2").render()
