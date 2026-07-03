"""Configuración de paths, timezone y constantes globales."""

from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

SCHEMA_VERSION = "1.0"
DEFAULT_TZ = "America/Argentina/Buenos_Aires"

# Ventanas de cálculo (días)
FITNESS_WINDOW = 42
FATIGUE_WINDOW = 7
BLOCK_WINDOW = 28
BASELINE_WINDOW = 28
WARMUP_DAYS = 56

# Ventanas de sincronización incremental (días)
SYNC_ACTIVITY_OVERLAP = 14
SYNC_DAILY_WINDOW = 35


def tz() -> ZoneInfo:
    return ZoneInfo(os.environ.get("ATHLETE_REPORT_TZ", DEFAULT_TZ))


def now_local() -> datetime:
    return datetime.now(tz=tz())


def today_local() -> date:
    return now_local().date()


@dataclass(frozen=True)
class ProjectPaths:
    """Rutas del proyecto. `data/` es privado; `dist/` es lo único público."""

    root: Path

    @classmethod
    def from_env(cls) -> "ProjectPaths":
        return cls(root=Path(os.environ.get("ATHLETE_REPORT_ROOT", os.getcwd())).resolve())

    # --- datos canónicos privados ---
    @property
    def data(self) -> Path:
        return self.root / "data"

    @property
    def raw_coros(self) -> Path:
        return self.data / "raw" / "coros"

    @property
    def raw_fit(self) -> Path:
        return self.data / "raw" / "fit"

    @property
    def normalized(self) -> Path:
        return self.data / "normalized"

    @property
    def activities_parquet(self) -> Path:
        return self.normalized / "activities.parquet"

    @property
    def daily_metrics_parquet(self) -> Path:
        return self.normalized / "daily_metrics.parquet"

    @property
    def training_status_parquet(self) -> Path:
        return self.normalized / "training_status.parquet"

    @property
    def sync_state(self) -> Path:
        return self.normalized / "sync_state.json"

    # --- snapshots de reportes ---
    @property
    def reports(self) -> Path:
        return self.data / "reports"

    def report_dir(self, week_start: date) -> Path:
        return self.reports / week_start.isoformat()

    def report_json(self, week_start: date) -> Path:
        return self.report_dir(week_start) / "report.json"

    def report_meta(self, week_start: date) -> Path:
        return self.report_dir(week_start) / "report_meta.json"

    # --- build intermedio ---
    @property
    def build(self) -> Path:
        return self.root / "build"

    @property
    def rendered_reports(self) -> Path:
        return self.build / "rendered_reports"

    @property
    def public_site(self) -> Path:
        return self.build / "public_site"

    # --- sitio público ---
    @property
    def dist(self) -> Path:
        return self.root / "dist"

    def ensure_base(self) -> None:
        for d in (
            self.raw_coros,
            self.raw_fit,
            self.normalized,
            self.reports,
            self.rendered_reports,
            self.public_site,
            self.dist,
        ):
            d.mkdir(parents=True, exist_ok=True)
