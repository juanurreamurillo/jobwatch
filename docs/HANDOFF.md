# Handoff — continuar jobwatch en una sesión limpia

Este documento le da a una sesión nueva todo lo necesario para retomar sin
re-derivar contexto. Léelo primero, junto con `docs/design.md` y
`docs/endpoints.md`.

## Estado actual (2026-07-23)

Todo está en `main` del repo público `github.com/juanurreamurillo/jobwatch`.

- **MVP completo** (mergeado): modelos, normalización, store SQLite con dedup de
  dos niveles, matcher híbrido (filtro local + puntuación LLM con tope y
  fail-loud), conector **Indeed** (vía JobSpy), reporte Markdown, orquestador,
  CLI, y cartas bajo demanda. **42 tests, ruff limpio.**
- **Fase 0 ejecutada** (mergeada): `discovery/probe.py` corrió con `curl_cffi`
  contra los tres portales colombianos; `docs/endpoints.md` tiene los hallazgos
  reales. Los conectores colombianos **aún no existen** — son el siguiente plan.

### Cómo trabajar en este repo

- Entorno: `python -m venv .venv && .venv/bin/pip install -e .` (o solo
  `pydantic pytest ruff` para los tests; `curl_cffi extruct` para el probe/conectores).
- Tests: `.venv/bin/pytest -q`. Lint: `.venv/bin/ruff check src tests`.
  pytest resuelve `src/` y la raíz vía `pythonpath` en `pyproject.toml`.
- **Repo público — nada personal:** commits con email noreply de GitHub (identidad
  local ya configurada); nunca commitear `secrets/`, `data/`, `reportes/`, `*.db`,
  ni `discovery/captures/` (todo en `.gitignore`). Copy de cara al usuario en español.
- Proceso usado: TDD estricto (test que falla → implementación mínima → commit) con
  subagente por tarea + revisión. El diseño pasó los gates de gobierno
  (`gate-altitud`, decisiones D1–D7 en `design.md` §5d).

## Siguiente plan: los tres conectores colombianos

Escribir y ejecutar un plan (usar `superpowers:writing-plans` →
`superpowers:subagent-driven-development`) para **Computrabajo, elempleo y
Magneto**. Cada uno es un archivo nuevo en `src/jobwatch/conectores/` que cumple
el mismo contrato, sin tocar el núcleo:

```python
def buscar(criterios: Criterios, fetch=None) -> ResultadoConector: ...
```

Inyectar el fetch (curl_cffi) como callable, igual que Indeed inyecta `scrape`,
para que los tests corran offline contra un **fixture de HTML recortado** tomado
de `discovery/captures/{portal}.html`. Cada conector debe: emitir `Vacante`
normalizado (normalización dentro del conector, D7), ser **fail-loud** (ERROR vs
OK-vacío, D2), y producir un **id nativo estable** (D3).

### Datos reales de la Fase 0 (de `docs/endpoints.md`)

Sondeados el 2026-07-23 con "gerente de proyectos"; los tres dieron HTTP 200 sin
bloqueo (curl_cffi `chrome124` pasa Cloudflare en Computrabajo).

| Portal | URL de búsqueda | Fuente del listado | Id nativo |
|---|---|---|---|
| Computrabajo | `https://co.computrabajo.com/trabajo-de-{slug}` | DOM `article.box_offer` | `data-id` (hash hex de 32) |
| elempleo | `https://www.elempleo.com/co/ofertas-empleo/trabajo-{slug}` | JSON-LD `ItemList` + card DOM | dígitos finales de la URL / `data-id` |
| Magneto | `https://www.magneto365.com/co/trabajos/buscar?search={q}` | JSON-LD `ItemList` + card DOM | dígitos finales de `/co/empleos/…-{id}` |

- **Computrabajo:** título `article > h2 > a.js-o-link`; url = su `href`; id = `data-id`.
  Empresa/salario/ubicación en los `<p>`/`<span>` del `article` — fijar selectores
  con TDD contra el fixture.
- **elempleo:** iterar `ItemList` (título `item.name`, url `item.@id`, id = dígitos
  finales); empresa/salario/ubicación del card en el DOM (emparejar por id).
- **Magneto:** iterar `ItemList` (url = `ListItem.url`, id = dígitos finales);
  confirmar que `?search=` filtra por término; título/empresa/salario/ubicación
  del card o del slug.

Ninguno trae `JobPosting` JSON-LD en resultados → los tres parsean el DOM.
Añadir `beautifulsoup4` o usar `lxml` (ya viene con extruct) como parser.

### Deuda que este plan DEBE saldar (heredada del MVP)

1. **Dedup dentro de la misma corrida (§6, prioridad alta).** Hoy `correr()`
   (`orquestador.py`) deduplica solo contra el store de corridas previas, no
   dentro del lote actual. Con varios conectores, la misma oferta vista en dos
   portales en una corrida se persiste dos veces. Añadir dedup por
   `fingerprint_contenido` dentro del lote y colapsar en "vista en N portales".
2. **Propagar `detalle` del conector al reporte (D2).** Hoy el reporte muestra
   `ERROR` por conector pero no el motivo (`ResultadoConector.detalle` se
   descarta en `correr` y `reporte.render`). Enriquecer render para mostrar
   "bloqueado" vs "N filas omitidas".

### Notas menores abiertas (no bloqueantes)

- `parsear_salario` (`normalizar.py`): heurística `len>=5` puede dar falso
  positivo con números sueltos de ≥5 dígitos (ids de referencia).
- `Vacante` recomputa `id_estable`/`fingerprint` solo al construir (sin
  `validate_assignment`); ok mientras se trate como inmutable.
- `store.persistir` usa `ON CONFLICT DO NOTHING`; revisar si al persistir todo lo
  cosechado (no solo lo nuevo) hiciera falta refrescar datos.
- Mejora opcional al probe: `extraer_jsonld` no aplana `@graph` (por eso el
  `ItemList` de Computrabajo no se detecta como tal); irrelevante para el DOM.

## Verificación end-to-end del MVP (opcional, antes o después)

```bash
mkdir -p data && cp /ruta/a/tu-cv.txt data/cv.txt   # data/ está en .gitignore
ANTHROPIC_API_KEY=… .venv/bin/jobwatch run \
  --terminos "Gerente de Proyectos TI" --ubicacion "Colombia" --cv data/cv.txt
```

Reporte en `reportes/AAAA-MM-DD.md`. Carta bajo demanda:
`jobwatch carta <id_estable> --cv data/cv.txt`.
