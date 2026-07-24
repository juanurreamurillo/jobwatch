# jobwatch — Diseño Plan C: modalidad remoto + recencia

**Estado:** Diseño en revisión (gates + revisión adversarial corridos), pendiente de
plan de implementación. Continúa `docs/design.md` (D1–D7) y `docs/design-skill.md`
(D8–D15). Decisiones nuevas D16–D22 en el mismo formato §5d de altitud arquitectónica
(§8). Descubrimiento y raw_signal en `docs/plan-c-descubrimiento.md`.

## 1. Propósito

Los conectores colombianos (Computrabajo, elempleo, Magneto) hoy solo buscan por
**keyword**: no fijan modalidad, no construyen URL filtrada por remoto, no extraen
fecha de publicación. Plan C activa los **filtros nativos de remoto** y añade
**recencia** (últimos N días), de modo que una corrida pueda pedir:
*cargo + modalidad remoto + publicadas en la ventana de recencia*. El requisito de
usuario que motiva el trabajo: **"gerente de proyectos, remoto, sin inglés,
publicadas ayer–hoy"**.

**No-objetivos.** No se añade un conector-navegador (D18). No se añade estado
`PARCIAL` al contrato: la cobertura parcial se declara en `detalle` (D17). El filtro
"sin inglés" no vive en los conectores (D20).

## 2. Decisiones del dueño (Juan) — ya tomadas

- **Recencia = `Criterios.dias` (int, últimos N días).** "ayer y hoy" → `dias=2`.
  Default `None` = sin filtro (backward-compatible).
- **Cobertura completa por paginación:** recorrer **todas** las páginas de la
  consulta (no best-effort de página 1). Alcanzable con `curl_cffi` en los tres
  portales HTTP (paginación por URL verificada, §6).
- **Fecha best-effort:** parsear texto relativo / ISO a fecha aprox; no fechable →
  **incluir marcada "fecha desconocida"** (nunca esconder). Coherente con D2. Ver D19.
- **"Sin inglés"** se resuelve en la puntuación en contexto, con `excluir` como
  pre-filtro barato. Ver D20.
- **Indeed incluido** vía parámetros nativos de JobSpy (`is_remote`, `hours_old`),
  pero sujeto al **mismo** filtro de recencia central (D22/D21).
- **Cobertura parcial = prosa en `detalle`** (no estado dado). La revisión adversarial
  recomendó un flag estructurado `cobertura_completa`; queda como deuda §9, no se
  implementa ahora por decisión del dueño.

## 3. Cambios de modelo (`modelos.py`)

- `Criterios.dias: int | None = None` — ventana de recencia en días.
- `Criterios.modalidad: Modalidad | None` **ya existe**; Plan C la **cablea** a la
  URL de cada conector HTTP (hoy se ignora).
- `Vacante.fecha_publicacion: str | None` **ya existe**; Plan C la **puebla** con
  fecha ISO (`YYYY-MM-DD`) cuando es fechable, o `None` cuando no lo es (marcada
  "fecha desconocida" en el reporte). Ver D19.
- **Fecha de referencia (`hoy`):** el filtro de recencia y el parser NO leen reloj;
  `hoy` se inyecta desde el core (D22 fija el seam). No se añade `hoy` a `Criterios`
  ni al contrato del conector — el conector queda agnóstico de fecha para filtrar.
- **Sin columnas nuevas en el store** (verificado: `store.persistir` guarda el
  `Vacante` completo como `model_dump_json()`, así que `fecha_publicacion` viaja sin
  columna nueva; el dedup por `fingerprint_contenido` = empresa+título+ubicación no
  incluye fecha, sin interacción mala).

## 4. Parseo de fecha (`normalizar.py`)

Nueva `parsear_fecha_relativa(texto: str, hoy: date) -> date | None`:

- "Hoy" / "Hace N hora(s)/minuto(s)" → `hoy`.
- "Ayer" → `hoy - 1d`.
- "Hace N día(s)" → `hoy - N`; "Hace N semana(s)" → `hoy - 7N`;
  "Hace N mes(es)" → `hoy - 30N` (aprox, best-effort).
- Otra cosa / vacío → `None` (no fechable).

`hoy` se inyecta (parámetro), no se lee reloj — tests deterministas. Magneto NO usa
esta función: trae `publishDate` ISO en el flight, se parsea directo a `date`.

## 5. Paginación y filtro de recencia

### 5.1 Separación de responsabilidades (resuelve B1/S2)

