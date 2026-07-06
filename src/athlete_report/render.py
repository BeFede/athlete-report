"""Render HTML desde snapshots congelados.

El contenido del reporte sale exclusivamente de report.json. La navegación
(prev/next/selector) se calcula sobre la lista de semanas disponibles al
momento de armar el sitio; el contenido de la semana no se recalcula nunca.

Los gráficos son SVG inline generados acá (determinista, sin JS ni CDNs).
Las coordenadas SVG se redondean a 1 decimal: además de compactar, evita
falsos positivos del validador de privacidad (pares de decimales largos).
"""

from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Any, Callable

from jinja2 import Environment, PackageLoader, select_autoescape
from markupsafe import Markup

MONTHS_ES = [
    "enero", "febrero", "marzo", "abril", "mayo", "junio",
    "julio", "agosto", "septiembre", "octubre", "noviembre", "diciembre",
]
DAYS_ES = ["lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo"]

SPORT_LABELS = {
    "run": "Ruta",
    "trail_run": "Trail",
    "indoor_run": "Cinta",
    "track_run": "Pista",
    "hike": "Trekking",
    "strength": "Fuerza",
}


def _env() -> Environment:
    return Environment(
        loader=PackageLoader("athlete_report", "templates"),
        autoescape=select_autoescape(["html", "j2"]),
    )


# ------------------------------------------------------------------ formato
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


def _num1(value: float) -> str:
    """Número compacto para etiquetas de gráfico: sin .0 redundante."""
    if float(value).is_integer():
        return str(int(value))
    return f"{value:.1f}"


def _sleep_h(seconds: float | None) -> str:
    if seconds is None:
        return "—"
    return f"{seconds / 3600:.1f} h"


def fmt_pace(seconds: float | None) -> str:
    if not seconds:
        return "—"
    total = int(round(seconds))
    return f"{total // 60}:{total % 60:02d}"


def _elev(gain: float | None, loss: float | None = None) -> str:
    if gain is None and loss is None:
        return "—"
    parts = []
    if gain is not None:
        parts.append(f"+{int(round(gain))}")
    if loss is not None:
        parts.append(f"-{int(round(loss))}")
    return "/".join(parts) + " m"


def _delta_fmt(pct: float | None) -> tuple[str, str]:
    if pct is None:
        return "—", ""
    sign = "+" if pct > 0 else ""
    cls = "delta-pos" if pct > 0 else ("delta-neg" if pct < 0 else "")
    return f"{sign}{pct:.1f}%", cls


def _vs_baseline(week_val: float | None, base_val: float | None, fmt) -> str:
    return f"{fmt(week_val)} (baseline {fmt(base_val)})"


# ------------------------------------------------------------------- charts
CHART_W = 600
CHART_H = 190
PAD_TOP = 22
PAD_BOTTOM = 26
PAD_X = 8


def _plot_area() -> tuple[float, float]:
    return CHART_H - PAD_TOP - PAD_BOTTOM, CHART_W - 2 * PAD_X


def _svg_open(title: str) -> str:
    return (
        f'<svg class="chart" viewBox="0 0 {CHART_W} {CHART_H}" role="img" '
        f'aria-label="{title}" preserveAspectRatio="xMidYMid meet">'
    )


def _baseline_svg(y: float) -> str:
    # sólo línea punteada; el subtítulo del gráfico explica qué es
    return f'<line x1="{PAD_X}" y1="{y:.1f}" x2="{CHART_W - PAD_X}" y2="{y:.1f}" class="chart-baseline"/>'


