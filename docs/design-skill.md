# jobwatch como skill de Claude Code — Diseño

**Estado:** Diseño en revisión (brainstorming cerrado; `gate-opciones` y
`gate-altitud` corridos e incorporados; pendiente revisión de Juan). Extiende
`docs/design.md`; **no lo reemplaza**.

## 1. Propósito

Empaquetar jobwatch como una **skill pública de Claude Code** para que cualquier
desarrollador que ya usa Claude Code pueda correr el agregador desde su CLI
(`/jobwatch`) **sin necesitar una API key de LLM**: el propio agente de la sesión
hace la puntuación contra el CV. El motor determinista (conectores, dedup, store,
reporte) sigue siendo el paquete Python; la skill es una capa delgada de
orquestación que llega por `pip install jobwatch`.

**Objetivo:** una segunda vía de entrega —skill— sobre el mismo motor, que
mueve el único paso irreduciblemente-LLM (puntuar) del SDK al agente en contexto.

**No-objetivos:**
- No reescribir el motor. La skill no duplica código Python (ver §7, D10).
- No hacer que el agente redacte el reporte a mano (ver §7, D12).
- No soportar corridas concurrentes / multiusuario en el handback (ver §7, D9).
- No cambiar el alcance de portales, el modelo `Vacante`, ni las decisiones
  D1–D7 de `design.md`.

## 2. Relación con el diseño existente

`design.md` define el pipeline de cuatro etapas y las decisiones D1–D7. Este
documento **añade** una descomposición del punto de entrada (`run` → `harvest` +
`report`) que hace posible inyectar a Claude Code como puntuador a través de la
frontera de proceso del CLI, y salda dos deudas heredadas (§6) que esa
descomposición toca de todos modos. Las decisiones nuevas se numeran D8–D15 en el
mismo formato §5d de altitud arquitectónica.

Los **tres conectores colombianos** (Computrabajo, elempleo, Magneto) ya están
especificados en `design.md` §3.1/§4 y `docs/endpoints.md` (selectores reales de
la Fase 0). Este diseño los incorpora al Plan A (§8) sin re-derivar su contrato.

## 3. Arquitectura — la costura de dos fases

El pipeline se parte en dos fases deterministas alrededor del paso LLM:

```
  1) DETERMINISTA (paquete)   jobwatch harvest --config … --json
     conectores → dedup 2 niveles (cross-run + EN-LOTE, §6) → filtro local
     → emite {estados, candidatas[]} a stdout.  SIN LLM, SIN escrituras.
  2) LLM-EN-CONTEXTO (agente) Claude lee data/cv.txt + candidatas
     → {id_estable, estado, puntaje, razon}.  ESTE es el `puntuador`, fuera de proceso.
  3) DETERMINISTA (paquete)   jobwatch report --candidatas … --scores …
     persiste en SQLite + registra corrida + renderiza reportes/AAAA-MM-DD.md.
```

La costura `puntuar(nuevas, cv, puntuador)` que ya existe en `matcher.py` se
convierte en una **frontera de proceso**: como no se puede inyectar un callable
Python a través del CLI, `run` se descompone en `harvest` (emite candidatas) +
`report` (consume puntajes). El agente es el `puntuador`.

## 4. Contrato del CLI

Regla de oro: **`harvest` es de solo-lectura; `report` hace todas las
escrituras** (ver §7, D13). Si el usuario abandona antes de puntuar, una nueva
corrida vuelve a cosechar las mismas ofertas — nada se pierde en silencio (D2).

### 4.0 Core compartido in-process (resuelve el "un solo pipeline")

Antes de los subcomandos: la lógica vive en un **core in-process** que tanto los
subcomandos del CLI como `run` invocan. El CLI es solo un adaptador de
serialización JSON en el borde.

```python
# núcleo, sin I/O de disco ni LLM:
def cosechar(criterios, store, conectores, tope) -> Cosecha
    #   Cosecha = { run_id: str, estados: dict[str, ResultadoConector], candidatas: list[Vacante] }
def validar_scores(cosecha: Cosecha, scores: list[Puntaje]) -> list[OfertaPuntuada]   # FAIL-LOUD
def reportar(cosecha, ofertas, store, fecha) -> str   # persiste + renderiza
```

