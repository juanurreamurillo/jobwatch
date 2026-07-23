# Fase 0 — Descubrimiento de endpoints

Este documento mapea, por portal, cómo se obtienen los listados de búsqueda: la
URL, el tipo de página (SSR vs SPA vs API), la forma de la respuesta y las
señales necesarias para construir cada conector. Es el insumo del plan de
conectores colombianos.

**Estado:** reconocimiento inicial hecho de forma remota (fetch + búsqueda). La
captura fina (selectores exactos, id nativo, paginación) se completa corriendo
`discovery/probe.py` **localmente**, porque solo desde tu máquina se alcanzan
los portales con TLS de grado navegador y, si hiciera falta, tu sesión.

---

## Resumen

| Portal | URL de búsqueda (patrón) | Tipo | JSON-LD | Mecanismo del conector |
|---|---|---|---|---|
| Computrabajo | `https://co.computrabajo.com/trabajo-de-{slug}` | SSR tras **Cloudflare** | Por confirmar (local) | `curl_cffi` + parsing HTML |
| elempleo | `https://www.elempleo.com/co/ofertas-empleo/trabajo-{slug}` | **SSR** | No detectado | `curl_cffi` + parsing HTML |
| Magneto | `https://www.magneto365.com/co/trabajos/buscar` (param por confirmar) | **SSR** | No detectado | `curl_cffi` + parsing HTML |

`{slug}` = término de búsqueda en minúsculas con guiones (p. ej. "gerente de
proyectos" → `gerente-de-proyectos`).

---

## Computrabajo

- **Observado (remoto):** una petición sin fingerprint de navegador (WebFetch)
  devolvió **contenido vacío** — consistente con un challenge/403 de Cloudflare.
  Esto **confirma** la premisa del diseño: hace falta `curl_cffi` con
  `impersonate` de un Chrome reciente para pasar el check pasivo de TLS.
- **Pendiente (local):** confirmar que `curl_cffi` devuelve 200 con el HTML de
  resultados; verificar si el HTML incrusta `<script type="application/ld+json">`
  con `@type: JobPosting` (si sí, `extruct` lo extrae casi todo: título,
  empresa, salario, ubicación, fecha); identificar el **id nativo** de cada
  oferta (en la URL del detalle o en un atributo `data-*`); mapear la paginación.
- **Riesgo:** si aparece un challenge JS (Turnstile) que `curl_cffi` no resuelve,
  este conector se promueve a conector-navegador (nodriver/Camoufox) — decisión
  explícita D5, no un fallback oculto.

## elempleo

- **Observado (remoto):** **SSR**. El HTML del servidor ya trae los listados
  (título + empresa visibles; ~18 tarjetas en la primera página). **No** se
  detectó bloque JSON-LD. La URL `…/trabajo-{slug}` responde directo.
- **Implicación de diseño:** el conector parsea el HTML (no hay API JSON interna
  que reversar, al contrario de lo que suponía el diseño original). El id nativo
  probablemente vive en la URL del detalle (p. ej. `…/ofertas-trabajo/{slug}/{id}`).
- **Pendiente (local):** fijar los selectores CSS del contenedor de oferta y de
  cada campo; extraer el id nativo de la URL de detalle; confirmar paginación.

## Magneto

- **Observado (remoto):** **SSR**. `…/co/trabajos/buscar` trae los listados en el
  HTML (título, empresa, salario, ubicación; ~20 tarjetas). **No** se detectó
  JSON-LD.
- **Pendiente (local):** confirmar el **parámetro de búsqueda por término** (la
  página `/buscar` sin parámetro ya lista; falta el `?...=` o la ruta que filtra
  por palabra clave); fijar selectores; extraer id nativo; paginación.

---

## Cómo completar la captura (runbook local)

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