def bar_chart(
    points: list[tuple[str, float | None]],
    *,
    title: str,
    value_fmt: Callable[[float], str] = _num1,
    baseline: float | None = None,
    extra_point: tuple[str, float | None] | None = None,
) -> Markup | None:
    """Barras por día. points: [(etiqueta, valor|None)]. None = sin barra.

    extra_point: un punto adicional fuera de la semana (p.ej. "hoy"), pintado
    con un color distinto para dejar claro que no forma parte del cierre
    semanal congelado.
    """
    all_points = list(points) + ([extra_point] if extra_point else [])
    extra_index = len(points) if extra_point else None
    values = [v for _, v in all_points if v is not None]
    if not values:
        return None
    plot_h, plot_w = _plot_area()
    vmax = max(max(values), baseline or 0) or 1
    slot = plot_w / len(all_points)
    bar_w = slot * 0.6
    parts = [_svg_open(title)]
    for i, (label, value) in enumerate(all_points):
        cx = PAD_X + slot * i + slot / 2
        is_extra = i == extra_index
        axis_cls = "chart-axis chart-axis-extra" if is_extra else "chart-axis"
        parts.append(
            f'<text x="{cx:.1f}" y="{CHART_H - 8}" class="{axis_cls}" text-anchor="middle">{label}</text>'
        )
        if value is None:
            continue
        h = value / vmax * plot_h
        y = PAD_TOP + plot_h - h
        bar_cls = "chart-bar chart-bar-extra" if is_extra else "chart-bar"
        parts.append(
            f'<rect x="{cx - bar_w / 2:.1f}" y="{y:.1f}" width="{bar_w:.1f}" height="{h:.1f}" rx="4" class="{bar_cls}"/>'
            f'<text x="{cx:.1f}" y="{y - 5:.1f}" class="chart-value" text-anchor="middle">{value_fmt(value)}</text>'
        )
    if baseline is not None and baseline > 0:
        y = PAD_TOP + plot_h - (baseline / vmax * plot_h)
        parts.append(_baseline_svg(y))
    parts.append("</svg>")
    return Markup("".join(parts))


