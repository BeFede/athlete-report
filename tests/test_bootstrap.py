import json
from datetime import date, timedelta

from conftest import NOW, TODAY, seed_history

from athlete_report.commands import cmd_bootstrap
from athlete_report.providers import CorosMcpProvider
from athlete_report.storage import Store
from athlete_report.weeks import bootstrap_range


def test_bootstrap_12_semanas_con_warmup(paths):
    data_start, data_end, weeks = bootstrap_range(12, TODAY, 56)
    seed_history(paths, data_start, data_end)

    result = cmd_bootstrap(paths, 12, provider=CorosMcpProvider(paths.raw_coros), now=NOW)

    # 12 snapshots generados
    assert len(result["weeks"]) == 12
    assert all(status == "created" for status in result["weeks"].values())
    for week in weeks:
        assert paths.report_json(week).exists()
        assert paths.report_meta(week).exists()

    # el warm-up de 56 días fue ingerido (hay actividades antes de la primera semana)
    store = Store(paths)
    act_dates = sorted(a["local_date"] for a in store.load_activities() if a["local_date"])
    assert date.fromisoformat(act_dates[0]) < weeks[0]
    assert date.fromisoformat(act_dates[0]) >= data_start

    # la semana MÁS VIEJA ya tiene métricas históricas correctas
    oldest = json.loads(paths.report_json(weeks[0]).read_text())
    fit = oldest["report_data"]["fitness"]
    assert fit["fitness_42d"] is not None and fit["fitness_42d"] > 30
    assert fit["fatigue_7d"] is not None and fit["fatigue_7d"] > 0
    prev_block = oldest["report_data"]["block_comparison"]["previous_28d"]
    assert prev_block["sessions"] > 0  # el bloque anterior existe gracias al warm-up
    assert oldest["report_data"]["baselines_28d"]["hrv"] is not None

    # cobertura completa con datos sintéticos (6 días de actividad, domingo libre)
    assert oldest["coverage"]["activity_days"] == 6
    assert oldest["coverage"]["hrv_days"] == 7
    assert oldest["coverage"]["sleep_days"] == 7
    assert oldest["coverage"]["rhr_days"] == 7


def test_bootstrap_no_pisa_snapshots_existentes(paths):
    data_start, data_end, weeks = bootstrap_range(3, TODAY, 56)
    seed_history(paths, data_start, data_end)
    provider = CorosMcpProvider(paths.raw_coros)

    cmd_bootstrap(paths, 3, provider=provider, now=NOW)
    original = paths.report_json(weeks[0]).read_bytes()

    result = cmd_bootstrap(paths, 3, provider=provider, now=NOW + timedelta(days=1))
    assert all(status == "skipped" for status in result["weeks"].values())
    assert paths.report_json(weeks[0]).read_bytes() == original
