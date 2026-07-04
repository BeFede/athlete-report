"""Lógica de los comandos del CLI. Inyectable para tests (paths/today/now/provider)."""

from __future__ import annotations

from datetime import date, datetime, time, timedelta
from typing import Any

from .config import (
    SYNC_ACTIVITY_OVERLAP,
    SYNC_DAILY_WINDOW,
    WARMUP_DAYS,
    ProjectPaths,
    now_local,
    tz,
)
from .providers import CorosMcpProvider
from .providers.base import AthleteProvider
from .report import build_snapshot, list_snapshot_weeks, snapshot_exists, write_snapshot
from .site import deploy_dist, render_all_to_build, stage_site, unpublish_dist
from .storage import Store
from .weeks import bootstrap_range, is_monday, last_complete_week_start, mondays_between


def default_provider(paths: ProjectPaths) -> CorosMcpProvider:
    return CorosMcpProvider(paths.raw_coros)


def _provider_versions(provider: AthleteProvider) -> dict[str, str]:
    return {provider.provider_name: provider.provider_version}


def _day_bounds(start: date, end: date) -> tuple[datetime, datetime]:
    return (
        datetime.combine(start, time.min, tzinfo=tz()),
        datetime.combine(end, time.max, tzinfo=tz()),
    )


def _enrich_from_details(store: Store, provider: AthleteProvider, activities: list) -> int:
    """Completa carga/desnivel de cada actividad desde su detalle (si existe)
    y persiste el detalle normalizado para embeberlo en snapshots."""
    from .details import normalize_detail

    enriched = 0
    for act in activities:
        raw = provider.fetch_activity_detail(act.external_activity_id)
        if raw is None:
            continue
        detail = normalize_detail(raw.payload)
        store.save_detail(act.provider, act.external_activity_id, detail)
        if act.training_load is None and detail.get("training_load") is not None:
            act.training_load = detail["training_load"]
        if act.elevation_gain_m is None and detail.get("elevation_gain_m") is not None:
            act.elevation_gain_m = detail["elevation_gain_m"]
        enriched += 1
    return enriched


def _ingest_range(
    store: Store,
    provider: AthleteProvider,
    act_start: date,
    act_end: date,
    daily_start: date,
    daily_end: date,
    now: datetime,
) -> dict[str, Any]:
    start_dt, end_dt = _day_bounds(act_start, act_end)
    activities = provider.fetch_activities(start_dt, end_dt)
    daily = provider.fetch_daily_metrics(daily_start, daily_end)
    status = provider.fetch_training_status(daily_start, daily_end)
    enriched = _enrich_from_details(store, provider, activities)
    ingested_at = now.isoformat()
    return {
        "activities": store.upsert_activities(activities, ingested_at),
        "daily_metrics": store.upsert_daily_metrics(daily, ingested_at),
        "training_status": store.upsert_training_status(status, ingested_at),
        "details": enriched,
    }