def line_chart(
    points: list[tuple[str, float | None]],
    *,
    title: str,
    value_fmt: Callable[[float], str] = _num1,
    baseline: float | None = None,
    series2: list[float | None] | None = None,
    legend: tuple[str, str] | None = None,
    extra_point: tuple[str, float | None] | None = None,
) -> Markup | None:
    """Línea por día (con serie secundaria opcional). None = hueco.

    extra_point: un punto adicional fuera de la semana (p.ej. "hoy"), unido
    por un segmento punteado y pintado con un color distinto.
    """
    values = [v for _, v in points if v is not None]
    series2_vals = [v for v in (series2 or []) if v is not None]
    if not values:
        return None
    extra_index = len(points) if extra_point else None
    all_points = list(points) + ([extra_point] if extra_point else [])
    plot_h, plot_w = _plot_area()
    all_vals = values + series2_vals + ([baseline] if baseline is not None else [])
    if extra_point is not None and extra_point[1] is not None:
        all_vals.append(extra_point[1])
    vmin, vmax = min(all_vals), max(all_vals)
    span = (vmax - vmin) or 1
    vmin -= span * 0.15
    vmax += span * 0.15
    slot = plot_w / len(all_points)

    def xy(i: int, v: float) -> tuple[float, float]:
        x = PAD_X + slot * i + slot / 2
        y = PAD_TOP + (vmax - v) / (vmax - vmin) * plot_h
        return x, y

    def series_svg(vals: list[float | None], cls: str, with_labels: bool) -> str:
        segs, seg = [], []
        for i, v in enumerate(vals):
            if v is None:
                if seg:
                    segs.append(seg)
                    seg = []
                continue
            seg.append(xy(i, v))
        if seg:
            segs.append(seg)
        out = []
        for s in segs:
            if len(s) > 1:
                pts = " ".join(f"{x:.1f},{y:.1f}" for x, y in s)
                out.append(f'<polyline points="{pts}" class="{cls}"/>')
            for x, y in s:
                out.append(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="3" class="{cls}-dot"/>')
        if with_labels:
            for i, v in enumerate(vals):
                if v is not None:
                    x, y = xy(i, v)
                    out.append(
                        f'<text x="{x:.1f}" y="{y - 8:.1f}" class="chart-value" text-anchor="middle">{value_fmt(v)}</text>'
                    )
        return "".join(out)

    parts = [_svg_open(title)]
    for i, (label, _) in enumerate(all_points):
        cx = PAD_X + slot * i + slot / 2
        axis_cls = "chart-axis chart-axis-extra" if i == extra_index else "chart-axis"
        parts.append(
            f'<text x="{cx:.1f}" y="{CHART_H - 8}" class="{axis_cls}" text-anchor="middle">{label}</text>'
        )
    if baseline is not None:
        y = PAD_TOP + (vmax - baseline) / (vmax - vmin) * plot_h
        parts.append(_baseline_svg(y))
    if series2 is not None:
        parts.append(series_svg(list(series2), "chart-line2", False))
    parts.append(series_svg([v for _, v in points], "chart-line", True))
    if extra_point is not None and extra_point[1] is not None:
        last_i, last_val = next(
            ((i, v) for i in range(len(points) - 1, -1, -1) if (v := points[i][1]) is not None),
            (None, None),
        )
        if last_val is not None:
            x1, y1 = xy(last_i, last_val)
            x2, y2 = xy(extra_index, extra_point[1])
            parts.append(f'<line x1="{x1:.1f}" y1="{y1:.1f}" x2="{x2:.1f}" y2="{y2:.1f}" class="chart-line-extra"/>')
        else:
            x2, y2 = xy(extra_index, extra_point[1])
        parts.append(f'<circle cx="{x2:.1f}" cy="{y2:.1f}" r="3.5" class="chart-line-extra-dot"/>')
        parts.append(
            f'<text x="{x2:.1f}" y="{y2 - 8:.1f}" class="chart-value chart-value-extra" text-anchor="middle">{value_fmt(extra_point[1])}</text>'
        )
    if legend:
        parts.append(
            f'<text x="{PAD_X}" y="12" class="chart-legend"><tspan class="legend1">● {legend[0]}</tspan>'
            f'  <tspan class="legend2">● {legend[1]}</tspan></text>'
        )
    parts.append("</svg>")
    return Markup("".join(parts))


# --------------------------------------------------------------- navegación
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


# ------------------------------------------------------------------ reporte
def _day_label(d: date) -> str:
    return f"{DAYS_ES[d.weekday()][:3].capitalize()} {d.day}"


def _week_days(week_start: date) -> list[date]:
    return [week_start + timedelta(days=i) for i in range(7)]


def _splits_view(splits: list[dict[str, Any]]) -> list[dict[str, Any]]:
    paces = [s["pace_s"] for s in splits if s.get("pace_s")]
    fastest = min(paces) if paces else None
    rows = []
    for s in splits:
        pace = s.get("pace_s")
        km = s.get("km")
        dist = s.get("distance_m") or 0
        label = str(km) if dist >= 950 else f"{dist / 1000:.2f}".rstrip("0").rstrip(".")
        rows.append(
            {
                "km": label,
                "pace": fmt_pace(pace),
                # barra proporcional a la velocidad: el km más rápido llena el ancho
                "pct": round(fastest / pace * 100) if (pace and fastest) else 0,
                "fastest": pace is not None and pace == fastest,
                "hr": _n(s.get("avg_hr")),
                "elev": _elev(s.get("elev_gain_m"), s.get("elev_loss_m")),
            }
        )
    return rows


def _fmt_lap_time(seconds: float | None) -> str:
    if not seconds:
        return "—"
    total = int(round(seconds))
    if total >= 3600:
        return f"{total // 3600}:{(total % 3600) // 60:02d}:{total % 60:02d}"
    return f"{total // 60}:{total % 60:02d}"


def _fmt_lap_dist(meters: float | None) -> str:
    if not meters:
        return "—"
    if meters < 950:
        return f"{int(round(meters))} m"
    return f"{meters / 1000:.2f}".rstrip("0").rstrip(".") + " km"


def _workout_laps_view(laps: list[dict[str, Any]]) -> list[dict[str, Any]]:
    # barra ∝ velocidad, ignorando vueltas cortas de ruido para la referencia
    paces = [l["pace_s"] for l in laps if l.get("pace_s") and (l.get("distance_m") or 0) >= 100]
    fastest = min(paces) if paces else None
    rows = []
    for lap in laps:
        pace = lap.get("pace_s")
        rows.append(
            {
                "n": lap.get("n"),
                "dist": _fmt_lap_dist(lap.get("distance_m")),
                "time": _fmt_lap_time(lap.get("time_s")),
                "pace": fmt_pace(pace),
                "pct": round(fastest / pace * 100) if (pace and fastest) else 0,
                "fastest": pace is not None and pace == fastest,
                "hr": _n(lap.get("avg_hr")),
                "power": _n(lap.get("avg_power_w")),
                "elev": _elev(lap.get("elev_gain_m"), lap.get("elev_loss_m")),
            }
        )
    return rows


def _activity_view(a: dict[str, Any]) -> dict[str, Any]:
    det = a.get("detail") or {}
    load = a.get("training_load") if a.get("training_load") is not None else det.get("training_load")
    elev_gain = a.get("elevation_gain_m") if a.get("elevation_gain_m") is not None else det.get("elevation_gain_m")

    stats = []
    for label, value in (
        ("Carga", _n(load)),
        ("Desnivel", _elev(elev_gain, det.get("elevation_loss_m")) if elev_gain is not None else "—"),
        ("TE aeróbico", _n(det.get("aerobic_te"))),
        ("TE anaeróbico", _n(det.get("anaerobic_te"))),
        ("Potencia media", _n(det.get("avg_power_w"), " W")),
        ("Cadencia", _n(det.get("avg_cadence_spm"), " spm")),
        ("Ritmo ajustado", fmt_pace(det.get("adjusted_pace_s")) + (" /km" if det.get("adjusted_pace_s") else "")),
        ("Mejor km", fmt_pace(det.get("best_km_s")) + (" /km" if det.get("best_km_s") else "")),
        ("Foco", det.get("training_focus") or "—"),
    ):
        if value not in ("—", ""):
            stats.append({"label": label, "value": value})

    return {
        "day": _day_label(date.fromisoformat(a["date"])) if a.get("date") else "—",
        "name": a.get("name") or "Actividad",
        "sport": a.get("sport") or "otro",
        "sport_label": SPORT_LABELS.get(a.get("sport") or "", (a.get("sport") or "—").replace("_", " ")),
        "duration": fmt_duration(a.get("duration_s")),
        "distance": fmt_km(a.get("distance_m")) if a.get("distance_m") is not None else "—",
        "avg_hr": _n(a.get("avg_hr")),
        "load": _n(load),
        "elev": _elev(elev_gain) if elev_gain is not None else "—",
        "has_detail": bool(det),
        "stats": stats,
        "splits": _splits_view(det.get("splits") or []),
        "workout_laps": _workout_laps_view(det.get("workout_laps") or []),
    }


def render_report(snapshot: dict[str, Any], nav: dict[str, Any], meta: dict[str, Any] | None = None) -> str:
    week_start = date.fromisoformat(snapshot["week_start"])
    week_end = date.fromisoformat(snapshot["week_end"])
    rd = snapshot["report_data"]
    totals = rd["totals"]
    fit = rd["fitness"]
    days = _week_days(week_start)

    activities = [_activity_view(a) for a in rd["activities"]]

    # series diarias sobre los 7 días de la semana
    daily_by_date = {m["date"]: m for m in rd["daily"]}
    load_by_day = rd.get("load_by_day", {})
    dist_by_day: dict[str, float] = {}
    for a in rd["activities"]:
        if a.get("date") and a.get("distance_m"):
            dist_by_day[a["date"]] = dist_by_day.get(a["date"], 0.0) + a["distance_m"] / 1000

    def day_points(getter: Callable[[date], float | None]) -> list[tuple[str, float | None]]:
        return [(_day_label(d), getter(d)) for d in days]

    base = rd["baselines_28d"]
    wk = rd["week_averages"]

    # dato de recuperación posterior al cierre (p.ej. "hoy"): se pinta distinto,
    # no forma parte de la semana congelada.
    latest = rd.get("latest_recovery")
    extra_label = _day_label(date.fromisoformat(latest["date"])) if latest else None
    extra_hrv = (extra_label, latest.get("hrv")) if latest and latest.get("hrv") is not None else None
    extra_rhr = (extra_label, latest.get("rhr")) if latest and latest.get("rhr") is not None else None
    extra_sleep = (
        (extra_label, latest["sleep_duration_s"] / 3600)
        if latest and latest.get("sleep_duration_s") is not None
        else None
    )

    charts = {
        "load": bar_chart(
            day_points(lambda d: load_by_day.get(d.isoformat())),
            title="Carga de entrenamiento por día",
        ),
        "distance": bar_chart(
            day_points(lambda d: dist_by_day.get(d.isoformat())),
            title="Distancia por día (km)",
        ),
        "hrv": line_chart(
            day_points(lambda d: (daily_by_date.get(d.isoformat()) or {}).get("hrv")),
            title="HRV nocturno (ms)",
            baseline=base.get("hrv"),
            extra_point=extra_hrv,
        ),
        "sleep": bar_chart(
            day_points(
                lambda d: (
                    v / 3600 if (v := (daily_by_date.get(d.isoformat()) or {}).get("sleep_duration_s")) else None
                )
            ),
            title="Horas de sueño por día",
            baseline=(base["sleep_duration_s"] / 3600) if base.get("sleep_duration_s") else None,
            extra_point=extra_sleep,
        ),
        "rhr": line_chart(
            day_points(lambda d: (daily_by_date.get(d.isoformat()) or {}).get("rhr")),
            title="Frecuencia cardíaca en reposo (ppm)",
            baseline=base.get("rhr"),
            extra_point=extra_rhr,
        ),
    }

    daily_rows = [
        {
            "day": _day_label(date.fromisoformat(m["date"])),
            "hrv": _n(m.get("hrv")),
            "rhr": _n(m.get("rhr")),
            "sleep": _sleep_h(m.get("sleep_duration_s")),
            "sleep_score": _n(m.get("sleep_score")),
            "load": _n(load_by_day.get(m["date"])),
        }
        for m in rd["daily"]
    ]

    wk_vs = {
        "hrv": _vs_baseline(wk.get("hrv"), base.get("hrv"), _n),
        "rhr": _vs_baseline(wk.get("rhr"), base.get("rhr"), _n),
        "sleep": _vs_baseline(wk.get("sleep_duration_s"), base.get("sleep_duration_s"), _sleep_h),
    }

    latest = rd.get("latest_recovery")
    latest_recovery = None
    if latest:
        latest_recovery = {
            "date_label": fmt_date_long(date.fromisoformat(latest["date"])),
            "hrv": _n(latest.get("hrv")),
            "rhr": _n(latest.get("rhr")),
            "sleep": _sleep_h(latest.get("sleep_duration_s")),
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
            "elevation": _elev(totals.get("elevation_gain_m")) if totals.get("elevation_gain_m") else "—",
        },
        fitness={
            "fitness": _n(fit.get("fitness_42d")),
            "fatigue": _n(fit.get("fatigue_7d")),
            "form": _n(fit.get("form")),
            "status": fit.get("status"),
        },
        activities=activities,
        charts=charts,
        has_charts=any(charts.values()),
        daily_rows=daily_rows,
        wk_vs=wk_vs,
        latest_recovery=latest_recovery,
        block_rows=block_rows,
        coverage_line=coverage_line,
        providers_line=providers_line,
        schema_version=f"schema {snapshot.get('schema_version', '?')}",
    )


