# Fase 0 — Descubrimiento de endpoints

Este documento mapea, por portal, cómo se obtienen los listados de búsqueda: la
URL, el tipo de página (SSR vs SPA vs API), la forma de la respuesta y las
señales necesarias para construir cada conector. Es el insumo del plan de
conectores colombianos.

**Estado:** sondeo ejecutado con `discovery/probe.py` (curl_cffi `chrome124`) el
2026-07-23 con el término "gerente de proyectos". Los tres portales
respondieron **HTTP 200 sin bloqueo** — incluido Computrabajo, que con TLS de
grado navegador **pasa Cloudflare**. Los datos de abajo son reales. Falta
únicamente fijar los selectores exactos de empresa/salario/ubicación, que se
harán al escribir cada conector con TDD contra el HTML capturado.

---

## Resumen

| Portal | URL de búsqueda | HTTP | Cloudflare | Fuente del listado | Id nativo |
|---|---|---|---|---|---|
| Computrabajo | `https://co.computrabajo.com/trabajo-de-{slug}` | 200 | pasa con curl_cffi | DOM: `article.box_offer` | `data-id` (hash hex) |
| elempleo | `https://www.elempleo.com/co/ofertas-empleo/trabajo-{slug}` | 200 | n/a | JSON-LD `ItemList` + DOM | dígitos finales de la URL / `data-id` |
| Magneto | `https://www.magneto365.com/co/trabajos/buscar?search={q}` | 200 | n/a | JSON-LD `ItemList` + DOM | dígitos finales de `/co/empleos/…-{id}` |

`{slug}` = término en minúsculas con guiones ("gerente de proyectos" →
`gerente-de-proyectos`). Ninguno expone `JobPosting` JSON-LD en la página de
resultados (suele estar solo en el detalle), así que los tres parsean el DOM;
elempleo y Magneto además traen un `ItemList` con título + URL de detalle.

---

## Computrabajo

- **Confirmado:** `curl_cffi` con `impersonate="chrome124"` devuelve **200** (313 KB),
  sin challenge de Cloudflare. La premisa del diseño se sostiene: sin fingerprint
  de navegador el mismo request queda vacío (WebFetch lo comprobó).
- **Listado:** cada oferta es un `<article class="box_offer" id="{HASH}" data-id="{HASH}">`.
  - **id nativo** = atributo `data-id` (hash hex de 32, p. ej. `067CFDC9FD215E0B61373E686DCF3405`).
    Estable y presente también al final de la URL de detalle.
  - **título** = `article > h2 > a.js-o-link` (texto); **url** = su `href`
    (`/ofertas-de-trabajo/oferta-de-trabajo-de-…-{HASH}`).
  - empresa / ubicación / salario: en los `<p>`/`<span>` siguientes dentro del
    `article` (selectores exactos a fijar en el conector con el HTML capturado).
- **JSON-LD:** un único bloque con `@graph` (Organization + WebPage + ItemList de
  14 ListItem); no aporta más que las URLs — el DOM es la fuente primaria.
- **Riesgo D5:** si en el futuro aparece Turnstile, este conector se promueve a
  conector-navegador (nodriver/Camoufox) — decisión explícita, no fallback oculto.

## elempleo

- **Confirmado:** **SSR**, 200 (684 KB). La URL `…/trabajo-{slug}` responde directo.
- **Listado (doble fuente):**
  - **JSON-LD `ItemList`** (20 items): cada `ListItem.item` trae `@id` = URL de
    detalle y `name` = título. Ej: `@id` =
    `https://www.elempleo.com/co/ofertas-trabajo/gerente-de-proyectos-1886730317`,
    `name` = "Gerente de proyectos".
  - **DOM**: tarjetas con `data-id="1886730317"` (mismo id).
  - **id nativo** = dígitos finales de la URL de detalle (= `data-id`).
- **Estrategia de conector:** iterar el `ItemList` para título + url + id; parsear
  el card correspondiente en el DOM para empresa / salario / ubicación.

## Magneto

- **Confirmado:** **SSR**, 200 (891 KB). El parámetro `?search={q}` responde 200
  (confirmar que efectivamente filtra por término al escribir el conector).
