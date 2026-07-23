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