La **validación fail-loud vive en `validar_scores`** (core), así la ejerce
**tanto** la ruta skill (scores de Claude vía archivo) **como** `run` (scores del
SDK en memoria). No es prosa; es una función testeada.

### 4.1 `jobwatch harvest`
```
jobwatch harvest --config jobwatch.config.json --json
```
- Corre los conectores, deduplica contra el store (cross-run) **y dentro del
  lote** (colapso "vista en N portales", §6), aplica el filtro local.
- **Hace cumplir el tope D6 aquí, determinista:** si
  `len(candidatas) > tope`, aborta con exit≠0 y un JSON `{"error": "tope
  excedido: N > tope"}` — el filtro local dejó pasar de más. El tope deja de ser
  prosa; es un chequeo Python en el core (`cosechar`), igual de duro que el
  `TopeExcedido` del MVP.
- **`run_id`:** hash determinista del conjunto ordenado de `id_estable` de las
  candidatas + `fecha`. Liga esta cosecha a sus puntajes (§4.3).
- Emite a stdout:
  ```json
  {
    "run_id":  "a1b2c3d4",
    "tope":    50,
    "estados": { "computrabajo": {"estado":"ok","detalle":""}, "indeed": {"estado":"error","detalle":"bloqueado: 403"} },
    "candidatas": [ { "id_estable":"…", "titulo":"…", "empresa":"…", "ubicacion":"…",
                      "url":"…", "descripcion_raw":"…", "portales":["computrabajo","elempleo"] } ]
  }
  ```
- **No toca la BD.**

### 4.2 Puntuación (el agente, en la skill)
Claude lee `data/cv.txt` + `candidatas`, aplica la rúbrica embebida (§5) y produce
`scores.json`. **Debe cubrir TODAS las candidatas** (una entrada por
`id_estable`), y eco del `run_id`:
```json
{
  "run_id": "a1b2c3d4",
  "puntajes": [
    { "id_estable":"…", "estado":"puntuada",    "puntaje":78, "razon":"…" },
    { "id_estable":"…", "estado":"sin_puntaje", "puntaje":null, "razon":"CV no aplica" }
  ]
}
```
`estado` ∈ `puntuada | sin_puntaje` (mismo `EstadoOferta` del MVP). `sin_puntaje`
es un ciudadano de primera clase: la oferta se reporta y se persiste marcada, **no
se descarta en silencio** (cierra la regresión de D2).

### 4.3 `jobwatch report` — con validación fail-loud
```
jobwatch report --candidatas candidatas.json --scores scores.json [--fecha AAAA-MM-DD]
```
`report` llama `validar_scores(cosecha, scores)` **antes** de escribir nada.
Aborta con exit≠0 si:
1. `scores.run_id != candidatas.run_id` (scores viejos / desalineados),
2. el conjunto de `id_estable` de `scores` **≠** el de `candidatas` (falta
   alguna, o hay una inventada),
3. algún `puntaje` de una `puntuada` cae fuera de `0–100`.

Solo si valida: **persiste TODAS las candidatas** (puntuadas y `sin_puntaje`) en
SQLite con el hecho multi-portal (§6), **registra la corrida** con
`estados`+`detalle`, y renderiza `reportes/AAAA-MM-DD.md`. Persistir todas (no
solo las puntuadas) es lo que evita el dilema del revisor: las `sin_puntaje`
quedan marcadas vistas (no se re-cosechan para siempre) y aun así aparecen en el
reporte (no se pierden). `--fecha` es opcional; por defecto, hoy.

### 4.4 `run` (ruta API-key, se conserva y se refactoriza)
`run` invoca el **mismo core** (§4.0) in-process:
`cosechar` → puntuar-vía-SDK → `validar_scores` → `reportar`. Sin baile de
archivos; sin lógica duplicada; y la validación de la costura queda ejercida
también por esta ruta. Para cron 100% headless sin Claude Code. **Un solo
pipeline real**, dos puntos de entrada (DRY).

### 4.5 `carta <id_estable>` (bajo demanda, D6)
La oferta ya está en el store (la persistió `report`). En la skill, Claude lee la
oferta + las cartas base del usuario + el CV y redacta. Sin API key.