- **Listado (doble fuente):**
  - **JSON-LD `ItemList`** (20 items): cada `ListItem.url` = URL de detalle. Ej:
    `https://www.magneto365.com/co/empleos/gestor-de-servicio-en-sitio-1004184`.
  - **id nativo** = dígitos finales de esa URL (`1004184`). El detalle vive en
    `/co/empleos/{slug}-{id}` (no `/co/trabajos/…`).
  - título / empresa / salario / ubicación: del card en el DOM (o del slug para el
    título) — selectores a fijar en el conector.
- **Detalle `/co/empleos/{slug}-{id}` (investigado 2026-07-24):** 200, 846 KB, SSR.
  - ⚠️ **Corrección.** Un primer barrido estático (documento + flight, sin abrir los
    bundles) concluyó "cero rutas `/api/`". **Es falso.** Con DevTools contra el
    runtime aparecen llamadas a **`api.magneto365.com`**; la URL base se arma en los
    chunks `_next/static/chunks/*.js`, que el barrido no leyó. Lección de método: un
    escaneo estático que no incluye los bundles no puede afirmar ausencia de API.
  - **Ninguna de esas llamadas trae datos de vacantes.** Verificado en la página de
    detalle y en la de resultados: son `sign-up/v1/countries/active`,
    `jobs/v1/public/locations`, `seo/v1/mega-menu/*`,
    `sign-up/v2/candidate/applications/count` (401) y
    `jobs/v1/vacancies/ia/suggested?id={id}` (401). Las vacantes siguen llegando con
    el documento SSR.
  - **Almacenamiento local:** `localStorage`, `sessionStorage`, cookies e IndexedDB
    contienen **solo tracking** (Amplitude, Clarity, Snapchat, TikTok, Pinterest,
    Google, Meta). IndexedDB: únicamente `AMP_diagnostics`. **Cero datos de vacantes
    cacheados** — no hay nada que aprovechar desde ahí.
  - **La descripción vive en `<script type="application/ld+json">` con
    `@type: "JobPosting"`** (schema.org). La página trae 3 bloques ld+json —
    `JobPosting`, `BreadcrumbList` y `LocalBusiness`— así que hay que filtrar por
    `@type`. Campos útiles: `description` (~3,2 K caracteres, HTML plano),
    `datePosted`, `baseSalary`, `employmentType`, `hiringOrganization`,
    `jobLocation`, `industry`, `qualifications`, `validThrough`.
  - **Contraste con el listado:** el listado obliga a reconstruir el flight RSC
    (`self.__next_f.push`); el detalle **no** — el JSON-LD está en el DOM directamente.
    Por eso `extraer_detalle` no comparte código con `_rows_del_flight`.
  - ⚠️ `baseSalary.value.unitText` viene como `"HOUR"` con `minValue: 10600000`, que es
    un salario **mensual** en COP. El dato del portal es incorrecto; no confiar en
    `unitText`.

### Servidor MCP oficial de Magneto (hallazgo del 2026-07-24)

`https://api.magneto365.com/agents/v1/mcp` — **"Magneto MCP Server" v1.1.2**, JSON-RPC
2.0, `initialize` responde **sin autenticación** y sin `Mcp-Session-Id`. Es la interfaz
que el propio portal expone para agentes.

| Tool | Params | Comportamiento observado |
|---|---|---|
| `get_job_detail` | `jobSlug` | **0,2 s / 4,3 KB** (vs 846 KB y timeouts de 30 s vía HTML). Devuelve `structuredContent.job` con `id`, `slug`, `title`, `company`, `location`, `salary`, `description`, **`modality`**, `sectors`, `experienceMonthsNumber`, `educationLevel`, `publicationDate`, `contractType`, `url`. |
| `ai_search_jobs` | `query` (lenguaje natural) | 1,9 s. Devuelve `{results, total, searchUrl}` con los mismos campos por vacante. |
| `get_filters` | — | Catálogo de filtros (ubicaciones, categorías, modalidades, experiencia, salario, contrato). |

