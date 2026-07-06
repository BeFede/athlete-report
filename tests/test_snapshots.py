import json
from datetime import date, timedelta

import pytest
from conftest import LAST_COMPLETE_WEEK, NOW, TODAY, seed_history

from athlete_report.commands import cmd_generate, cmd_generate_latest
from athlete_report.providers import CorosMcpProvider
from athlete_report.report import SnapshotExistsError, build_snapshot, write_snapshot
from athlete_report.storage import Store


@pytest.fixture
def seeded(paths):
    seed_history(paths, TODAY - timedelta(days=100), TODAY)
    return paths


def _provider(paths):
    return CorosMcpProvider(paths.raw_coros)


def test_generate_latest_crea_snapshot(seeded):
    week, status = cmd_generate_latest(seeded, provider=_provider(seeded), now=NOW)
    assert week == LAST_COMPLETE_WEEK
    assert status == "created"
    snap = json.loads(seeded.report_json(week).read_text())
    assert snap["schema_version"] == "1.0"
    assert snap["week_start"] == "2026-06-22"
    assert snap["week_end"] == "2026-06-28"
    assert snap["provider_versions"] == {"coros": "mcp"}
    assert snap["data_as_of"] == NOW.isoformat()
    assert set(snap["coverage"]) == {"activity_days", "hrv_days", "sleep_days", "rhr_days"}
    assert snap["report_data"]["totals"]["sessions"] == 6


def test_snapshot_cerrado_no_se_modifica(seeded):
    week, _ = cmd_generate_latest(seeded, provider=_provider(seeded), now=NOW)
    original = seeded.report_json(week).read_bytes()

    # segunda corrida más tarde, sin overwrite: intacto byte a byte
    week2, status = cmd_generate_latest(seeded, provider=_provider(seeded), now=NOW + timedelta(hours=5))
    assert week2 == week
    assert status == "skipped"
    assert seeded.report_json(week).read_bytes() == original


def test_overwrite_explicito_regenera(seeded):
    week, _ = cmd_generate_latest(seeded, provider=_provider(seeded), now=NOW)
    later = NOW + timedelta(hours=5)
    week2, status = cmd_generate_latest(seeded, provider=_provider(seeded), now=later, overwrite=True)
    assert status == "overwritten"
    snap = json.loads(seeded.report_json(week).read_text())
    assert snap["generated_at"] == later.isoformat()


def test_generate_semana_puntual(seeded):
    target = date(2026, 6, 8)
    status = cmd_generate(seeded, target, provider=_provider(seeded), now=NOW)
    assert status == "created"
    assert seeded.report_json(target).exists()
    # regenerar sin overwrite no toca nada
    assert cmd_generate(seeded, target, provider=_provider(seeded), now=NOW) == "skipped"


def test_generate_rechaza_no_lunes(seeded):
    with pytest.raises(ValueError):
        cmd_generate(seeded, date(2026, 6, 9), provider=_provider(seeded), now=NOW)


def test_write_snapshot_sin_flags_falla_si_existe(seeded):
    store = Store(seeded)
    snap = build_snapshot(store, LAST_COMPLETE_WEEK, generated_at=NOW, data_as_of=NOW.isoformat(), provider_versions={"coros": "mcp"})
    write_snapshot(seeded, snap)
    with pytest.raises(SnapshotExistsError):
        write_snapshot(seeded, snap)


def test_fitness_prefiere_valores_del_proveedor(seeded):
    from conftest import write_dump

    # status del proveedor disponible para el domingo de la última semana completa
    write_dump(seeded, "status.json", "training_status", [
        {"date": "2026-06-28", "fitness": 177, "fatigue": 233, "status": "Optimized"},
    ])
    week, _ = cmd_generate_latest(seeded, provider=_provider(seeded), now=NOW)
    snap = json.loads(seeded.report_json(week).read_text())
    fit = snap["report_data"]["fitness"]
    assert fit["source"] == "provider"
    assert fit["fitness_42d"] == 177
    assert fit["fatigue_7d"] == 233
    assert fit["form"] == -56
    assert fit["status"] == "Optimized"


def test_fitness_computado_sin_status_del_proveedor(seeded):
    week, _ = cmd_generate_latest(seeded, provider=_provider(seeded), now=NOW)
    snap = json.loads(seeded.report_json(week).read_text())
    fit = snap["report_data"]["fitness"]
    assert fit["source"] == "computed"
    assert fit["fitness_42d"] > 0


def test_latest_recovery_dato_fuera_de_semana(paths):
    from conftest import write_dump

    # sin datos posteriores al cierre de semana (2026-06-28)
    seed_history(paths, date(2026, 4, 1), date(2026, 6, 28))
    write_dump(paths, "extra.json", "daily_metrics", [
        {"date": "2026-06-30", "hrv": 68, "resting_hr": 47, "sleep_duration_s": 27000},
    ])
    week, _ = cmd_generate_latest(paths, provider=_provider(paths), now=NOW)
    snap = json.loads(paths.report_json(week).read_text())
    latest = snap["report_data"]["latest_recovery"]
    assert latest == {"date": "2026-06-30", "hrv": 68, "rhr": 47, "sleep_duration_s": 27000}


def test_latest_recovery_ausente_sin_datos_posteriores(paths):
    seed_history(paths, date(2026, 4, 1), date(2026, 6, 28))
    week, _ = cmd_generate_latest(paths, provider=_provider(paths), now=NOW)
    snap = json.loads(paths.report_json(week).read_text())
    assert snap["report_data"]["latest_recovery"] is None


def test_latest_recovery_no_aparece_si_es_muy_lejano(paths):
    """Al reconstruir una semana vieja mucho después, no debe traer el dato
    de "hoy" como si fuera reciente."""
    from conftest import write_dump

    seed_history(paths, date(2026, 4, 1), date(2026, 6, 28))
    write_dump(paths, "extra.json", "daily_metrics", [
        {"date": "2026-07-10", "hrv": 68, "resting_hr": 47, "sleep_duration_s": 27000},
    ])
    week, _ = cmd_generate_latest(paths, provider=_provider(paths), now=NOW)
    snap = json.loads(paths.report_json(week).read_text())
    assert snap["report_data"]["latest_recovery"] is None
