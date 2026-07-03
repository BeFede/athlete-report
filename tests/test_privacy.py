from datetime import timedelta

import pytest
from conftest import NOW, TODAY, seed_history

from athlete_report.commands import cmd_publish, cmd_unpublish
from athlete_report.privacy import PrivacyError, scan_public_dir, validate_public_dir
from athlete_report.providers import CorosMcpProvider


def test_dist_publicado_pasa_validacion(paths):
    seed_history(paths, TODAY - timedelta(days=100), TODAY)
    cmd_publish(paths, provider=CorosMcpProvider(paths.raw_coros), now=NOW)
    assert scan_public_dir(paths.dist) == []
    # nada de archivos privados en dist
    suffixes = {p.suffix for p in paths.dist.rglob("*") if p.is_file()}
    assert suffixes <= {".html", ".css"}


def test_detecta_archivos_prohibidos(tmp_path):
    (tmp_path / "activity.fit").write_bytes(b"\x0e\x10")
    (tmp_path / "route.gpx").write_text("<gpx></gpx>")
    (tmp_path / "report.json").write_text("{}")
    violations = scan_public_dir(tmp_path)
    assert len(violations) == 3
    with pytest.raises(PrivacyError):
        validate_public_dir(tmp_path)


def test_detecta_tokens_y_coordenadas(tmp_path):
    (tmp_path / "leak1.html").write_text("<p>api_key: abc123</p>")
    (tmp_path / "leak2.html").write_text('<script>var p = {"latitude": -34.6037, "longitude": -58.3816}</script>')
    (tmp_path / "leak3.html").write_text("<p>-34.603722, -58.381592</p>")
    (tmp_path / "clean.html").write_text("<p>Distancia: 10.2 km</p>")
    violations = scan_public_dir(tmp_path)
    assert any("leak1.html" in v for v in violations)
    assert any("leak2.html" in v for v in violations)
    assert any("leak3.html" in v for v in violations)
    assert not any("clean.html" in v for v in violations)


def test_unpublish_deja_pagina_minima(paths):
    seed_history(paths, TODAY - timedelta(days=100), TODAY)
    cmd_publish(paths, provider=CorosMcpProvider(paths.raw_coros), now=NOW)
    weeks_before = sorted(p.name for p in paths.reports.iterdir())

    cmd_unpublish(paths)

    files = [p for p in paths.dist.rglob("*") if p.is_file()]
    assert len(files) == 1
    assert files[0].name == "index.html"
    html = files[0].read_text()
    assert "No hay un reporte semanal publicado actualmente." in html
    assert "<a " not in html  # sin links a semanas previas
    assert scan_public_dir(paths.dist) == []

    # snapshots y renders históricos locales intactos
    assert sorted(p.name for p in paths.reports.iterdir()) == weeks_before
    assert any(paths.rendered_reports.iterdir())
