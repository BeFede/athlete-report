import json
from datetime import date, timedelta

from conftest import NOW, TODAY, seed_history

from athlete_report.commands import cmd_generate, cmd_rebuild
from athlete_report.providers import CorosMcpProvider


def _setup_three_weeks(paths):
    seed_history(paths, TODAY - timedelta(days=120), TODAY)
    provider = CorosMcpProvider(paths.raw_coros)
    weeks = [date(2026, 6, 8), date(2026, 6, 15), date(2026, 6, 22)]
    for w in weeks:
        cmd_generate(paths, w, provider=provider, now=NOW)
    return provider, weeks


def test_rebuild_solo_el_rango_pedido(paths):
    provider, weeks = _setup_three_weeks(paths)
    untouched = paths.report_json(weeks[0]).read_bytes()
    untouched_meta = paths.report_meta(weeks[0]).read_bytes()

    later = NOW + timedelta(days=3)
    statuses = cmd_rebuild(paths, weeks[1], weeks[2], provider=provider, now=later)

    assert statuses == {weeks[1].isoformat(): "rebuilt", weeks[2].isoformat(): "rebuilt"}
    # fuera del rango: intacto
    assert paths.report_json(weeks[0]).read_bytes() == untouched
    assert paths.report_meta(weeks[0]).read_bytes() == untouched_meta


def test_rebuild_conserva_generated_at_y_registra_reconstruccion(paths):
    provider, weeks = _setup_three_weeks(paths)
    original = json.loads(paths.report_json(weeks[1]).read_text())

    later = NOW + timedelta(days=3)
    cmd_rebuild(paths, weeks[1], weeks[1], provider=provider, now=later, reason="manual")

    snap = json.loads(paths.report_json(weeks[1]).read_text())
    meta = json.loads(paths.report_meta(weeks[1]).read_text())

    assert snap["generated_at"] == original["generated_at"]  # se conserva
    assert meta["generated_at"] == original["generated_at"]
    assert meta["rebuilt_at"] == later.isoformat()
    assert meta["rebuild_reason"] == "manual"


def test_rebuild_no_es_automatico(paths):
    """generate-latest / generate nunca reconstruyen semanas cerradas."""
    provider, weeks = _setup_three_weeks(paths)
    meta_before = json.loads(paths.report_meta(weeks[1]).read_text())
    assert "rebuilt_at" not in meta_before

    cmd_generate(paths, weeks[1], provider=provider, now=NOW + timedelta(days=5))
    meta_after = json.loads(paths.report_meta(weeks[1]).read_text())
    assert meta_after == meta_before
