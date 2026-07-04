"""Normalización de detalles de actividad (COROS MCP).

Convierte el payload crudo del dump activity_detail ({detail_text, laps}) en
un dict normalizado y estable que se persiste en
data/normalized/details/<provider>/<id>.json y se embebe en los snapshots.
"""

from __future__ import annotations

import re
from typing import Any

_PACE_RE = r"(\d+):(\d{2})"


def _pace_s(text: str | None) -> float | None:
    if not text:
        return None
    m = re.search(_PACE_RE, text)
    if not m:
        return None
    return int(m.group(1)) * 60 + int(m.group(2))


def _num(text: str | None) -> float | None:
    if text is None:
        return None
    try:
        return float(text)
    except ValueError:
        return None


def parse_detail_text(text: str) -> dict[str, Any]:
    """Extrae métricas del resumen de texto de getActivityDetail."""

    def find(pattern: str) -> str | None:
        m = re.search(pattern, text)
        return m.group(1) if m else None

    elev = re.search(r"Elevation Gain / Loss: (\d+(?:\.\d+)?) m / (\d+(?:\.\d+)?) m", text)
    return {
        "training_load": _num(find(r"Training Load: (\d+(?:\.\d+)?)")),
        "elevation_gain_m": _num(elev.group(1)) if elev else None,
        "elevation_loss_m": _num(elev.group(2)) if elev else None,
        "aerobic_te": _num(find(r"Aerobic TE: (\d+(?:\.\d+)?)")),
        "anaerobic_te": _num(find(r"Anaerobic TE: (\d+(?:\.\d+)?)")),
        "training_focus": find(r"Training Focus: (.+)"),
        "avg_power_w": _num(find(r"Average Power: (\d+(?:\.\d+)?) W")),
        "avg_cadence_spm": _num(find(r"Average Cadence: (\d+(?:\.\d+)?) spm")),
        "avg_stride_len_m": _num(find(r"Average Stride Length: (\d+(?:\.\d+)?) m")),
        "adjusted_pace_s": _pace_s(find(r"Adjusted Pace: ([\d:]+) /km")),
        "best_km_s": _pace_s(find(r"Best Kilometer: ([\d:]+) /km")),
        "moving_pace_s": _pace_s(find(r"Moving Average Pace: ([\d:]+) /km")),
    }


def parse_km_splits(laps: dict[str, Any] | None) -> list[dict[str, Any]]:
    """Parciales por kilómetro: lapGroup type=10 (distancias en cm, pace en s/km)."""
    if not isinstance(laps, dict):
        return []
    groups = laps.get("lapGroups") or []
    km_group = next((g for g in groups if g.get("type") == 10), None)
    if not km_group:
        return []
    splits = []
    for lap in km_group.get("laps") or []:
        distance_m = (lap.get("distance") or 0) / 100.0
        if distance_m < 200:  # resto final demasiado corto: ruido
            continue
        splits.append(
            {
                "km": lap.get("lapIndex"),
                "distance_m": round(distance_m, 0),
                "time_s": round(lap.get("time") or 0, 1),
                "pace_s": round(lap.get("avgPace") or 0, 1) or None,
                "avg_hr": lap.get("avgHr") or None,
                "elev_gain_m": lap.get("elevGain"),
                "elev_loss_m": lap.get("totalDescent"),
                "avg_power_w": lap.get("avgPower") or None,
            }
        )
    return splits


def normalize_detail(payload: dict[str, Any]) -> dict[str, Any]:
    """Payload del dump ({detail_text, laps, ...}) -> detalle normalizado."""
    text = payload.get("detail_text") or ""
    detail = parse_detail_text(text) if text else {}
    detail["splits"] = parse_km_splits(payload.get("laps"))
    return detail