# ------------------------------------------------------------------ archivo
def render_archive(entries: list[dict[str, Any]], latest: date) -> str:
    """entries desc: [{week_start, week_end, generated_at, rebuilt_at,
    distance_m, duration_s, sessions, training_load, fitness, fatigue}]."""
    asc = list(reversed(entries))

    def short(e: dict[str, Any]) -> str:
        return f"{e['week_start'].day}/{e['week_start'].month}"

    def pts(getter: Callable[[dict[str, Any]], float | None]) -> list[tuple[str, float | None]]:
        return [(short(e), getter(e)) for e in asc]

    trends = [
        {
            "title": "Distancia semanal",
            "sub": "km por semana",
            "svg": bar_chart(pts(lambda e: e["distance_m"] / 1000 if e.get("distance_m") else None), title="Distancia semanal (km)"),
        },
        {
            "title": "Desnivel acumulado",
            "sub": "m de subida por semana",
            "svg": bar_chart(pts(lambda e: e.get("elevation_gain_m")), title="Desnivel semanal (m)", value_fmt=lambda v: str(int(round(v)))),
        },
        {
            "title": "Carga semanal",
            "sub": "training load total por semana",
            "svg": bar_chart(pts(lambda e: e.get("training_load")), title="Carga semanal", value_fmt=lambda v: str(int(round(v)))),
        },
        {
            "title": "Fitness y fatiga",
            "sub": "al cierre de cada semana",
            "svg": line_chart(
                pts(lambda e: e.get("fitness")),
                title="Fitness y fatiga por semana",
                series2=[e.get("fatigue") for e in asc],
                legend=("Fitness (42 d)", "Fatiga (7 d)"),
            ),
        },
        {
            "title": "HRV nocturno",
            "sub": "promedio semanal (ms)",
            "svg": line_chart(pts(lambda e: e.get("hrv")), title="HRV promedio semanal (ms)"),
        },
        {
            "title": "FC en reposo",
            "sub": "promedio semanal (ppm)",
            "svg": line_chart(pts(lambda e: e.get("rhr")), title="FC en reposo promedio semanal (ppm)"),
        },
        {
            "title": "Sueño",
            "sub": "horas promedio por noche",
            "svg": bar_chart(
                pts(lambda e: e["sleep_duration_s"] / 3600 if e.get("sleep_duration_s") else None),
                title="Sueño promedio semanal (horas)",
            ),
        },
        {
            "title": "Tiempo de entrenamiento",
            "sub": "horas por semana",
            "svg": bar_chart(
                pts(lambda e: e["duration_s"] / 3600 if e.get("duration_s") else None),
                title="Horas de entrenamiento por semana",
            ),
        },
    ]
    trends = [t for t in trends if t["svg"]]

    view = [
        {
            "value": e["week_start"].isoformat(),
            "label": fmt_week_title(e["week_start"], e["week_end"]),
            "generated_on": _fmt_ts_date(e.get("generated_at")),
            "rebuilt_on": _fmt_ts_date(e["rebuilt_at"]) if e.get("rebuilt_at") else None,
            "distance": fmt_km(e.get("distance_m")) if e.get("distance_m") else None,
            "duration": fmt_duration(e.get("duration_s")) if e.get("duration_s") else None,
            "sessions": e.get("sessions"),
        }
        for e in entries
    ]
    template = _env().get_template("archive.html.j2")
    return template.render(entries=view, latest=latest.isoformat(), trends=trends)


def render_redirect(latest: date) -> str:
    return _env().get_template("redirect.html.j2").render(latest=latest.isoformat())


def render_unpublished() -> str:
    return _env().get_template("unpublished.html.j2").render()
