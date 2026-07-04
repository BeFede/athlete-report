import json
from datetime import date, timedelta

from conftest import DETAIL_LAPS, DETAIL_TEXT, NOW, TODAY, make_daily, make_detail, seed_history, write_dump

from athlete_report.commands import cmd_generate_latest, cmd_publish, cmd_sync
from athlete_report.details import normalize_detail, parse_detail_text, parse_km_splits
from athlete_report.providers import CorosMcpProvider
from athlete_report.storage import Store


def test_parse_detail_text():
    parsed = parse_detail_text(DETAIL_TEXT.format(load=309, gain=581, loss=596))
    assert parsed["training_load"] == 309
    assert parsed["elevation_gain_m"] == 581
    assert parsed["elevation_loss_m"] == 596
    assert parsed["aerobic_te"] == 3.1
    assert parsed["anaerobic_te"] == 1.2
    assert parsed["training_focus"] == "Base"
    assert parsed["avg_power_w"] == 250
    assert parsed["adjusted_pace_s"] == 330
    assert parsed["best_km_s"] == 310


def test_parse_km_splits():
    splits = parse_km_splits(DETAIL_LAPS)
    assert len(splits) == 3
    assert splits[0] == {
        "km": 1, "distance_m": 1000, "time_s": 360.0, "pace_s": 360.0,
        "avg_hr": 140, "elev_gain_m": 40.0, "elev_loss_m": 30.0, "avg_power_w": 240,
    }
    assert splits[2]["distance_m"] == 500


def test_normalize_detail_sin_laps():
    detail = normalize_detail({"detail_text": DETAIL_TEXT.format(load=80, gain=10, loss=5)})
    assert detail["training_load"] == 80
    assert detail["splits"] == []


def test_sync_enriquece_carga_y_desnivel_desde_detalle(paths):
    d = TODAY - timedelta(days=3)
    # actividad SIN training_load ni desnivel en el resumen (caso COROS real)
    write_dump(paths, "a.json", "activities", [{
        "id": f"act-{d.isoformat()}", "name": "Trail", "sport": "trail_run",
        "start_time": f"{d.isoformat()}T08:00:00-03:00", "duration_s": 3600, "distance_m": 10000,
    }])
    write_dump(paths, "d.json", "daily_metrics", [make_daily(d)])
    write_dump(paths, "det.json", "activity_detail", [make_detail(d, load=222, gain=333)])

    cmd_sync(paths, provider=CorosMcpProvider(paths.raw_coros), now=NOW)

    store = Store(paths)
    act = [a for a in store.load_activities() if a["external_activity_id"] == f"act-{d.isoformat()}"][0]
    assert act["training_load"] == 222
    assert act["elevation_gain_m"] == 333
    detail = store.load_detail("coros", f"act-{d.isoformat()}")
    assert detail["training_load"] == 222
    assert len(detail["splits"]) == 3


def test_snapshot_embebe_detalle_y_totales(paths):
    seed_history(paths, TODAY - timedelta(days=100), TODAY)
    week, _ = cmd_generate_latest(paths, provider=CorosMcpProvider(paths.raw_coros), now=NOW)
    snap = json.loads(paths.report_json(week).read_text())
    acts = snap["report_data"]["activities"]
    assert all("detail" in a for a in acts)
    assert acts[0]["detail"]["splits"][0]["pace_s"] == 360.0
    assert acts[0]["detail"]["training_focus"] == "Base"
    # totales de desnivel: 6 actividades x 120 m
    assert snap["report_data"]["totals"]["elevation_gain_m"] == 720


def test_html_muestra_detalle_expandible(paths):
    seed_history(paths, TODAY - timedelta(days=100), TODAY)
    cmd_publish(paths, provider=CorosMcpProvider(paths.raw_coros), now=NOW)
    html = (paths.dist / "reports" / "2026-06-22" / "index.html").read_text()
    assert '<details class="activity"' in html
    assert "TE aeróbico" in html
    assert 'class="split-bar"' in html
    assert "5:10" in html  # mejor km
    assert "Desnivel" in html
