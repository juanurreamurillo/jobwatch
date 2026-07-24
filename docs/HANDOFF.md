# Handoff — continuar jobwatch en una sesión limpia

Ficha para que una sesión nueva retome sin re-derivar contexto. Léela junto a
`docs/design.md` (D1–D7), `docs/design-skill.md` (D8–D15), `docs/design-plan-c.md`
(D16–D22) y `docs/endpoints.md` (Fase 0).

## Goal

Buscador de empleo multi-portal (Computrabajo, elempleo, Magneto, Indeed) que
deduplica, puntúa contra el CV y reporta solo lo nuevo. Uso personal, cron, bajo
volumen. Repo público `github.com/juanurreamurillo/jobwatch`.

## Current Progress (2026-07-23)

- **MVP, Fase 0, Plan A (PR #1), Plan B (PR #2): mergeados a `main`.** MVP (modelos,
  store SQLite con dedup, matcher híbrido, reporte, CLI, cartas); conectores CO
  multi-portal; jobwatch como skill de Claude Code + release 0.1.0.
- **Plan C — modalidad remoto + recencia: COMPLETO en PR #3, pendiente de review/merge.**
  Rama `feat/plan-c-recencia-remoto`. **128 tests verdes, ruff limpio.**
  - Búsqueda por **cargo + remoto + últimos N días** (`Criterios.dias`).
  - Filtro de recencia **central** en `cosechar` con `hoy` inyectado (D22); conectores
    guardan fecha **cruda**, el core normaliza a ISO. Predicado `(hoy-fecha).days < dias`.
  - Paginación fail-loud en `ejecutar`: parada por tarjetas crudas (`n_crudo`, no
    filtradas); tope/corte → cobertura parcial en `detalle`, nunca en silencio.
  - Computrabajo `-en-remoto?pubdate&by=publicationtime&p=N`; elempleo
    `-modalidad-remoto/{N}?PublishDate=hoy`; Magneto ruta de término `/pagina-N` +
    **parser del flight RSC** (`isRemote`, `publishDate` ISO); Indeed `is_remote`+`hours_old`.
  - "Sin inglés" → puntuación en contexto + `excluir` (D20).

## What Worked

- Descubrimiento con raw_signal real (chrome-devtools contra Chrome de Windows +
  `curl_cffi`) antes de diseñar. Corrigió supuestos falsos (Magneto RSC, selectores).
- Gates de gobierno (opciones/altitud/premisas) + revisión adversarial de rama:
  cazaron el `date.today()` en conectores (S2), la parada por vacantes filtradas (B1),
  y el sub-fetch de `_pubdate_para` para `dias>15`.
- TDD subagente-por-tarea con revisión de dos etapas.

## What Didn't Work

- `?paginator[page]=N` de Magneto se ignora (client-side); el que SÍ pagina por URL es
  el segmento de ruta `/pagina-N` (en la ruta de término, no en `/remoto`).
- elempleo `?PublishDate=hoy` solo confirmado para `dias≤2`; `?PublishDate=semana` NO
  es token válido (se ignora).

## Next Steps

1. **Revisar y mergear PR #3** (`gh pr view 3`). El caso primario (`dias=2`, remoto)
   funciona; la rama quedó lista tras el fix del bloqueante de la review de rama.
2. Backlog documentado en `docs/design-plan-c.md` §9 (no bloquea): capturar tokens de
   fecha de elempleo para `dias>2`; considerar flag `cobertura_completa` (hoy es prosa
   en `detalle`); vigilar volumen/ToS al paginar.
3. Verificación e2e opcional (con API key):
   `jobwatch run --terminos "Gerente de Proyectos TI" --ubicacion Colombia --modalidad remoto --dias 2 --cv data/cv.txt`

## Cómo trabajar en este repo

- Entorno: `.venv/bin/pip install -e .`. Tests: `.venv/bin/pytest -q`. Lint:
  `.venv/bin/ruff check src tests`. Repo público: nada personal en commits
  (`data/`, `reportes/`, `secrets/`, `*.db` en `.gitignore`); copy en español.
- Ledger de progreso Plan C (git-ignored): `.superpowers/sdd/progress.md`.
