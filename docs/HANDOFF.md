# Handoff — continuar jobwatch en una sesión limpia

Ficha para que una sesión nueva retome sin re-derivar contexto. Léela junto a
`docs/design.md` (D1–D7), `docs/design-skill.md` (D8–D15), `docs/design-plan-c.md`
(D16–D22) y `docs/endpoints.md` (Fase 0 + investigación de Magneto).

## Goal

Buscador de empleo multi-portal (Computrabajo, elempleo, Magneto, Indeed) que
deduplica, puntúa contra el CV y reporta solo lo nuevo. Uso personal, cron, bajo
volumen. Repo público `github.com/juanurreamurillo/jobwatch`.

## Current Progress (2026-07-24)

- **MVP, Fase 0, Plan A (PR #1), Plan B (PR #2), Plan C (PR #3): mergeados a `main`.**
- **CI activo** (`.github/workflows/ci.yml`): ruff + vulture + pytest en Python 3.10 y
  3.12, verde en `main`. **169 tests.**
- Plan C entrega búsqueda por **cargo + remoto + últimos N días**, con filtro de
  recencia central en `cosechar` (`hoy` inyectado, D22) y paginación fail-loud.
- **La primera corrida real destapó seis defectos que los 128 tests no veían.** Todos
  corregidos en PR #3; el detalle de cada uno está en el cuerpo del PR.

## What Worked

- **Ejecutar contra datos reales.** Los seis defectos eran invisibles para la suite:
  descripciones vacías, un `coincide_termino` que nunca se cableó, `is_remote=False`
  leído como "no sé", un 404 de fin de paginación reportado como error, timeouts de
  Magneto que borraban la fuente entera, y dos falsos negativos de relevancia.
- **`vulture` en el lint.** Nació del defecto #2: los tests no ven el código muerto
  —ellos sí lo llaman—, solo un análisis de alcance sobre `src/` lo delata.
- **Descubrimiento con raw_signal** antes de diseñar (chrome-devtools + `curl_cffi` +
  `jsluice` sobre los bundles). Ver el runbook de herramientas en `docs/endpoints.md`.
- **Verificar la hipótesis antes de implementarla.** Dos conclusiones propias cayeron
  al contrastarlas: "Magneto no hace peticiones de API" y "hay un muro de paginación
  en la página 4". Ninguna llegó al código.

## What Didn't Work

- **Un escaneo estático que no abre los bundles JS** no puede afirmar que un portal no
  tiene API. Omitirlo produjo la conclusión falsa de "cero rutas `/api/`" en Magneto.
- **Linters sin techo de versión.** El primer CI falló con 51 hallazgos sobre código
  intacto porque `ruff>=0.5` instala el último release. Ahora `ruff>=0.15,<0.16`.
- `ai_search_jobs` del MCP de Magneto **no sirve como fuente del listado**: ignora la
  recencia y trunca en silencio (`total=23`, devuelve 10).
- Magneto tiene **latencia de cola errática en cualquier página** (no un muro por
  profundidad): la misma URL da timeout de 45 s y responde en 0,8 s al reintentar.
- `?paginator[page]=N` de Magneto se ignora (client-side); el que SÍ pagina por URL es
  el segmento de ruta `/pagina-N`. elempleo `?PublishDate=hoy` solo confirmado para
  `dias<=2`; `?PublishDate=semana` NO es token válido.

## Next Steps

1. **Sondear https://vacantes.com/** como conector nuevo (pedido de Juan, 2026-07-24).
   Seguir el runbook de Fase 0 de `docs/endpoints.md`; **abrir los bundles con
   `jsluice`**, no solo el documento.
2. **Migrar a un ruff más estricto en su propio PR**, con su limpieza: 51 hallazgos
   preexistentes (BLE001 sobre los `except` genéricos que SON el patrón fail-loud,
   I001, DTZ011, S112, UP035). No colarlo de rebote en un PR de conectores.
3. Backlog en `docs/design-plan-c.md` §9: tokens de fecha de elempleo para `dias>2`;
   flag `cobertura_completa` (hoy es prosa en `detalle`); vigilar volumen/ToS.
4. Magneto emite la descripción por su **MCP oficial** (`get_job_detail`, ~4 KB / 0,2 s)
   con el extractor JSON-LD como respaldo. Uso aprobado por el responsable del repo;
   razones registradas en `docs/endpoints.md`.

## Cómo trabajar en este repo

- Entorno: `.venv/bin/pip install -e ".[dev]"`. Tests: `.venv/bin/pytest -q`. Lint:
  `.venv/bin/ruff check src tests` y `.venv/bin/vulture`. Herramientas de descubrimiento:
  `pip install -e ".[discovery]"` (mitmproxy2swagger); `jsluice` y `curlconverter` se
  instalan aparte — ver `docs/endpoints.md`.
- **La suite es offline por diseño**: los conectores reciben `fetch`/`post` inyectados
  y los imports de red son perezosos. Si un test empieza a tardar decenas de segundos,
  se le escapó una petición real.
- Repo público: nada personal en commits (`data/`, `reportes/`, `secrets/`, `*.db`,
  `candidatas.json`, `scores.json`, `jobwatch.config.json`, `.codegraph/` en
  `.gitignore`); copy en español.
- Ledger de progreso Plan C (git-ignored): `.superpowers/sdd/progress.md`.
