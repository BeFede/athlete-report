from datetime import date, timedelta

from conftest import NOW, TODAY, seed_history

from athlete_report.commands import cmd_generate, cmd_publish
from athlete_report.providers import CorosMcpProvider

WEEKS = [date(2026, 6, 8), date(2026, 6, 15), date(2026, 6, 22)]


def _publish_three_weeks(paths):
    seed_history(paths, TODAY - timedelta(days=120), TODAY)
    provider = CorosMcpProvider(paths.raw_coros)
    for w in WEEKS[:2]:
        cmd_generate(paths, w, provider=provider, now=NOW)
    cmd_publish(paths, provider=provider, now=NOW)  # genera también 2026-06-22


def test_estructura_dist(paths):
    _publish_three_weeks(paths)
    assert (paths.dist / "index.html").exists()
    assert (paths.dist / "archive" / "index.html").exists()
    for w in WEEKS:
        assert (paths.dist / "reports" / w.isoformat() / "index.html").exists()


def test_index_redirige_a_ultima_semana(paths):
    _publish_three_weeks(paths)
    index = (paths.dist / "index.html").read_text()
    assert "url=reports/2026-06-22/" in index


def test_flechas_prev_next(paths):
    _publish_three_weeks(paths)
    middle = (paths.dist / "reports" / "2026-06-15" / "index.html").read_text()
    assert 'href="../2026-06-08/"' in middle  # semana anterior
    assert 'href="../2026-06-22/"' in middle  # semana siguiente

    latest = (paths.dist / "reports" / "2026-06-22" / "index.html").read_text()
    assert 'href="../2026-06-15/"' in latest
    assert "Semana siguiente" in latest
    assert 'href="../2026-06-29/"' not in latest  # no hay siguiente

    oldest = (paths.dist / "reports" / "2026-06-08" / "index.html").read_text()
    assert 'href="../2026-06-01/"' not in oldest  # no hay anterior


def test_selector_y_link_ultima_semana(paths):
    _publish_three_weeks(paths)
    middle = (paths.dist / "reports" / "2026-06-15" / "index.html").read_text()
    assert "<select" in middle
    for w in WEEKS:
        assert f'value="{w.isoformat()}"' in middle
    assert 'href="../2026-06-22/">Última semana</a>' in middle
    assert 'href="../../archive/"' in middle


def test_archivo_historico_lista_semanas(paths):
    _publish_three_weeks(paths)
    archive = (paths.dist / "archive" / "index.html").read_text()
    for w in WEEKS:
        assert f'href="../reports/{w.isoformat()}/"' in archive


def test_encabezado_del_reporte(paths):
    _publish_three_weeks(paths)
    html = (paths.dist / "reports" / "2026-06-22" / "index.html").read_text()
    assert "Semana del 22 al 28 de junio de 2026" in html
    assert "Generado el 3 de julio de 2026" in html
    assert "Datos sincronizados hasta el 3 de julio de 2026" in html
