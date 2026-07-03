# athlete-report

Reportes semanales de entrenamiento (COROS) con historial navegable, snapshots
congelados y publicación temporal en GitHub Pages.

## Arquitectura en tres capas

1. **Datos normalizados canónicos** (`data/normalized/*.parquet` + `sync_state.json`).
   Pueden actualizarse cuando COROS corrige o sincroniza tarde.
2. **Snapshots de reportes históricos** (`data/reports/YYYY-MM-DD/report.json`).
   Congelados por defecto: nunca se recalculan automáticamente.
3. **Sitio estático público temporal** (`dist/`, listo para GitHub Pages).
   Se valida que no contenga FIT/GPX/JSON/tokens/coordenadas antes de publicar.

`data/` y `build/` están en `.gitignore`. Sólo `dist/` es público.

## Publicación

Sitio: <https://befede.github.io/athlete-report/> — se despliega automáticamente
desde `dist/` al pushear a `main` (workflow `.github/workflows/pages.yml`).

**Flujo semanal**: en Claude Code correr `/weekly-report`. Baja los datos
frescos del MCP de COROS a `data/raw/coros/`, corre `publish` y pushea `dist/`.
Para despublicar: `uv run athlete-report unpublish` + commit de `dist/`.

## Comandos

```bash
uv run athlete-report doctor                    # diagnóstico
uv run athlete-report bootstrap --history-weeks 12
uv run athlete-report sync                      # ingestión incremental idempotente
uv run athlete-report generate-latest [--overwrite]
uv run athlete-report generate --week-start 2026-06-29 [--overwrite]
uv run athlete-report rebuild --from 2026-04-13 --to 2026-06-29
uv run athlete-report publish
uv run athlete-report unpublish
```

- `bootstrap` descarga `history_weeks*7 + 56` días (warm-up para fitness 42 d,
  bloques de 28 d y baselines de 28 d) y genera todas las semanas.
- `sync` usa ventana solapada de 14 días para actividades y 35 días para
  métricas diarias. Upsert por `provider + external_activity_id` y
  `provider + date`. `sync_state.json` sólo se actualiza tras éxito.
- `generate-latest` nunca modifica un snapshot existente sin `--overwrite`.
- `rebuild` conserva el `generated_at` original y registra `rebuilt_at` +
  `rebuild_reason` en `report_meta.json`.
- `unpublish` deja en `dist/` una única página: “No hay un reporte semanal
  publicado actualmente.” Los snapshots locales se conservan.

## Proveedores

Interfaz `AthleteProvider` (`providers/base.py`), sin acoplamiento a MCP ni LLM:

| Proveedor           | Estado                                             |
|---------------------|----------------------------------------------------|
| `CorosMcpProvider`  | **Activo.** Lee dumps JSON crudos del MCP de COROS |
| `CorosApiProvider`  | Placeholder documentado (si hay API oficial)       |
| `GarminProvider`    | Placeholder                                        |
| `StravaProvider`    | Placeholder                                        |
| `FitFileProvider`   | Fallback portable: FIT locales (`uv sync --extra fit`) |

### Cómo alimenta datos el MCP (`CorosMcpProvider`)

Un cliente MCP (por ejemplo Claude con el conector de COROS) descarga
respuestas crudas y las guarda en `data/raw/coros/*.json` con este envoltorio:

```json
{
  "kind": "activities",
  "provider": "coros",
  "fetched_at": "2026-07-03T10:00:00-03:00",
  "items": [ { "...": "objetos nativos del MCP" } ]
}
```

`kind` ∈ `activities` · `daily_metrics` · `training_status` · `activity_detail`.
Ante ids/fechas repetidos gana el dump más nuevo (orden por nombre de archivo),
lo que permite correcciones tardías. El CLI (`sync`, `bootstrap`) normaliza,
deduplica y persiste de forma 100 % determinista — ningún LLM participa en
cálculos, normalización ni persistencia. No hace falta bajar FIT históricos:
alcanza con actividad resumida + métricas diarias; los FIT son bajo demanda
(`fetch_activity_detail` / `FitFileProvider`).

## Tests

```bash
uv run pytest
```

Cubren: semanas completas, bootstrap con warm-up de 56 días, upsert
idempotente, detección de duplicados y modificaciones, snapshots congelados,
rebuild manual de rangos, navegación entre semanas y validación de privacidad
de `dist/`.