- **El conector NO filtra por fecha.** Parsea la fecha por oferta, **puebla**
  `fecha_publicacion`, y filtra **modalidad** donde toca localmente (Magneto:
  `isRemote`). No descarta por recencia.
- **La parada de paginación es por conteo de tarjetas CRUDAS de la página**, no por
  `len(vacantes)` tras filtrar. Por eso `extraer` cambia su contrato:
  `extraer(html, criterios) -> (vacantes, omitidas, n_crudo)`, donde `n_crudo` =
  tarjetas de oferta vistas en el HTML **antes** de filtrar remoto. `ejecutar` para
  cuando `n_crudo == 0`. (Sin esto, en Magneto una página intermedia toda-no-remota
  daría `vacantes=[]` y pararía en falso, perdiendo páginas siguientes con remotas.)
- **El filtro de recencia se centraliza** en el core (D22), con `hoy` inyectado,
  aplicado a las candidatas consolidadas de TODOS los portales (incl. Indeed) →
  semántica de `dias` **uniforme**. Predicado exacto (corrige el off-by-one):
  conservar la oferta datable si `(hoy - fecha).days < dias` (así `dias=2` = {hoy,
  ayer}, no anteayer); conservar toda oferta no-fechable (D19). `dias=None` = sin
  filtro.

### 5.2 Filtro server-side = solo reductor de volumen

Donde el portal ofrece filtro de fecha nativo se usa para **traer menos**, pero la
semántica exacta la da el filtro local central (5.1). Ningún portal define la ventana
final; solo la recorta antes.

| Portal | Remoto (server) | Fecha (server, reductor) | Paginación (verificada) |
|---|---|---|---|
| Computrabajo | ruta `-en-remoto` | `?pubdate={menor∈{1,3,7,15} ≥ dias}` + `?by=publicationtime` | `?p=N` |
| elempleo | ruta `-modalidad-remoto` | `?PublishDate=hoy` (solo `dias≤2` confirmado) | ruta `/{N}` |
| Magneto | local `isRemote` | — (sin filtro server) | ruta `/pagina-N` |
| Indeed | JobSpy `is_remote` | JobSpy `hours_old≈24·dias` (rodante) | interna a JobSpy |

### 5.3 Bucle de paginación (`ejecutar`, conectores HTTP)

`ejecutar` itera `_url(criterios, pagina)` desde `pagina=1`, acumulando vacantes,
hasta la **primera** de estas condiciones:

1. **Página vacía** (`n_crudo == 0`) → **fin normal, cobertura completa** → `OK`.
2. **Error HTTP en `pagina > 1`** (p. ej. elempleo devuelve 500 más allá de la
   última) → fin de páginas → `OK` con las páginas ya cosechadas + `detalle`
   ("fin en página K: HTTP 500"). En `pagina == 1` un error es `ERROR` (fail-loud).
3. **Tope de seguridad** (`MAX_PAGINAS`, p. ej. 50) → **cobertura NO exhaustiva** →
   `OK` **marcado en `detalle`** ("tope de N páginas alcanzado; cobertura parcial")
   — distinto de la condición 1. (B2: agotar el tope NO se disfraza de "agotado".)
4. **Throttle/error a media** → `OK` con lo cosechado + `detalle` de corte.

Guardas: pausa breve entre páginas (throttling verificado en Magneto). Indeed **no**
usa este bucle (JobSpy pagina/filtra internamente; su conector es categoría aparte,
D4/D21).

## 6. Por portal (URLs, selectores, paginación — verificados)

- **Computrabajo:** lista `/trabajo-de-{slug}-en-remoto?pubdate={N}&by=publicationtime`;
  paginación `&p={pagina}`; fin más-allá-de-última = 200 con 0 `article.box_offer`.
  Fecha por oferta en `p.fs13.fc_aux` (texto relativo).
- **elempleo:** `/co/ofertas-empleo/trabajo-{slug}-modalidad-remoto?PublishDate=hoy`;
  paginación sufijo de ruta `/{pagina}`; fin = 200 con 0 tarjetas **o** HTTP 500.
  Fecha por oferta en `span.info-publish-date` (texto relativo). El JSON-LD `ItemList`
  **no trae `datePosted`** → la fecha se lee del DOM del card y se asocia por id.
- **Magneto:** `/co/trabajos/buscar/{slug}/pagina-{pagina}`; datos del flight RSC
  (`self.__next_f`): `title, company, city, salary, url, id, isRemote, publishDate`
  (ISO). Filtro remoto (`isRemote:true`) local; fecha ISO poblada, filtro central.
  `n_crudo` = tarjetas del flight antes de filtrar remoto.
