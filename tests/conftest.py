import json
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

import pytest

from athlete_report.config import ProjectPaths

TZ = ZoneInfo("America/Argentina/Buenos_Aires")
TODAY = date(2026, 7, 3)  # viernes -> última semana completa: 2026-06-22
NOW = datetime(2026, 7, 3, 8, 0, tzinfo=TZ)
LAST_COMPLETE_WEEK = date(2026, 6, 22)


@pytest.fixture
def paths(tmp_path) -> ProjectPaths:
    p = ProjectPaths(root=tmp_path)
    p.ensure_base()
    return p


def write_dump(paths: ProjectPaths, name: str, kind: str, items: list[dict]) -> None:
    payload = {
        "kind": kind,
        "provider": "coros",
        "fetched_at": NOW.isoformat(),
        "items": items,
    }
    (paths.raw_coros / name).write_text(json.dumps(payload))


def make_activity(d: date, *, load: float | None = None, name: str | None = None) -> dict:
    return {
        "id": f"act-{d.isoformat()}",
        "name": name or f"Trote {d.isoformat()}",
        "sport": "run",
        "start_time": f"{d.isoformat()}T07:00:00-03:00",
        "duration_s": 3600,
        "distance_m": 10000,
        "avg_hr": 145,
        "max_hr": 168,
        "training_load": load if load is not None else 60 + (d.toordinal() % 5) * 15,
        "elevation_gain_m": 120,
        "calories": 640,
        "updated_at": NOW.isoformat(),
    }


def make_daily(d: date) -> dict:
    return {
        "date": d.isoformat(),
        "hrv": 58 + (d.toordinal() % 7),
        "resting_hr": 44 + (d.toordinal() % 3),
        "sleep_duration_s": int(7.2 * 3600),
        "sleep_score": 78 + (d.toordinal() % 10),
        "stress_avg": 28,
        "steps": 9500,
    }


def seed_history(paths: ProjectPaths, start: date, end: date) -> None:
    """Actividades todos los días menos domingo + métricas diarias completas."""
    activities, daily = [], []
    d = start
    while d <= end:
        if d.weekday() != 6:
            activities.append(make_activity(d))
        daily.append(make_daily(d))
        d += timedelta(days=1)
    write_dump(paths, "activities_seed.json", "activities", activities)
    write_dump(paths, "daily_seed.json", "daily_metrics", daily)
