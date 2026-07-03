---
description: Baja datos frescos de COROS vía MCP, genera el reporte de la última semana completa y lo publica en GitHub Pages
---

Sos el paso de ingestión del sistema athlete-report. Tu trabajo: bajar datos frescos del MCP de COROS, dejarlos como dumps crudos en `data/raw/coros/`, y dejar que el CLI (determinista, sin LLM) haga todo lo demás. NUNCA calcules métricas ni edites snapshots a mano.

Argumentos opcionales: `$ARGUMENTS` (por ejemplo `--overwrite` para regenerar la última semana si ya existía).

## Paso 1 — Descargar datos del MCP de COROS

Ventanas (hoy = fecha local America/Argentina/Buenos_Aires):
- Actividades: últimos 21 días (cubre la ventana solapada de 14 días del sync).
- Métricas diarias y training load: últimos 35 días.

Tools del MCP de COROS (conector `b9aae74a-...`; cargalas con ToolSearch si están deferred):
1. `querySportRecords` — ES la lista de actividades. Pasar `startDate`/`endDate` en `yyyyMMdd`, `sportTypeCodes: [65535]`, `limit: 200`, timezone `America/Argentina/Buenos_Aires`, y para el resto de los filtros valores neutros (min 0 / max enormes / strings vacíos).
2. `queryTrainingLoadAssessment` — `days: 35` (la API sólo devuelve ~31 días; es esperado).
3. `queryRestingHeartRate` — `days: 35`.
4. `querySleepData` — rango `startDate`/`endDate` de 35 días.
5. `querySleepHrv` — en bloques de 7 días (5 llamadas) para no exceder el límite de output; usar SOLO la sección "HRV Assessment" (HRV Avg por día), ignorar las series temporales.

## Paso 2 — Escribir dumps crudos

Un JSON por kind en `data/raw/coros/`, nombre `YYYYMMDD_<kind>.json` (fecha de hoy). Envoltorio:

```json
{"kind": "<kind>", "provider": "coros", "fetched_at": "<ISO local con offset>", "items": [...]}
```

Items canónicos (parsear las respuestas de texto del MCP con un script Python en el scratchpad, no a mano):

- `kind: "activities"`: `{"id": labelId, "name": "<label> — <location>", "sport": <ver mapa>, "start_time": <startTimestamp epoch segundos, int>, "duration_s": <Duration parseada>, "distance_m": <km*1000 o null>, "avg_hr": int|null, "calories": int|null}`
  Mapa sportType → sport: 100 run, 101 indoor_run, 102 trail_run, 103 track_run, 104 hike, 402 strength; otro código → str(código). NO incluir coordenadas.
- `kind: "daily_metrics"`: `{"date": "YYYY-MM-DD", "hrv": <HRV Avg>, "resting_hr": <rhr>, "sleep_duration_s": <Main Sleep en segundos>, "sleep_score": int}` — mergear las cuatro fuentes por fecha en UN solo archivo (el provider pisa por fecha, no mergea entre archivos).
- `kind: "training_status"`: `{"date": "YYYY-MM-DD", "fitness": <Long-Term Load>, "fatigue": <Short-Term Load>, "status": "<Comment>"}`

Está bien que la ventana se solape con dumps anteriores: el sync deduplica por id/fecha y el dump más nuevo gana.

## Paso 3 — Generar y publicar

```bash
uv run athlete-report publish
```

(agregar `--overwrite` a un `generate-latest` previo sólo si el usuario lo pidió en `$ARGUMENTS`). Si la validación de privacidad falla, NO publicar: mostrar las violaciones y parar.

Verificar con `uv run athlete-report doctor` que la última semana completa tiene snapshot.

## Paso 4 — Deploy a GitHub Pages

```bash
git add dist && git commit -m "Publicar semana <YYYY-MM-DD del lunes>" && git push
```

El workflow `.github/workflows/pages.yml` despliega `dist/` automáticamente. Commitear SOLO `dist/` (data/ y build/ están gitignoreados; jamás forzar su inclusión).

## Reglas

- No usar `--overwrite` ni `rebuild` salvo pedido explícito del usuario.
- No modificar archivos en `data/reports/` a mano.
- Si un tool del MCP falla o devuelve vacío, reportarlo y seguir con lo que haya (el reporte muestra la cobertura real).
- Al final, resumir: semana generada, cobertura, totales, fitness/fatiga, y URL de Pages.
