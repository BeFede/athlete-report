from datetime import date, timedelta

from conftest import NOW, TODAY, make_daily, seed_history, write_dump

from athlete_report.commands import cmd_generate, cmd_publish
from athlete_report.privacy import scan_public_dir
from athlete_report.providers import CorosMcpProvider
from athlete_report.render import bar_chart, line_chart


def test_reporte_incluye_graficos_svg(paths):
    seed_history(paths, TODAY - timedelta(days=100), TODAY)
    cmd_publish(paths, provider=CorosMcpProvider(paths.raw_coros), now=NOW)
    html = (paths.dist / "reports" / "2026-06-22" / "index.html").read_text()
    assert html.count("<svg") >= 4  # distancia, carga, hrv, fc reposo, sueño
    assert "La semana en gráficos" in html
    # los SVG pasan la validación de privacidad (coords redondeadas)
    assert scan_public_dir(paths.dist) == []


def test_archivo_incluye_tendencias(paths):
    seed_history(paths, TODAY - timedelta(days=100), TODAY)
    provider = CorosMcpProvider(paths.raw_coros)
    cmd_generate(paths, date(2026, 6, 15), provider=provider, now=NOW)
    cmd_publish(paths, provider=provider, now=NOW)
    html = (paths.dist / "archive" / "index.html").read_text()
    assert "Tendencias" in html
    assert html.count("<svg") >= 2


def test_semana_sin_carga_ni_hrv_no_rompe(paths):
    # sólo actividades sin training_load y métricas sin hrv
    d = date(2026, 6, 24)
    write_dump(paths, "acts.json", "activities", [
        {"id": "a1", "name": "Trote", "sport": "run",
         "start_time": f"{d.isoformat()}T07:00:00-03:00", "duration_s": 3600},
    ])
    daily = make_daily(d)
    daily.pop("hrv")
    write_dump(paths, "daily.json", "daily_metrics", [daily])
    cmd_publish(paths, provider=CorosMcpProvider(paths.raw_coros), now=NOW)
    html = (paths.dist / "reports" / "2026-06-22" / "index.html").read_text()
    assert "Semana del 22 al 28 de junio de 2026" in html


def test_chart_builders_devuelven_none_sin_datos():
    assert bar_chart([("Lun", None), ("Mar", None)], title="x") is None
    assert line_chart([("Lun", None)], title="x") is None


def test_chart_coords_sin_pares_de_coordenadas_largos():
    svg = str(line_chart([("Lun", 61.123456), ("Mar", 58.9), ("Mié", 70.5)], title="hrv", baseline=64.33333))
    import re
    assert not re.search(r"-?\d{1,3}\.\d{4,}\s*,\s*-?\d{1,3}\.\d{4,}", svg)