### 4.6 `--config`
`harvest`/`run` ganan `--config <archivo.json>` que deserializa a `Criterios`
(términos, ubicación, modalidad, salario_min, excluir). El mismo archivo sirve a
la skill y a la ruta cron. El CV vive en `data/cv.txt` (gitignored).

## 5. El bundle de la skill

Es lo único que se distribuye como skill; el motor llega por `pip`.

```
jobwatch-skill/
  SKILL.md                      # frontmatter (name, description=trigger) + instrucciones
  jobwatch.config.example.json  # plantilla de Criterios
  references/scoring-rubric.md   # rúbrica 0–100 (levantada del prompt LLM actual del paquete)
```

**Cero datos personales:** el bundle trae solo la *plantilla* de config; nunca un
CV ni una config rellena.

**Flujo que instruye `SKILL.md`:**
1. **Pre-vuelo:** ¿`jobwatch` instalado? Si no → instruir `pipx install jobwatch`.
   ¿Existe `jobwatch.config.json` y `data/cv.txt`? Si no → guiar el setup de
   primera vez (copiar plantilla, crear CV).
2. `jobwatch harvest --config … --json > candidatas.json`.
3. **Puntuar en contexto** con la rúbrica de `references/scoring-rubric.md` (para
   consistencia entre corridas), respetando el tope; escribir `scores.json`.
4. `jobwatch report --candidatas … --scores … --fecha …`.
5. Mostrar la ruta del reporte; ofrecer `carta <id>` para las mejores.

**Trigger (`description` del frontmatter):** "Agrega ofertas de empleo de portales
colombianos, deduplica, puntúa contra tu CV y reporta solo lo nuevo — desde Claude
Code, sin API key. Trigger: /jobwatch".

**Scheduling comunitario:** el usuario usa el propio `/schedule` de Claude Code
para correr `/jobwatch` en cron (Claude-en-esa-sesión puntúa). Para automatización
100% headless queda `jobwatch run` con API key. Ambas documentadas, sin código
nuevo.

## 6. Las dos deudas heredadas (se saldan aquí)

Viven ahora dentro de `harvest`/`report`, no son un anexo.

### 6.1 Dedup en-lote + colapso "vista en N portales" (D11)
`harvest` (en `cosechar`) deduplica por `fingerprint_contenido` dentro del lote y
colapsa las repetidas en **una fila canónica** que lleva `portales: [...]`.

- **Fila canónica determinista.** El portal canónico se elige por una **prioridad
  explícita** declarada como constante en el paquete:
  `PRIORIDAD_PORTAL = ["computrabajo", "elempleo", "magneto", "indeed"]`
  (orden por estabilidad del id nativo observada en Fase 0; Computrabajo y
  elempleo exponen ids hex/numéricos estables, Indeed depende de JobSpy). La fila
  canónica **fija `portal` → fija `id_estable`** (`calcular_id_estable`), así que
  la identidad es reproducible corrida a corrida, **no** a merced del orden del
  `dict` de conectores. `portales[]` se ordena por esa misma prioridad.
- **Deuda conocida (documentada, no accidental):** al persistir solo lo nuevo, si
  el mismo aviso reaparece luego en un **tercer portal**, `es_nueva` lo bloquea por
  `fingerprint_contenido` y `portales[]` queda congelado en el set del primer
  avistamiento. Aceptable a volumen personal; disparador para refrescar
  `portales[]` en ofertas ya vistas: si el "vista en N portales" se vuelve una
  señal de decisión. Los `id_estable` de los hermanos colapsados no se persisten,
  pero la dedup cross-run sobrevive por `fingerprint_contenido` (`es_nueva` chequea
  ambos).

### 6.2 Propagar `detalle` al reporte
`report` (en `reportar`) registra y renderiza el `detalle` por conector
("bloqueado: 403" vs "N filas omitidas"), no solo el `EstadoConector`.

### 6.3 Migración de schema (diseñada, no solo nombrada)
`store._init_schema` usa hoy `CREATE TABLE IF NOT EXISTS`, que **no** añade
columnas a un `jobwatch.db` existente. Se introduce versionado con
`PRAGMA user_version`:

