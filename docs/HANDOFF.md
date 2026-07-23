# Handoff — continuar jobwatch en una sesión limpia

Este documento le da a una sesión nueva todo lo necesario para retomar sin
re-derivar contexto. Léelo primero, junto con `docs/design.md` (diseño base,
decisiones D1–D7), `docs/design-skill.md` (jobwatch como skill de Claude Code,
D8–D15) y `docs/endpoints.md` (Fase 0).

## Estado actual (2026-07-23)

Todo está en `main` del repo público `github.com/juanurreamurillo/jobwatch`.

- **MVP completo** (mergeado): modelos, normalización, store SQLite con dedup de
  dos niveles, matcher híbrido (filtro local + puntuación LLM con tope y
  fail-loud), conector **Indeed** (vía JobSpy), reporte Markdown, orquestador,
  CLI, y cartas bajo demanda.
- **Fase 0 ejecutada** (mergeada): `discovery/probe.py` corrió con `curl_cffi`
  contra los tres portales colombianos; `docs/endpoints.md` tiene los hallazgos
  reales.
- **Plan A completo** (mergeado, PR #1): **motor multi-portal.** Los tres
  conectores colombianos existen y cumplen el contrato
  `buscar(criterios, fetch=None) -> ResultadoConector`:
  - `conectores/computrabajo.py` — DOM `article.box_offer`.
  - `conectores/elempleo.py` — JSON-LD `ItemList` + card `data-ga4-offerdata`.
  - `conectores/magneto.py` — JSON-LD `ItemList` + filtro **client-side** por
    término (su `?search=` no filtra server-side; ver Backlog D5).
  - `conectores/_comun.py` — envoltorio fail-loud compartido `ejecutar`, más
    helpers (`slug`, `id_de_url`, `texto`, `coincide_termino`).
  - Tests offline contra fixtures recortados en `tests/conectores/fixtures/`.
  - **Deudas saldadas:** dedup en-lote con colapso "vista en N portales"
    (`colapsar_lote` + `PRIORIDAD_PORTAL`, cableado en `correr`); `detalle` por
    conector propagado al reporte y a `corridas`; migración de schema
    (`PRAGMA user_version` + columna `portales`, retrocompatible con BD v0).
  - **69 tests, ruff limpio.**

### Cómo trabajar en este repo

- Entorno: `python -m venv .venv && .venv/bin/pip install -e .` (trae
  `beautifulsoup4`, `lxml`, `curl_cffi`, `extruct`, `pydantic`, `python-jobspy`).
- Tests: `.venv/bin/pytest -q`. Lint: `.venv/bin/ruff check src tests`.
  pytest resuelve `src/` y la raíz vía `pythonpath` en `pyproject.toml`.
- **Repo público — nada personal:** commits con email noreply de GitHub (identidad
  local ya configurada); nunca commitear `secrets/`, `data/`, `reportes/`, `*.db`,
  ni `discovery/captures/` (todo en `.gitignore`). Copy de cara al usuario en español.
- Proceso usado: gates de gobierno (`gate-opciones`, `gate-altitud`) sobre el
  diseño; luego TDD estricto con subagente por tarea + revisión de dos etapas +
  revisión adversarial de rama completa. El ledger de progreso del Plan A vive en
  `.superpowers/sdd/progress.md` (git-ignored).

## Siguiente plan: Plan B — jobwatch como skill de Claude Code

Diseño en `docs/design-skill.md`. Objetivo: empaquetar jobwatch como **skill
pública de Claude Code** para que el desarrollador corra el agregador desde su CLI
**sin API key** — el propio agente de la sesión puntúa contra el CV. Escribir y
ejecutar el plan (usar `superpowers:writing-plans` →
`superpowers:subagent-driven-development`). Alcance (design-skill.md §4, §5, §8):

- **Core in-process** (§4.0): extraer `cosechar` / `validar_scores` / `reportar`
  de la lógica actual, para que tanto los subcomandos del CLI como `run` lo usen.
- **Split `run` → `harvest` + `report`** (D8): `harvest` (determinista, sin LLM,
  solo-lectura) emite candidatas JSON con un `run_id`; Claude las puntúa en
  contexto; `report` valida **fail-loud** (D14: `run_id` igual, cobertura total de
  `id_estable`, `puntaje ∈ 0–100`) y persiste+renderiza. El tope D6 se hace cumplir
  en `harvest` (D15). `run` (ruta API-key, headless) se refactoriza sobre el core.
- **`--config`** (§4.6): archivo que deserializa a `Criterios`, compartido por
  skill y cron.
- **Bundle de la skill** (§5): `SKILL.md` + `jobwatch.config.example.json` +
  `references/scoring-rubric.md`. Cero datos personales.
- **Publicar a PyPI** (§9/D10): la skill instala `jobwatch` vía `pip`.

## Backlog heredado del Plan A (no bloquea, documentado)

- **D5 — Magneto:** `?search=` no filtra server-side y `slug` no quita acentos.
  Reconfirmar el parámetro de búsqueda correcto con un probe dedicado; endurecer la
  extracción posicional de `<p>` (salario 1º / ubicación 2º) y el guard del
  panel-detalle (hoy inclusión-only).
- **Endurecer tests:** el test de migración v0 no inserta fila antes de migrar
  (no prueba literal "no se pierde fila"); falta test de reapertura v1; el e2e no
  asevera `COUNT(*)` en el store; empresa/ubicación vacías no cuentan como
  `omitidas`.
- **Consistencia menor:** `indeed.buscar` nombra su segundo parámetro `scrape` en
  vez de `fetch` (los tres nuevos usan `fetch`).
- **Nota cross-run:** `portales[]` no se refresca si una oferta ya vista reaparece
  en otro portal en una corrida posterior (`es_nueva` la bloquea por
  `fingerprint_contenido`). Inherente al colapso en-lote; dentro del alcance del
  diseño (design-skill.md §6.1).

## Verificación end-to-end (opcional, ruta `run`/API-key)

```bash
mkdir -p data && cp /ruta/a/tu-cv.txt data/cv.txt   # data/ está en .gitignore
ANTHROPIC_API_KEY=… .venv/bin/jobwatch run \
  --terminos "Gerente de Proyectos TI" --ubicacion "Colombia" --cv data/cv.txt
```

Corre los cuatro conectores (Computrabajo, elempleo, Magneto, Indeed). Reporte en
`reportes/AAAA-MM-DD.md`. Carta bajo demanda:
`jobwatch carta <id_estable> --cv data/cv.txt`.