# ------------------------------------------------------------------- sync
def cmd_sync(
    paths: ProjectPaths,
    provider: AthleteProvider | None = None,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Ingestión incremental idempotente.

    Ventana de actividades solapada 14 días desde la última sync exitosa;
    métricas diarias y status de los últimos 35 días. sync_state.json se
    actualiza sólo si todo terminó bien.
    """
    paths.ensure_base()
    now = now or now_local()
    today = now.date()
    provider = provider or default_provider(paths)
    store = Store(paths)

    state = store.read_sync_state()
    last_sync = state.get("last_sync_at")
    if last_sync:
        act_start = datetime.fromisoformat(last_sync).date() - timedelta(days=SYNC_ACTIVITY_OVERLAP)
    else:
        act_start = today - timedelta(days=SYNC_DAILY_WINDOW - 1)
    daily_start = today - timedelta(days=SYNC_DAILY_WINDOW - 1)

    results = _ingest_range(store, provider, act_start, today, daily_start, today, now)

    store.write_sync_state(
        {
            "provider": provider.provider_name,
            "provider_version": provider.provider_version,
            "last_sync_at": now.isoformat(),
            "last_activity_window": {"start": act_start.isoformat(), "end": today.isoformat()},
            "last_daily_window": {"start": daily_start.isoformat(), "end": today.isoformat()},
        }
    )
    return results


# -------------------------------------------------------------- generación
def _data_as_of(store: Store, now: datetime) -> str:
    return store.read_sync_state().get("last_sync_at") or now.isoformat()


def generate_week(
    paths: ProjectPaths,
    week_start: date,
    *,
    provider: AthleteProvider | None = None,
    now: datetime | None = None,
    overwrite: bool = False,
    rebuild: bool = False,
    rebuild_reason: str | None = None,
) -> str:
    """Genera el snapshot de una semana. Devuelve created|skipped|overwritten|rebuilt."""
    if not is_monday(week_start):
        raise ValueError(f"{week_start} no es lunes; las semanas empiezan en lunes.")
    paths.ensure_base()
    now = now or now_local()
    provider = provider or default_provider(paths)
    store = Store(paths)

    exists = snapshot_exists(paths, week_start)
    if exists and not overwrite and not rebuild:
        return "skipped"

    snapshot = build_snapshot(
        store,
        week_start,
        generated_at=now,
        data_as_of=_data_as_of(store, now),
        provider_versions=_provider_versions(provider),
    )
    write_snapshot(
        paths,
        snapshot,
        overwrite=overwrite,
        rebuild=rebuild,
        rebuilt_at=now.isoformat(),
        rebuild_reason=rebuild_reason,
    )
    if rebuild and exists:
        return "rebuilt"
    return "overwritten" if exists else "created"


def cmd_generate(
    paths: ProjectPaths,
    week_start: date,
    *,
    overwrite: bool = False,
    provider: AthleteProvider | None = None,
    now: datetime | None = None,
) -> str:
    status = generate_week(paths, week_start, provider=provider, now=now, overwrite=overwrite)
    render_all_to_build(paths)
    stage_site(paths)
    return status


def cmd_generate_latest(
    paths: ProjectPaths,
    *,
    overwrite: bool = False,
    provider: AthleteProvider | None = None,
    now: datetime | None = None,
) -> tuple[date, str]:
    """sync + snapshot de la última semana completa + render + índice histórico."""
    now = now or now_local()
    provider = provider or default_provider(paths)
    cmd_sync(paths, provider=provider, now=now)
    week = last_complete_week_start(now.date())
    status = generate_week(paths, week, provider=provider, now=now, overwrite=overwrite)
    render_all_to_build(paths)
    stage_site(paths)
    return week, status


# --------------------------------------------------------------- bootstrap
def cmd_bootstrap(
    paths: ProjectPaths,
    history_weeks: int,
    *,
    overwrite: bool = False,
    provider: AthleteProvider | None = None,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Ingesta history_weeks*7 + 56 días de warm-up y genera todas las semanas."""
    paths.ensure_base()
    now = now or now_local()
    today = now.date()
    provider = provider or default_provider(paths)
    store = Store(paths)

    data_start, data_end, weeks = bootstrap_range(history_weeks, today, WARMUP_DAYS)
    ingest = _ingest_range(store, provider, data_start, data_end, data_start, data_end, now)

    store.write_sync_state(
        {
            "provider": provider.provider_name,
            "provider_version": provider.provider_version,
            "last_sync_at": now.isoformat(),
            "last_activity_window": {"start": data_start.isoformat(), "end": data_end.isoformat()},
            "last_daily_window": {"start": data_start.isoformat(), "end": data_end.isoformat()},
        }
    )

    statuses = {}
    for week in weeks:
        statuses[week.isoformat()] = generate_week(
            paths, week, provider=provider, now=now, overwrite=overwrite
        )
    render_all_to_build(paths)
    stage_site(paths)
    return {
        "data_start": data_start.isoformat(),
        "data_end": data_end.isoformat(),
        "weeks": statuses,
        "ingest": ingest,
    }


# ----------------------------------------------------------------- rebuild
def cmd_rebuild(
    paths: ProjectPaths,
    from_week: date,
    to_week: date,
    *,
    reason: str = "manual",
    provider: AthleteProvider | None = None,
    now: datetime | None = None,
) -> dict[str, str]:
    """Recalcula snapshots SOLO del rango pedido, registrando la reconstrucción."""
    now = now or now_local()
    statuses = {}
    for week in mondays_between(from_week, to_week):
        statuses[week.isoformat()] = generate_week(
            paths, week, provider=provider, now=now, rebuild=True, rebuild_reason=reason
        )
    render_all_to_build(paths)
    stage_site(paths)
    return statuses


# ----------------------------------------------------------- publish/unpub
def cmd_publish(
    paths: ProjectPaths,
    *,
    provider: AthleteProvider | None = None,
    now: datetime | None = None,
) -> tuple[date, list[date]]:
    week, _ = cmd_generate_latest(paths, provider=provider, now=now)
    published = deploy_dist(paths)
    return week, published


def cmd_unpublish(paths: ProjectPaths) -> None:
    unpublish_dist(paths)


# ------------------------------------------------------------------ doctor
def cmd_doctor(paths: ProjectPaths, now: datetime | None = None) -> list[str]:
    now = now or now_local()
    store = Store(paths)
    lines: list[str] = []

    def check(label: str, value: str) -> None:
        lines.append(f"{label}: {value}")

    check("Raíz del proyecto", str(paths.root))
    check("Timezone", str(tz()))
    check("Hoy", now.date().isoformat())
    check("Última semana completa", last_complete_week_start(now.date()).isoformat())

    raw = sorted(paths.raw_coros.glob("*.json")) if paths.raw_coros.exists() else []
    check("Dumps crudos COROS", f"{len(raw)} archivo(s) en {paths.raw_coros}")

    acts = store.load_activities()
    daily = store.load_daily_metrics()
    status = store.load_training_status()
    dates_a = sorted(a["local_date"] for a in acts if a.get("local_date"))
    dates_d = sorted(m["date"] for m in daily if m.get("date"))
    check("Actividades normalizadas", f"{len(acts)}" + (f" ({dates_a[0]} → {dates_a[-1]})" if dates_a else ""))
    check("Métricas diarias", f"{len(daily)}" + (f" ({dates_d[0]} → {dates_d[-1]})" if dates_d else ""))
    check("Training status", str(len(status)))

    state = store.read_sync_state()
    check("Última sync", state.get("last_sync_at", "nunca"))

    weeks = list_snapshot_weeks(paths)
    if weeks:
        check("Snapshots", f"{len(weeks)} ({weeks[0]} → {weeks[-1]})")
    else:
        check("Snapshots", "0 (correr bootstrap o generate-latest)")

    if not paths.dist.exists() or not any(paths.dist.iterdir()):
        check("dist/", "vacío (sin publicar)")
    elif (paths.dist / "reports").exists():
        n = len(list((paths.dist / "reports").iterdir()))
        check("dist/", f"publicado ({n} semanas)")
    else:
        check("dist/", "página de no-publicado")

    return lines