- **Indeed:** JobSpy con `is_remote=True` y `hours_old=24·dias`; parsea `date_posted`
  a `fecha_publicacion`; el filtro de recencia central lo recorta igual que a los otros.

## 7. "Sin inglés" (fuera del conector, D20)

Ningún portal filtra por idioma. Se resuelve en la puntuación en contexto: Claude lee
`descripcion_raw` y descarta / baja puntaje a las ofertas en inglés o que lo exijan.
`Criterios.excluir` actúa como pre-filtro barato (títulos con tokens vetados). Sin
cambios de conector.

## 8. Altitud arquitectónica (D16–D22)

Formato §5d: (a) mínimo esfuerzo, (b) correcta, (c) elegida + por qué, (d) deuda +
"¿qué se rompe a 10× / en producción?".

**D16 — Recencia: server-side como reductor + filtro local exacto y central.**
- Flujo: `Criterios.dias` → `_url` añade param de fecha server donde exista (reduce
  volumen) → el conector puebla `fecha_publicacion` sin filtrar → el core aplica el
  recorte exacto uniforme (D22).
- (a) Fácil: filtrar solo con el param server de cada portal. Da ventanas distintas
  por portal (`pubdate∈{1,3,7,15}` vs `PublishDate=hoy` vs nada) → semántica
  inconsistente de `dias`.
- (b) Correcta: server como reductor + un filtro local **único** que define la
  ventana igual para todos.
- (c) **Elegida: dos niveles con la semántica en el local central.** El único punto
  donde `dias` significa algo es el filtro central → uniforme por construcción.
- (d) elempleo solo confirma token para `dias≤2`; ventanas mayores → sin filtro
  server + local (deuda §9). **A 10×:** sin reductor server el recorrido crece; el
  tope de páginas (§5.3) y el fail-loud acotan y declaran.

**D17 — Paginación en el contrato + cobertura parcial declarada.**
- Flujo: `ejecutar` itera `_url(criterios, pagina)` hasta parada (§5.3); corte/tope
  → `OK` + `detalle` de cobertura parcial; `report` propaga `detalle` (§6.2 skill).
- (a) Fácil: página 1 y `OK` como completo — el truncamiento silencioso que D2(d)
  veta.
- (b) Correcta: recorrer todo; corte/tope **declarado**, no oculto.
- (c) **Elegida: paginar + declarar.** Las **tres** condiciones de parada no-normales
  (error>p1, tope, corte) marcan `detalle`; solo la página vacía (n_crudo=0) emite
  `OK`-completo.
- (d) Cobertura parcial es prosa, no garantía testeable (dissenso de la revisión:
  §9). **A 10×:** el tope evita el cuelgue; el costo crece lineal con páginas —
  aceptable para uso personal de bajo volumen (design.md §1).

**D18 — Magneto: paginar por ruta de término, no conector-navegador.**
- Flujo: `/buscar/{slug}/pagina-N` con `curl_cffi` → parsear flight RSC → filtrar
  `isRemote` local, poblar fecha ISO → parar en n_crudo=0.
- (a) Vetada (D5/gate-opciones E): fallback headless oculto en `magneto.py`.
- (b) Correcta candidata: conector-navegador de primera clase (D5) si la paginación
  exigiera JS.
- (c) **Elegida: `curl_cffi` + `/pagina-N`.** Raw_signal probó que la ruta de término
  **sí** pagina por URL (páginas distintas, `publishDate` ISO en el flight). El
  navegador resultó **innecesario** → se descarta por costo/fragilidad (D5c).
- (d) La ruta *remoto-sola* `/remoto/pagina-N` NO pagina; por eso se pagina por
  término y se filtra remoto local. Páginas no ordenadas por fecha → se recorren
  todas. **A 10×:** throttling verificado → pausa + tope + fail-loud. Si Magneto
  rompe `/pagina-N`, revive el plan B (conector-navegador, D5).

**D19 — Fecha no-fechable: incluir marcada, no esconder.**
- Flujo: el conector puebla `fecha_publicacion=None`; el filtro central **no** la
  descarta; el reporte la marca "fecha desconocida".
- (a) Fácil: descartar lo no-fechable. Esconde ofertas por una limitación de parsing.
- (b) Correcta: incluir + marcar. La incertidumbre es del sistema, no de la oferta.
- (c) **Elegida: incluir + marcar.** Decisión del dueño; coherente con fail-loud.
- (d) Ninguna. **A 10×** (muchas no-fechables por selector roto): el reporte se llena
  de "fecha desconocida" — señal visible de rotura, no degradación silenciosa.

