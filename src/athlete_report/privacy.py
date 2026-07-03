"""Validación de privacidad del sitio público.

`dist/` sólo puede contener HTML/CSS renderizado. Nada de FIT, GPX, JSON
crudo, parquet, tokens ni coordenadas.
"""

from __future__ import annotations

import re
from pathlib import Path

FORBIDDEN_EXTENSIONS = {
    ".fit", ".gpx", ".tcx", ".json", ".parquet", ".csv",
    ".db", ".sqlite", ".sqlite3", ".pkl", ".env",
}

TEXT_EXTENSIONS = {".html", ".htm", ".css", ".js", ".txt", ".xml", ".svg"}

CONTENT_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    ("posible token/credencial", re.compile(r"(?i)\b(api[_-]?key|access[_-]?token|refresh[_-]?token|client[_-]?secret|bearer\s+[A-Za-z0-9._\-]{10,})\b")),
    ("clave de coordenadas", re.compile(r"(?i)[\"']?(latitude|longitude|start_lat|start_lng|end_lat|end_lng|lat_lng)[\"']?\s*[:=]")),
    ("par de coordenadas decimales", re.compile(r"-?\d{1,3}\.\d{4,}\s*,\s*-?\d{1,3}\.\d{4,}")),
    ("referencia a datos crudos", re.compile(r"data/raw")),
]


class PrivacyError(Exception):
    def __init__(self, violations: list[str]):
        self.violations = violations
        super().__init__(
            "El sitio público contiene información privada:\n" + "\n".join(f"  - {v}" for v in violations)
        )


def scan_public_dir(public_dir: Path) -> list[str]:
    violations: list[str] = []
    if not public_dir.exists():
        return violations
    for path in sorted(public_dir.rglob("*")):
        if not path.is_file():
            continue
        rel = path.relative_to(public_dir)
        suffix = path.suffix.lower()
        if suffix in FORBIDDEN_EXTENSIONS:
            violations.append(f"{rel}: extensión prohibida ({suffix})")
            continue
        if suffix in TEXT_EXTENSIONS:
            try:
                text = path.read_text(errors="ignore")
            except OSError:
                violations.append(f"{rel}: no se pudo leer para validar")
                continue
            for label, pattern in CONTENT_PATTERNS:
                if pattern.search(text):
                    violations.append(f"{rel}: {label}")
    return violations


def validate_public_dir(public_dir: Path) -> None:
    violations = scan_public_dir(public_dir)
    if violations:
        raise PrivacyError(violations)
