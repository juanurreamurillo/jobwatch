# Plan C — Filtros server-side de modalidad y fecha — Nota de descubrimiento

**Estado:** descubrimiento en curso (pre-brainstorm cerrado). Retomar aquí tras
reiniciar Claude Code (se instaló el MCP chrome-devtools; ver §Tooling).

## Objetivo
Los conectores colombianos hoy solo buscan por keyword: **no** fijan `modalidad`,
**no** construyen URL filtrada por remoto, **no** extraen fecha de publicación. Juan
quiere buscar: **modalidad remoto + sin inglés + publicadas ayer–hoy**. Plan C
activa los filtros nativos de remoto y añade recencia.

## Decisiones tomadas (Juan)
- **Recencia = campo `Criterios.dias` (int, últimos N días).** "ayer y hoy" → `dias=2`.
  Reusable/configurable.
- **Fecha sin timestamp confiable → best-effort por portal:** estricto donde el
  portal fecha bien; parsear texto relativo ("Hoy"/"Ayer"/"Hace N días/horas") →
  fecha aprox; si una oferta no se puede fechar, **INCLUIRLA marcada "fecha
  desconocida"** (nunca esconder por no poder fecharla). Coherente con fail-loud D2.
- **"Sin inglés"**: ningún portal lo trae como filtro. Se resuelve en el paso de
  puntuación en contexto (yo leo `descripcion_raw` y descarto/bajo puntaje a las que
  estén en inglés o exijan inglés), con `excluir` como pre-filtro barato.

## Descubrimiento — cómo se activa cada filtro
**Modalidad remoto = SEGMENTO DE RUTA en los tres (confirmado):**
- Computrabajo: `https://co.computrabajo.com/empleos-en-remoto` (análogo a
  `empleos-en-{ciudad}`). Cómo combina con término: por confirmar con DevTools.
- elempleo: `…/co/ofertas-empleo/modalidad-remoto` y con término
  `…/co/ofertas-empleo/trabajo-{slug}-modalidad-remoto` (probado, 200 real).
- Magneto: `…/co/trabajos/buscar/remoto` (y `ofertas-empleo-trabajo-remoto`).

**Fecha = TEXTO RELATIVO por oferta (no ISO en 2 de 3):**
- elempleo: `<span class="js-offer-date …">Hace 1 semana…</span>` (relativo).
- Computrabajo: "Ayer" / "Hace X" (relativo, disperso — fijar selector real).
- Magneto: `publishDate` ISO **escapado** dentro del payload RSC de Next.js
  (`\"publishDate\":\"2026-07-23T23:27…\"`).
- **La API JSON de Magneto NO aparece en el HTML estático** (la SPA la inyecta desde
  el bundle JS). Hay que verla en DevTools → Network → Fetch/XHR.

## Lo que falta descubrir — CERRADO (2026-07-23, sesión 2, chrome-devtools)

Las tres preguntas quedaron resueltas con raw_signal directo (URLs reales
navegadas que devuelven listas filtradas + selectores/campos observados en vivo).

### Computrabajo — TODO server-side (mejor de lo esperado)
- **término + remoto = sufijo de ruta:** el checkbox remoto trae
  `data-sem="-en-remoto"` → `/trabajo-de-{slug}-en-remoto`.
- **fecha = query param nativo `?pubdate=N`** (valores discretos observados):
  `1`=Hoy · `3`=Últimos 3 días · `7`=Última semana · `15`=15 días · `99`=Urgente.
- **orden por fecha:** `?by=publicationtime`.
- **URL combinada verificada (200, 3 ofertas, todas ≤3 días):**
  `https://co.computrabajo.com/trabajo-de-gerente-de-proyectos-en-remoto?pubdate=3&by=publicationtime`
- **fecha por oferta (DOM):** `<p class="fs13 fc_aux">` texto relativo ("Hace 2 horas"/"Ayer").

### elempleo — TODO server-side (mejor de lo esperado; corrige el plan)
- **término + remoto = ruta:** `/co/ofertas-empleo/trabajo-{slug}-modalidad-remoto`
  (verificado 200, 233 ofertas).
- **fecha = query param nativo `?PublishDate=<token>`.** Confirmado
  `?PublishDate=hoy` = radio "Hoy y ayer" (value=1) → tras aplicar dejó solo
  ofertas "Hoy"/"Ayer" (= `dias=2`, target de Juan). Radios: 1=Hoy y ayer,
  2=1 semana, 3=2 semanas, 4=1 mes, 6=+1 mes. **Tokens de 2/3/4/6 SIN confirmar**
  (`semana` NO es válido: se ignoró y no filtró); el mapeo value→token vive en el
  bundle server/vendor. Solo `hoy` verificado — cubre el caso primario.
- **fecha por oferta (DOM):** `<span class="info-publish-date">` texto relativo.
  **CORRECCIÓN:** el plan suponía `js-offer-date`; el real es `info-publish-date`.
- El **JSON-LD `ItemList` NO trae `datePosted`** → la fecha sale del DOM, no del LD.

### Magneto — sin API JSON limpia; datos en el RSC del HTML estático
- **NO existe XHR/JSON de lista en cliente.** La lista se sirve en el payload RSC
  inline del documento: `<script>self.__next_f.push([1,"…"])</script>`. `curl_cffi`
  **sí** lo recibe (no requiere ejecutar JS). Campos limpios por vacante:
  `title, company, companyName, city, salary, url, slug, id, isRemote(bool),
  publishDate(ISO)`. Ej. real observado: `"publishDate":"2026-07-23T23:27:17.004Z"`.