**D20 — "Sin inglés" fuera del conector.**
- Flujo: conector no filtra idioma → `excluir` pre-filtra títulos → Claude puntúa
  leyendo `descripcion_raw` y descarta/baja las en inglés.
- (a) Fácil-equivocada: heurística de idioma en el conector, duplicada ×4, sin
  contexto semántico.
- (b) Correcta: juicio de idioma en la etapa que ya lee la descripción con contexto.
- (c) **Elegida: en la puntuación.** No ensucia el contrato de conector.
- (d) Ninguna nueva. **A 10×:** el costo recae en la puntuación (acotada por el tope
  D6/D15).

**D21 — Indeed: parámetros nativos de JobSpy + filtro central uniforme.**
- Flujo: el conector Indeed pasa `is_remote=True`, `hours_old=24·dias` a JobSpy
  (reductor); parsea `date_posted` → `fecha_publicacion`; el filtro central lo recorta
  igual que a los otros.
- (a) Fácil-equivocada: confiar solo en `hours_old` (ventana **rodante** desde la
  corrida ≠ días de calendario) → Indeed usaría otra semántica de recencia.
- (b) Correcta: `hours_old` como reductor + el **mismo** filtro central de calendario.
- (c) **Elegida: reductor + filtro central.** Uniformidad con D16; `is_remote`/
  `hours_old` verificados en la JobSpy instalada (raw_signal).
- (d) `hours_old` sobre-trae un poco (rodante) y el central recorta. **A 10×:**
  irrelevante; JobSpy pagina/filtra internamente.

**D22 — Dónde vive el filtro de recencia (el seam de `hoy`).**
- Flujo: los conectores pueblan `fecha_publicacion` sin filtrar → `cosechar` (core,
  que ya recibe `fecha` de la corrida) aplica el recorte con `hoy = fecha` sobre las
  candidatas consolidadas, ANTES del dedup/puntuación.
- (a) Fácil-equivocada: filtrar recencia dentro de cada `_extraer`. Duplica el filtro
  ×3–4, necesita colar `hoy` al conector (rompe el contrato agnóstico de fecha), y
  **reintroduce B1** (mezcla filtro de fecha con la parada de paginación).
- (b) Correcta: un único filtro en el core, con `hoy` inyectado desde `fecha`.
- (c) **Elegida: central en `cosechar`.** Un solo dueño de la semántica de `dias`
  (uniforme, D16); conectores agnósticos de fecha (parada por n_crudo, D17); tests
  deterministas por inyección de `hoy`.
- (d) Recorta antes del dedup para no gastar dedup/puntuación en viejas. **A 10×:**
  el filtro es O(candidatas) en memoria, trivial frente al costo de red/LLM.

## 9. Backlog / deudas (documentadas, no bloquean)

- **elempleo tokens de fecha `>2 días`:** solo `PublishDate=hoy` (=`dias≤2`)
  confirmado; `semana`/etc. NO son tokens válidos (probado). Ventanas mayores →
  recorrer sin filtro server + local. Deuda: capturar el mapeo value→token real.
- **Computrabajo granularidad:** `pubdate∈{1,3,7,15}` no cubre todo `dias` exacto
  server-side; se sobre-trae al menor ≥ `dias` y recorta local (correcto, menos
  eficiente).
- **Cobertura como garantía testeable (dissenso de la revisión adversarial):** la
  revisión recomendó `ResultadoConector.cobertura_completa: bool` (o
  `motivo_parada`) en vez de prosa en `detalle`, porque la completitud de recencia es
  la promesa central del producto. El dueño eligió prosa por ahora. Disparador para
  promover: si el consumo exige auditar cobertura programáticamente.
- **Volumen vs ToS/bloqueo:** paginar cada consulta hasta agotarla sube el volumen de
  requests frente a "uso personal de bajo volumen" (design.md §10), con throttling ya
  visto en Magneto. Mitigado con pausa + tope; trade-off completitud↔bloqueo asumido
  por decisión del dueño.
- **Selectores frágiles:** `fc_aux`, `info-publish-date`, shape del flight de Magneto
  pueden cambiar con un rediseño; el fail-loud + "fecha desconocida" (D19) los vuelve
  visibles.
- **Magneto meses aprox:** "Hace N meses" = 30·N; irrelevante para recencia corta.