**`ai_search_jobs` — caracterizado con 3 consultas + prueba de repetición:**

- ✅ **Determinista.** Dos llamadas idénticas devuelven los mismos ids, en el mismo orden.
- ✅ **Respeta la modalidad** expresada en lenguaje natural ("presencial" → todo Presencial).
- ❌ **Ignora la recencia.** Las consultas *con* y *sin* "publicado en los últimos 2 días"
  devolvieron **resultados idénticos**, incluyendo una vacante de abril. Comprobado por
  comparación directa, no inferido.
- ❌ **Trunca en silencio.** Reporta `total=23` y devuelve 10; `total=4` y devuelve 2.
  Para un cosechador esto es descalificante: perdería vacantes sin declararlo, que es
  justo lo que prohíbe el principio fail-loud (D4/B2).
- Su `searchUrl` lleva `utm_source=openai&utm_medium=mcp`: el servidor está pensado
  para agentes tipo OpenAI.

**`get_filters` — vocabulario canónico del portal** (útil como referencia, no como
dependencia en runtime):

- `modalities`: `remote` / `hybrid` / `onSite` — mapea 1:1 con `Modalidad`.
- `publishDate`: **ventanas discretas** `Hoy` / `Últimos 3 días` / `Última semana` /
  `Últimos 15 días` / `Último mes` (`BK-01`…`BK-05`). **No existe "2 días"**: mismo
  patrón que el `pubdate=[1,3,7,15]` de Computrabajo, así que `dias=2` cae en `BK-02`
  y el recorte fino lo hace `filtro_recencia` (D22). Confirma el diseño actual.
- `categories` (34): id **23** = "Software, informática y telecomunicaciones",
  **28** = "Dirección y Gerencia", **14** = "Ingenierías".
- `experienceMonths` (`BK-01`…`BK-08`), `salaryRanges` (`BK-01`…`BK-08`),
  `contractTypes` (1–6, 153; **5** = "Prestación de servicios").

**Protocolo, medido:** `tools/call` responde **sin `initialize` previo** y sin
`Mcp-Session-Id` — un único POST JSON-RPC basta. 5 llamadas seguidas: 0,19–0,22 s,
todas 200. No hace falta cliente MCP ni dependencia nueva: `curl_cffi` ya está.

**Veredicto:** adoptar `get_job_detail`; **no** adoptar `ai_search_jobs` como fuente del
listado. El listado debe seguir saliendo del flight RSC, que sí controlamos.

**Decisión sobre términos de uso (aprobada por el responsable del repo, 2026-07-24):**
se adopta `get_job_detail`. Razones registradas: el endpoint es **público y sin
autenticación**, el portal lo publica **explícitamente para agentes** (su propio
`searchUrl` devuelve `utm_source=openai&utm_medium=mcp`), y usarlo **reduce** la carga
sobre Magneto en vez de aumentarla — 4 KB por oferta frente a 846 KB de la página SSR.
Es la opción más respetuosa disponible, no un atajo. Se mantiene el extractor JSON-LD
como respaldo, de modo que jobwatch no queda cautivo del servicio.

### Fiabilidad del listado de Magneto (medido 2026-07-24)

Causa raíz del `error`/`cobertura parcial` que aparece en casi toda corrida:

- **Latencia de cola errática, en cualquier página. No hay muro por profundidad.**
  Una primera medición con el término `gerente-de-proyectos` sugería un muro fijo en la
  página 4 (p1-p3 en <2 s, p4-p6 en timeout de 45 s, reproducible incluso como primera
  petición de una sesión nueva). **Contrastado con más términos, la hipótesis cae:**

  | término | p1 | p3 | p4 |
  |---|---|---|---|
  | `desarrollador` | 1,2 s | 19,8 s | **1,5 s** |
  | `contador` | 1,0 s | **timeout** | 3,8 s |
  | `inteligencia-artificial` | 0,8 s | **timeout** | **timeout** |

  Cualquier página puede tardar >35 s, y la misma página puede responder rápido al
  reintentarla. **Un tope fijo de páginas no arregla nada**; lo que corresponde es
  reintentar.