- **v0 → v1 (esta migración):**
  1. `ALTER TABLE vacantes ADD COLUMN portales TEXT NOT NULL DEFAULT '[]'` (JSON
     array; default vacío para filas legadas).
  2. `PRAGMA user_version = 1`.
- **`detalle` NO necesita columna nueva:** la tabla `corridas` ya guarda
  `estados TEXT` (JSON). Se enriquece ese JSON a `{portal: {estado, detalle}}` —
  cambio de forma del valor, no del schema. Retrocompatible al leer (tolerar la
  forma vieja `{portal: estado}`).
- `_init_schema` corre las migraciones pendientes según `user_version` al abrir el
  store (idempotente). Base nueva: crea v1 directo.

## 7. Altitud arquitectónica (D8–D15)

Formato §5d: (a) mínimo esfuerzo, (b) correcta, (c) elegida + por qué, (d) deuda.

**D8 — Dónde puntúa el LLM (la costura agente↔paquete).**
(a) Fácil: la skill llama `jobwatch run` con API key. No aprovecha a Claude como
LLM y le exige una API key a cada usuario de la comunidad.
(b) Correcta: partir el pipeline en `harvest` (determinista) + puntuación-en-
contexto (Claude) + `report` (determinista).
(c) **Elegida: split.** Es lo que permite "sin API key" y reusa la costura
`puntuar(...,puntuador)` existente como frontera de proceso.
(d) Se conserva `run` (API-key) para headless; dos puntos de entrada, **un**
pipeline (§4.4).

**D9 — Handback de puntajes.**
(a) Fácil-avara: dos archivos con nombres fijos y `report` que confía ciegamente
en el `scores.json` (un scores viejo se une por `id_estable` en silencio).
(b) Correcta: dos archivos JSON **correlacionados por `run_id`** (§4.1/§4.3) y
validados fail-loud en el core antes de escribir (ver D14).
(c) **Elegida: dos archivos + `run_id` + validación.** Sin estado nuevo en el
store (YAGNI frente a una tabla `staging`), pero sin el agujero de confianza ciega
que marcó el `gate-altitud`.
(d) No soporta corridas concurrentes. Disparador para migrar a `staging`: uso
multiusuario o cron solapado. Desacoplado.

**D14 — Validación de la costura agente↔paquete (fail-loud del scoring).**
(a) Fácil: `report` hace un join laxo candidatas⋈scores; ofertas faltantes se
caen, ids inventados o puntajes fuera de rango pasan.
(b) Correcta: `validar_scores` en el **core** exige `run_id` igual, cobertura
**total** de `id_estable` (ni faltantes ni inventadas), y `puntaje ∈ 0–100`;
aborta si no. `sin_puntaje` es explícito, no ausencia.
(c) **Elegida: validación dura en el core**, ejercida por la ruta skill y por
`run` (§4.0). Restaura la garantía que en el MVP daba la construcción Python de
`OfertaPuntuada`, ahora que el productor de puntajes es un agente falible.
(d) Ninguna: es endurecimiento. A 10× (más candidatas) el fail-loud del tope (D6)
corta antes de que la validación vea un lote enorme.

**D15 — Dueño del tope de puntuación (D6) en la nueva costura.**
(a) Fácil: una instrucción en prosa dentro de `SKILL.md` ("no puntúes más de N").
Un agente puede ignorarla; el fail-loud se evapora.
(b) Correcta: el tope es un **chequeo determinista en `cosechar`** — si
`len(candidatas) > tope`, `harvest` aborta antes de involucrar al LLM.
(c) **Elegida: en el core.** El tope mide "el filtro local dejó pasar de más", que
es puramente determinista y no necesita LLM; vive donde vivía en el MVP.
(d) Ninguna. El valor del tope viaja en el JSON de `harvest` para trazabilidad.

**D10 — Distribución del motor.**
(a) Fácil: vendorizar el código Python dentro del bundle de la skill.
(b) Correcta: skill delgada + `pip install jobwatch` (un solo código fuente).
(c) **Elegida: pip.** Vendorizar duplica el repo y garantiza drift.
(d) Exige publicar a PyPI y que el usuario tenga Python/pipx. Pre-vuelo de la
skill lo detecta y guía (§5).

