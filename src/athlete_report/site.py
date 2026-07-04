"""Armado del sitio: build/rendered_reports, staging y dist/ público."""

from __future__ import annotations

import shutil
from datetime import date
from typing import Any

from .config import ProjectPaths
from .privacy import validate_public_dir
from .render import build_nav, render_archive, render_redirect, render_report, render_unpublished
from .report import list_snapshot_weeks, load_meta, load_snapshot

ARCHIVE_LIMIT = 12


def render_all_to_build(paths: ProjectPaths) -> list[date]:
    """Renderiza cada snapshot a build/rendered_reports/<semana>/index.html.

    El contenido sale del snapshot congelado; sólo la navegación se refresca
    con la lista actual de semanas.
    """
    weeks = list_snapshot_weeks(paths)
    for week in weeks:
        snapshot = load_snapshot(paths, week)
        meta = load_meta(paths, week)
        html = render_report(snapshot, build_nav(weeks, week), meta)
        out_dir = paths.rendered_reports / week.isoformat()
        out_dir.mkdir(parents=True, exist_ok=True)
        (out_dir / "index.html").write_text(html)
    return weeks


def _archive_entries(paths: ProjectPaths, weeks: list[date]) -> list[dict[str, Any]]:
    entries = []
    for week in sorted(weeks, reverse=True)[:ARCHIVE_LIMIT]:
        snapshot = load_snapshot(paths, week)
        meta = load_meta(paths, week)
        totals = snapshot["report_data"].get("totals", {})
        fitness = snapshot["report_data"].get("fitness", {})
        week_avg = snapshot["report_data"].get("week_averages", {})
        entries.append(
            {
                "week_start": week,
                "week_end": date.fromisoformat(snapshot["week_end"]),
                "generated_at": meta.get("generated_at") or snapshot.get("generated_at"),
                "rebuilt_at": meta.get("rebuilt_at"),
                "distance_m": totals.get("distance_m"),
                "duration_s": totals.get("duration_s"),
                "sessions": totals.get("sessions"),
                "training_load": totals.get("training_load"),
                "elevation_gain_m": totals.get("elevation_gain_m"),
                "fitness": fitness.get("fitness_42d"),
                "fatigue": fitness.get("fatigue_7d"),
                "hrv": week_avg.get("hrv"),
                "rhr": week_avg.get("rhr"),
                "sleep_duration_s": week_avg.get("sleep_duration_s"),
            }
        )
    return entries


def stage_site(paths: ProjectPaths) -> list[date]:
    """Arma el sitio completo en build/public_site (staging previo a dist)."""
    weeks = render_all_to_build(paths)
    staging = paths.public_site
    if staging.exists():
        shutil.rmtree(staging)
    staging.mkdir(parents=True)

    if not weeks:
        (staging / "index.html").write_text(render_unpublished())
        return []

    published = sorted(weeks, reverse=True)[:ARCHIVE_LIMIT]
    latest = published[0]

    for week in published:
        dst_dir = staging / "reports" / week.isoformat()
        dst_dir.mkdir(parents=True)
        # nav dentro del sitio publicado: sólo semanas publicadas
        snapshot = load_snapshot(paths, week)
        meta = load_meta(paths, week)
        html = render_report(snapshot, build_nav(published, week), meta)
        (dst_dir / "index.html").write_text(html)

    archive_dir = staging / "archive"
    archive_dir.mkdir(parents=True)
    (archive_dir / "index.html").write_text(
        render_archive(_archive_entries(paths, published), latest)
    )
    (staging / "index.html").write_text(render_redirect(latest))
    return published


def deploy_dist(paths: ProjectPaths) -> list[date]:
    """Staging -> validación de privacidad -> dist/."""
    published = stage_site(paths)
    validate_public_dir(paths.public_site)
    if paths.dist.exists():
        shutil.rmtree(paths.dist)
    shutil.copytree(paths.public_site, paths.dist)
    return published


def unpublish_dist(paths: ProjectPaths) -> None:
    """Reemplaza dist/ por una página mínima sin links ni datos."""
    if paths.dist.exists():
        shutil.rmtree(paths.dist)
    paths.dist.mkdir(parents=True)
    (paths.dist / "index.html").write_text(render_unpublished())