- **Paginación por URL = esquema de RUTA `/pagina-N`** (verificado curl_cffi), **NO**
  `?paginator[page]=N` (ese es el `<a href>` del DOM pero se ignora en SSR: pág. 2/5
  devuelven la MISMA página 1, hash idéntico). Con `/pagina-N`:
  - **Ruta de término `/buscar/{termino}/pagina-N` SÍ pagina:** cada página trae 20
    vacantes DISTINTAS (p1 hash `2375ffcd`, p2 `71a8fa9b`, p3 `86b6b41e`), con
    publishDate ISO + isRemote. Ratio remoto por página variable (13/20, 5/20, 5/20).
  - **Ruta remoto-sola `/buscar/remoto/pagina-N` NO pagina** (pág. 2+ = 0 vacantes en
    SSR). Por eso el conector pagina por **término** y filtra remoto local.
  - **Las páginas NO están ordenadas por fecha global** (p3 más nueva que p2) → sin
    parada temprana por fecha; se recorre hasta **página vacía** y se filtra fecha local.
  - **Throttling real:** hammering rápido (~4 páginas seguidas) disparó timeout/HTTP.
    Recorrer muchas páginas tiene costo; ir con pausas; el fail-loud/`detalle` (D2/§6.2)
    cubre un recorrido cortado a media (cobertura parcial declarada, nunca silenciosa).
- La ruta combinada `/buscar/{termino}/remoto` **NO** SSR-ea la lista (solo ~2 tarjetas)
  → no usarla; usar la ruta de término + filtro remoto local.
- **Implicación de diseño (corregida):** Magneto sí alcanza cobertura completa con
  `curl_cffi` paginando `/buscar/{termino}/pagina-N` hasta página vacía y filtrando
  remoto (`isRemote`) + fecha (`publishDate` ISO) localmente. **NO** hace falta
  conector-navegador (Opción C descartada). Magneto no tiene filtro de fecha
  server-side; el filtro de fecha es local sobre el ISO del flight.

### Paginación por URL — esquema por portal (verificado curl_cffi, 2026-07-23)
Los tres paginan por URL con contenido DISTINTO por página, y pedir página >
última **no** repite la página 1 (condición de parada real, no cap):
- **Computrabajo:** query `?p=N` (el botón "Siguiente" trae `data-path=…?p=2`).
  p1≠p2 (hashes de hrefs distintos); **p200 → 200 con 0 `article.box_offer`**
  (página vacía limpia). Combina con los params de filtro (`?pubdate=&by=&p=`).
- **elempleo:** sufijo de ruta `/{N}` (`…-modalidad-remoto/2`). p1/p2/p3 distintas
  (20 ids c/u, hashes distintos); **p999 → HTTP 500** (no repite p1). El conector
  debe tratar 0-tarjetas O error-más-allá-de-última como fin de páginas.
- **Magneto:** sufijo de ruta `/pagina-N` en la **ruta de término** (no en remoto-
  sola). p1/p2/p3 distintas; NO ordenadas por fecha. Parada = página con 0 tarjetas.
- **OJO (parada correcta):** la señal de parada es **conteo de tarjetas CRUDAS** de
  la página, NO `len(vacantes)` tras filtrar remoto/fecha. En Magneto una página
  intermedia toda-no-remota da 0 vacantes filtradas pero SÍ tiene tarjetas crudas;
  parar ahí perdería páginas siguientes con ofertas remotas.

### Indeed / JobSpy (verificado, 2026-07-23)
`jobspy.scrape_jobs` acepta `is_remote` **y** `hours_old` (params confirmados en la
versión instalada). `hours_old` es ventana **rodante** (desde el instante de corrida),
no días de calendario → usarlo como reductor de volumen y afinar con filtro local.

### Implicación transversal para `Criterios.dias`
`dias` (int) → por portal se elige la ventana server-side más pequeña ≥ `dias` y se
afina con filtro local por fecha parseada:
- Computrabajo: `?pubdate` ∈ {1,3,7,15} (elegir el menor ≥ dias).
- elempleo: `?PublishDate=hoy` (=2 días) confirmado; demás ventanas por confirmar.
- Magneto: sin server-side → filtro local por `publishDate` ISO.
Fechas no fechables → INCLUIR marcadas "fecha desconocida" (decisión D2/fail-loud).

## Tooling (ya configurado)
- MCP `chrome-devtools` en user scope → `/home/jd_um/.claude/bin/cdp-win.sh`, que
  conduce el **Chrome de Windows real** por CDP vía relé `C:\cdp-relay\relay.js`
  (host Windows por `ip route`; relé 9223 → Chrome 9222). Pre-calentado y verificado
  (Chrome/150 responde). **Requiere reiniciar Claude Code** para que las tools carguen.

## Insumos listos
- **CV:** `cv-ats/cv-juan-urrea.html` (genera `CV-Juan-Urrea-Gerente-Proyectos-TI.pdf`);
  texto en `cv-ats/_extraido.txt`. Rol objetivo: **Gerente de Proyectos TI**.
- Capturas estáticas: `discovery/captures/{computrabajo,elempleo,magneto}.html`.

## Próximos pasos (secuencia)
1. ~~Reiniciar Claude Code → usar chrome-devtools para cerrar §"Lo que falta".~~
   **HECHO (2026-07-23, sesión 2).** Ver §"Lo que falta descubrir — CERRADO".
2. `superpowers:brainstorming` → presentar diseño Plan C (Criterios.dias + contrato
   de URL por conector + extracción de fecha) con los **gates** (gate-opciones,
   gate-altitud; gate-premisas ya alimentado con el raw_signal de arriba).
3. `writing-plans` → `subagent-driven-development` (TDD, como Plan A/B).

## Notas de estado del repo
- Plan A (motor multi-portal) y Plan B (CLI + skill) mergeados a `main` (PR #1, #2).
  93 tests verdes. `docs/HANDOFF.md` cubre A/B.