**D11 — Dedup en-lote (representación del colapso).**
(a) Fácil (gate opción A): dropear duplicados en memoria sin persistir el hecho
multi-portal; el portal ganador queda a merced del orden de iteración del `dict`.
(b) Correcta (gate opción C): colapso de primera clase — las candidatas llevan
`portales: [...]`, el store lo persiste y el reporte dice **cuáles**.
(c) **Elegida: C.** §6 de `design.md` exige "Se colapsa en una **fila** marcada
'vista en N portales'" y §8 "una nota sobre **cuáles** se vieron en varios
portales". Un contador (opción B) da la "N" pero no las "cuáles".
(d) Requiere columna `portales` en `vacantes` (migración diseñada en §6.3) y
elegir la fila canónica de forma **determinista** vía la constante
`PRIORIDAD_PORTAL` (§6.1), no el orden del `dict` — porque `portal` determina el
`id_estable`. Deuda conocida del "tercer portal congela `portales[]`" documentada
en §6.1. Derivado por el agente ciego del `gate-opciones` (2026-07-23) y endurecido
por el `gate-altitud`.

**D12 — Reparto paquete/agente (quién renderiza).**
(a) Fácil: el paquete solo cosecha; Claude puntúa **y** redacta el reporte libre
en contexto.
(b) Correcta: el paquete cosecha **y** renderiza+persiste; Claude solo puntúa.
(c) **Elegida: paquete renderiza.** El formato del reporte y el estado "puntuada"
quedan en un solo lugar testeado; la skill se mantiene delgada y estable; fail-
loud intacto. Claude hace solo lo irreduciblemente-LLM.
(d) Menos flexibilidad estética del reporte; se gana reproducibilidad. Si se
quisiera un reporte adaptativo, sería una plantilla en el paquete, no prosa del
agente.

**D13 — Momento de escritura (harvest vs report).**
(a) Fácil: `harvest` persiste las candidatas al cosechar. Si el usuario abandona
antes de puntuar, quedan marcadas "vistas" y no se re-cosechan → pérdida silenciosa.
(b) Correcta: `harvest` solo-lectura; `report` escribe todo tras la puntuación.
(c) **Elegida: report escribe.** Coherente con D2 (fail-loud): abandonar a medias
no borra ofertas del radar.
(d) Ninguna deuda real; `harvest` es idempotente y repetible.

## 8. Alcance y secuenciación — dos planes

Un solo diseño, dos planes de implementación (cada uno = software funcional y
testeable solo):

- **Plan A — Motor multi-portal.** Los 3 conectores colombianos (contrato de
  `design.md` §3.1 + selectores de `endpoints.md`, tests offline contra fixtures
  de `discovery/captures/`) + deuda #1 (dedup en-lote + colapso, D11/§6.1, con la
  **migración de schema de §6.3**) + deuda #2 (`detalle` al reporte, §6.2).
  Implementa estos comportamientos en la estructura actual (`orquestador.correr`
  + `reporte.render`) y entrega un agregador multi-portal funcional por la ruta
  `run`/API-key. **Depende de nada nuevo.**
- **Plan B — CLI + skill.** Extrae el **core in-process** (§4.0:
  `cosechar`/`validar_scores`/`reportar`), descompone `run` → `harvest` +
  `report` con `run_id` y validación fail-loud (D8/D14), añade el tope en el core
  (D15), `--config` (§4.6), refactoriza `run` sobre el core (§4.4), construye el
  bundle de la skill (§5) y **publica a PyPI** (D10). **Depende de A.**

## 9. Distribución / publicación

`pip install jobwatch` exige el paquete en PyPI (o instalable desde GitHub como
fallback: `pipx install git+https://github.com/juanurreamurillo/jobwatch`).
Publicar es una tarea de Plan B: `pyproject.toml` ya declara metadata y
`project.scripts`; falta versionado (subir de `0.0.1`), `LICENSE` (ya existe), y
el build/upload (`python -m build` + `twine`). La skill se publica en su propio
repo/registro de skills, apuntando al paquete.

## 10. Uso responsable / ToS

Hereda `design.md` §10 sin cambios: volumen personal bajo, pausas entre
peticiones, solo lectura de listados públicos, honrar `robots.txt`. La skill no
cambia el perfil de acceso; solo mueve la puntuación del SDK al agente.
