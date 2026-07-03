from datetime import date, datetime, timedelta

from conftest import NOW, TODAY, make_activity, make_daily, seed_history, write_dump

from athlete_report.commands import cmd_sync
from athlete_report.providers import CorosMcpProvider
from athlete_report.storage import Store


def _sync(paths, now=NOW):
    return cmd_sync(paths, provider=CorosMcpProvider(paths.raw_coros), now=now)


def test_sync_idempotente_sin_duplicados(paths):
    seed_history(paths, TODAY - timedelta(days=20), TODAY)
    store = Store(paths)

    first = _sync(paths)
    assert first["activities"].inserted > 0
    n_after_first = len(store.load_activities())

    second = _sync(paths, now=NOW + timedelta(hours=1))
    assert second["activities"].inserted == 0
    assert second["activities"].updated == 0
    assert len(store.load_activities()) == n_after_first

    # sin duplicados por clave provider + external_activity_id
    keys = [(a["provider"], a["external_activity_id"]) for a in store.load_activities()]
    assert len(keys) == len(set(keys))


def test_sync_detecta_modificaciones(paths):
    d = TODAY - timedelta(days=3)
    write_dump(paths, "a1.json", "activities", [make_activity(d, load=80)])
    write_dump(paths, "d1.json", "daily_metrics", [make_daily(d)])
    _sync(paths)

    # COROS corrige la carga después: dump más nuevo, mismo id
    write_dump(paths, "a2.json", "activities", [make_activity(d, load=95, name="Trote corregido")])
    result = _sync(paths, now=NOW + timedelta(hours=2))

    assert result["activities"].updated == 1
    assert result["activities"].inserted == 0
    store = Store(paths)
    acts = [a for a in store.load_activities() if a["external_activity_id"] == f"act-{d.isoformat()}"]
    assert len(acts) == 1
    assert acts[0]["training_load"] == 95
    assert acts[0]["name"] == "Trote corregido"


def test_daily_metrics_upsert_por_fecha(paths):
    d = TODAY - timedelta(days=2)
    write_dump(paths, "d1.json", "daily_metrics", [make_daily(d)])
    _sync(paths)

    fixed = make_daily(d) | {"hrv": 99}
    write_dump(paths, "d2.json", "daily_metrics", [fixed])
    result = _sync(paths, now=NOW + timedelta(hours=1))

    assert result["daily_metrics"].updated == 1
    store = Store(paths)
    rows = [m for m in store.load_daily_metrics() if m["date"] == d.isoformat()]
    assert len(rows) == 1
    assert rows[0]["hrv"] == 99


def test_sync_state_solo_tras_exito(paths):
    seed_history(paths, TODAY - timedelta(days=10), TODAY)
    store = Store(paths)
    assert store.read_sync_state() == {}
    _sync(paths)
    state = store.read_sync_state()
    assert state["last_sync_at"] == NOW.isoformat()
    assert state["provider"] == "coros"
    # ventana solapada de 14 días en la sync siguiente
    later = NOW + timedelta(days=2)
    _sync(paths, now=later)
    state = store.read_sync_state()
    start = date.fromisoformat(state["last_activity_window"]["start"])
    assert start == NOW.date() - timedelta(days=14)
