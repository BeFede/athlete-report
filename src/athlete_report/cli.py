"""CLI: uv run athlete-report <comando>."""

from __future__ import annotations

import argparse
import sys
from datetime import date

from . import commands
from .config import ProjectPaths
from .privacy import PrivacyError
from .report import SnapshotExistsError

STATUS_ES = {
    "created": "generado",
    "skipped": "ya existía, no se modificó (usar --overwrite)",
    "overwritten": "sobrescrito",
    "rebuilt": "reconstruido",
}


def _date(value: str) -> date:
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError(f"fecha inválida: {value} (usar YYYY-MM-DD)") from exc


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="athlete-report",
        description="Reportes semanales de entrenamiento con snapshots históricos congelados.",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("doctor", help="Diagnóstico del estado del sistema")

    p = sub.add_parser("bootstrap", help="Carga inicial: historial + warm-up de 56 días")
    p.add_argument("--history-weeks", type=int, default=12)
    p.add_argument("--overwrite", action="store_true")

    sub.add_parser("sync", help="Ingestión incremental idempotente")

    p = sub.add_parser("generate-latest", help="sync + snapshot de la última semana completa")
    p.add_argument("--overwrite", action="store_true")

    p = sub.add_parser("generate", help="Genera el snapshot de una semana puntual")
    p.add_argument("--week-start", type=_date, required=True, metavar="YYYY-MM-DD")
    p.add_argument("--overwrite", action="store_true")

    p = sub.add_parser("rebuild", help="Reconstrucción explícita de un rango histórico")
    p.add_argument("--from", dest="from_week", type=_date, required=True, metavar="YYYY-MM-DD")
    p.add_argument("--to", dest="to_week", type=_date, required=True, metavar="YYYY-MM-DD")
    p.add_argument("--reason", default="manual")

    sub.add_parser("publish", help="generate-latest + valida privacidad + arma dist/")
    sub.add_parser("unpublish", help="Reemplaza dist/ por página mínima sin datos")

    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    paths = ProjectPaths.from_env()

    try:
        if args.command == "doctor":
            paths.ensure_base()
            for line in commands.cmd_doctor(paths):
                print(line)

        elif args.command == "bootstrap":
            result = commands.cmd_bootstrap(paths, args.history_weeks, overwrite=args.overwrite)
            print(f"Datos ingeridos: {result['data_start']} → {result['data_end']}")
            for kind, res in result["ingest"].items():
                print(f"  {kind}: {res}")
            for week, status in result["weeks"].items():
                print(f"Semana {week}: {STATUS_ES[status]}")

        elif args.command == "sync":
            result = commands.cmd_sync(paths)
            for kind, res in result.items():
                print(f"{kind}: {res}")

        elif args.command == "generate-latest":
            week, status = commands.cmd_generate_latest(paths, overwrite=args.overwrite)
            print(f"Semana {week}: {STATUS_ES[status]}")

        elif args.command == "generate":
            status = commands.cmd_generate(paths, args.week_start, overwrite=args.overwrite)
            print(f"Semana {args.week_start}: {STATUS_ES[status]}")

        elif args.command == "rebuild":
            statuses = commands.cmd_rebuild(paths, args.from_week, args.to_week, reason=args.reason)
            for week, status in statuses.items():
                print(f"Semana {week}: {STATUS_ES[status]}")

        elif args.command == "publish":
            week, published = commands.cmd_publish(paths)
            print(f"Publicado. Última semana: {week}. Semanas en dist/: {len(published)}")
            print(f"dist/ listo para GitHub Pages: {paths.dist}")

        elif args.command == "unpublish":
            commands.cmd_unpublish(paths)
            print("dist/ reemplazado por página mínima. Snapshots locales intactos.")

    except SnapshotExistsError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    except PrivacyError as exc:
        print(f"Error de privacidad, publicación abortada:\n{exc}", file=sys.stderr)
        return 1
    except (ValueError, FileNotFoundError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