- **Consecuencia grave del fallo en la página 1.** Un error en la primera página tumba
  el conector entero (`ERROR`, por diseño en `ejecutar`). Así se perdió la única vacante
  real de la búsqueda `ingeniero-inteligencia-artificial`, cuyo p1 responde en 0,8 s al
  reintentarlo.
- **Los filtros por query string se ignoran.** `?modality=remote`, `?modalities=`,
  `?workModality=`, `?publishDate=BK-02` y su combinación devuelven byte por byte lo
  mismo que sin filtro (836 KB, 20 filas, 13 remotas). **No hay filtrado en servidor**:
  el filtro remoto local del conector es correcto e inevitable.

---

## Herramientas de Fase 0 — instalación real (verificado 2026-07-24)

El README las nombra como si las tres se instalaran igual. **No es así.**

```bash
# mitmproxy2swagger — extra del propio proyecto
pip install -e ".[discovery]"          # trae mitmproxy 12.2.3 + mitmproxy2swagger 0.15.0
                                       # ⚠️ fija pydantic 2.11.10; correr la suite después

# curlconverter — npm, trivial
npm i -g curlconverter                 # 4.12.0

# jsluice — NO tiene binarios precompilados (cero releases, cero tags en GitHub);
# hay que compilarlo, y necesita Go, que no viene con WSL.
curl -sL -o /tmp/go.tgz "https://go.dev/dl/$(curl -s https://go.dev/VERSION?m=text | head -1).linux-amd64.tar.gz"
tar -C ~/.local -xzf /tmp/go.tgz       # sin sudo: queda en ~/.local/go
PATH="$HOME/.local/go/bin:$PATH" go install github.com/BishopFox/jsluice/cmd/jsluice@latest
~/go/bin/jsluice urls chunks/*.js      # el binario queda en ~/go/bin
```

**Qué aporta cada una, medido y no supuesto:**

- **`jsluice urls`** sobre los 45 chunks de magneto: 520 URLs, y para la API los
  **mismos namespaces** que un barrido a mano (`jobs`, `sign-up`, `seo`, `referrals`,
  `growth`, `notification-manager`, `oauth2`). No sacó rutas más específicas porque se
  construyen en runtime. Su valor real: **lee los bundles por defecto**, que es
  exactamente el paso omitido que produjo la conclusión falsa de "cero rutas `/api/`".
- **`curlconverter`** traduce `curl` a Python/otros lenguajes. No descubre nada; sirve
  para pasar una petición capturada en DevTools a código del conector sin transcribir
  headers a mano.
- **`mitmproxy2swagger`** necesita un `.har` o un dump de flujos. Para magneto **no
  aplica**: no hay API de vacantes que documentar. Su sitio es Computrabajo bajo
  Turnstile, donde `curl_cffi` no basta.

---

## Cómo re-capturar (runbook local)

1. Instala el proyecto con sus dependencias: `pip install -e .` (trae `curl_cffi`
   y `extruct`).
2. Corre el sondeo por portal, que guarda el HTML crudo y reporta status,
   bloqueo Cloudflare y JSON-LD:

   ```bash
   python -m discovery.probe computrabajo "gerente de proyectos"
   python -m discovery.probe elempleo "gerente de proyectos"
   python -m discovery.probe magneto "gerente de proyectos"
   ```

   El HTML crudo queda en `discovery/captures/{portal}.html` (git-ignored).

3. Abre el HTML capturado e identifica, por portal: el selector del contenedor de
   cada oferta, y dentro de él los selectores/atributos de `titulo`, `empresa`,
   `ubicacion`, `salario`, `url` de detalle y **el id nativo estable**. Anótalos
   en la sección del portal de arriba.

4. Si un portal requiere DevTools (p. ej. Computrabajo bajo Turnstile), captura
   un **HAR** desde el navegador y pásalo por `mitmproxy2swagger` para extraer la
   estructura; documenta ahí la ruta y los headers necesarios.

5. Con los selectores confirmados, se escribe el plan de conectores (uno por
   portal), cada uno cumpliendo el contrato `buscar(criterios) -> ResultadoConector`.
