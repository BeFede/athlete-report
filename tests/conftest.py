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


DETAIL_TEXT = """🏃 Trail Run Activity Details
========================================

Workout Time: 1:00:00
Distance: 10.00 km
Average Pace: 6:00 /km
Adjusted Pace: 5:30 /km
Best Kilometer: 5:10 /km
Average Heart Rate: 145 bpm
Average Cadence: 172 spm
Average Power: 250 W
Elevation Gain / Loss: {gain} m / {loss} m
Calories: 640 kcal
Training Load: {load}
Aerobic TE: 3.1
Anaerobic TE: 1.2
Training Focus: Base"""

DETAIL_LAPS = {
    "lapGroups": [
        {
            "type": 10,
            "lapDistance": 100000,
            "laps": [
                {"lapIndex": 1, "distance": 100000, "time": 360.0, "avgPace": 360.0,
                 "avgHr": 140, "elevGain": 40.0, "totalDescent": 30.0, "avgPower": 240},
                {"lapIndex": 2, "distance": 100000, "time": 350.0, "avgPace": 350.0,
                 "avgHr": 150, "elevGain": 50.0, "totalDescent": 45.0, "avgPower": 260},
                {"lapIndex": 3, "distance": 50000, "time": 180.0, "avgPace": 360.0,
                 "avgHr": 148, "elevGain": 30.0, "totalDescent": 40.0, "avgPower": 250},
            ],
        }
    ]
}


def make_detail(d: date, *, load: float = 100, gain: float = 120, loss: float = 115) -> dict:
    return {
        "external_activity_id": f"act-{d.isoformat()}",
        "sportType": 102,
        "date": d.isoformat(),
        "detail_text": DETAIL_TEXT.format(load=load, gain=gain, loss=loss),
        "laps": DETAIL_LAPS,
    }


def seed_history(paths: ProjectPaths, start: date, end: date, *, details: bool = True) -> None:
    """Actividades todos los días menos domingo + métricas diarias completas."""
    activities, daily, det = [], [], []
    d = start
    while d <= end:
        if d.weekday() != 6:
            activities.append(make_activity(d))
            det.append(make_detail(d, load=activities[-1]["training_load"]))
        daily.append(make_daily(d))
        d += timedelta(days=1)
    write_dump(paths, "activities_seed.json", "activities", activities)
    write_dump(paths, "daily_seed.json", "daily_metrics", daily)
    if details:
        write_dump(paths, "details_seed.json", "activity_detail", det)
