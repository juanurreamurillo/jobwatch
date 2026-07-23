# jobwatch — Diseño

**Estado:** Diseño aprobado, pendiente de plan de implementación.

## 1. Propósito

Herramienta de consola que agrega ofertas de empleo de varios portales, las
deduplica, puntúa cada una contra el CV del usuario y reporta **solo lo que es
nuevo** desde la última corrida. Corre programada (cron / Programador de
Tareas). Uso personal, de bajo volumen. No es un producto multiusuario.

**Objetivo:** agregación con match contra CV + monitoreo continuo con
deduplicación.

**No-objetivos (MVP):**
- No escribe en los portales (no postula, no marca favoritos). Solo lectura de
  lo que una búsqueda pública ya muestra.
- Sin sesión/autenticación (ver §4 y §5d, decisión D1).
- Sin generación masiva de cartas (ver §5d, D6).

## 2. Alcance de portales

| Portal | Tipo | Mecanismo | Sesión |
|---|---|---|---|
| Computrabajo | SSR tras Cloudflare | `curl_cffi` (TLS de grado navegador) + `extruct` sobre JSON-LD `JobPosting` | No (público) |
| elempleo | SPA, API JSON interna | `curl_cffi` contra endpoint interno (mapeado en Fase 0) | No (público) |
| Magneto | SPA, API JSON interna | `curl_cffi` contra endpoint interno (mapeado en Fase 0) | No (público) |
| Indeed | Librería de terceros | Envuelve `JobSpy`; categoría aparte (ver §5d, D4) | No (público) |

LinkedIn queda **fuera de alcance** en el MVP: sesión obligatoria y detección de
automatización agresiva hacen que el riesgo de bloqueo de cuenta sea
desproporcionado al valor.

## 3. Arquitectura

Pipeline de cuatro etapas. La normalización vive **dentro** de cada conector (no
hay etapa "normalizador" separada — ver §5d, D7).

```
[Conectores]           [Matcher híbrido]        [Store + Reporte]
 4 fuentes       ──►    filtro local → LLM  ──►   SQLite + .md
 cada uno emite        (solo puntúa, no            dedup de dos niveles
 list[Vacante]         redacta cartas)             reporte de solo nuevas
 pre-normalizado
```

**Una corrida (`jobwatch run`):**
1. Por cada conector: `buscar(criterios) -> ResultadoConector`.
2. Consolidar todos los registros `Vacante`.
3. Dedup contra el store (dos niveles, §6).
4. Matchear **solo las nuevas**: filtro local barato → LLM puntúa las
   sobrevivientes.
5. Persistir en SQLite.
6. Escribir `reportes/YYYY-MM-DD.md` con las nuevas puntuadas + estado por
   conector.

### 3.1 Contrato de conector

```python
def buscar(criterios: Criterios) -> ResultadoConector: ...
```

- `Criterios`: términos de búsqueda, ubicación, modalidad, etc. (mapeados al
  vocabulario de cada portal dentro del conector).
- `ResultadoConector`: `{ estado: OK | ERROR | SESION_EXPIRADA,
  vacantes: list[Vacante], detalle: str }`. El campo `estado` es lo que hace
  posible el fail-loud (§5d, D2): distinguir "0 resultados por búsqueda vacía"
  de "conector roto/bloqueado".

### 3.2 Modelo `Vacante` (Pydantic)

```
id_estable            # hash(portal + id nativo) — ver §6 y §5d, D3
id_nativo             # el id interno de la oferta en el portal
portal                # computrabajo | elempleo | magneto | indeed
titulo
empresa
ubicacion
modalidad             # remoto | hibrido | presencial | desconocido
salario_raw           # texto original
salario_min           # normalizado, opcional
salario_max           # normalizado, opcional
url
fecha_publicacion
descripcion_raw
fingerprint_contenido # normalizar(empresa)+normalizar(titulo)+ubicacion — ver §6
```

## 4. Módulos

- `conectores/computrabajo.py`, `elempleo.py`, `magneto.py` — `curl_cffi` +
  parsing propio, emiten `Vacante` normalizado.
- `conectores/indeed.py` — envuelve `JobSpy`; categoría aparte con detección de
  fallo propia (§5d, D4).
- `matcher.py` — filtro local + puntuación LLM.
- `cartas.py` — generación de cartas, **bajo demanda** (no en `run`).
- `store.py` — SQLite, dedup de dos niveles, persistencia.
- `reporte.py` — render Markdown.
- `sesion.py` — **diseñado pero NO construido en el MVP** (§5d, D1). Dueño de un
  perfil de navegador persistente + export de cookies. Se activa solo si un
  portal empieza a exigir sesión.
- `cli.py` — `run`, `carta <id>`, (futuro) `login <portal>`.

Cualquier credencial/perfil futuro vive en `secrets/` (ignorado por git), nunca
en el repo.

## 5. Fase 0 — descubrimiento de endpoints (previa a construir conectores)

Antes de escribir cada conector, mapear su endpoint real y su forma de
respuesta. Entregable: `docs/endpoints.md` con endpoint, parámetros y forma de
respuesta por portal. Útil por sí solo aunque no se construya nada más.

**Herramientas:** DevTools del navegador (Copy as cURL / exportar HAR),
`mitmproxy2swagger` (HAR → OpenAPI), `jsluice` (extracción por AST de endpoints
en los bundles JS de las SPAs), `curlconverter` / `har2requests` (captura →
cliente Python), `extruct` (validar el JSON-LD `JobPosting` de Computrabajo).

**Regla de ruta por portal (§5d, D5):** si un portal exige un challenge JS
(Turnstile) que `curl_cffi` no puede pasar, ese conector se declara **conector-
navegador de primera clase** (nodriver/Camoufox), con su propia ruta explícita —
nunca un modo oculto del conector HTTP.

### 5d. Altitud arquitectónica

Por cada decisión no trivial: (a) la opción de mínimo esfuerzo, (b) la opción
correcta, (c) la elegida + por qué, (d) deuda / qué se rompe a 10× o en
producción. Validado con una revisión adversarial de agente fresco.

**D1 — Sesión/autenticación.**
(a) Fácil-tentador: navegador persistente + export de cookies desde el día uno.
(b) Correcta para el MVP: sin sesión; pegar a los listados públicos con `curl_cffi`.
(c) **Elegida: sin sesión.** Los listados de búsqueda son públicos en los cuatro
portales; nada con sesión (recomendados, postulaciones, contacto) aparece en la
salida del pipeline. Construir el subsistema más frágil (navegador + login +
export de cookies + fingerprint matching) para features que nunca se entregan es
gold-plating.
(d) Deuda deliberada: `sesion.py` queda **diseñado** (§4) pero no construido.
Disparador: un portal devuelve 401/403 en el endpoint de listado que usamos → se
agrega sesión **solo a ese portal**. A 10×: sin cambios; el riesgo de sesión
estaba desacoplado del valor.

**D2 — Comportamiento ante cero resultados.**
(a) Fácil: fail-silent, "0 es 0".
(b) Correcta: fail-loud, distinguir búsqueda vacía de conector roto.
(c) **Elegida: fail-loud** vía `ResultadoConector.estado`. El reporte marca
`ERROR` por conector.
(d) Sin fail-loud, un endurecimiento del anti-bot devolvería 0 y el usuario
creería "no hay nada nuevo" por semanas. Cicatriz de truncamiento silencioso
evitada.

**D3 — Identidad de oferta (dedup primaria).**
(a) Fácil: hash de la URL.
(b) Correcta: hash de portal + id nativo.
(c) **Elegida: portal + id nativo.** Una URL con `?utm=` distinto haría aparecer
la misma oferta como nueva en cada corrida.
(d) Requiere que la Fase 0 identifique el id nativo de cada portal. Si un portal
no expone uno estable (riesgo real en Computrabajo vía JSON-LD e Indeed vía
JobSpy), el fallback se documenta en `docs/endpoints.md` — no accidental.

**D4 — Indeed vía JobSpy.**
(a) Fácil: dejar fluir el DataFrame de JobSpy semi-crudo (un "conector falso").
(b) Correcta: adaptador completo al modelo `Vacante`, tratado como categoría aparte.
(c) **Elegida: adaptador completo, categoría aparte.** JobSpy no lo controlamos:
traga errores y devuelve un DataFrame vacío → hay que envolverlo con detección de
fallo dedicada (excepción/vacío → `ERROR` explícito) para no romper el fail-loud
justo en el conector que no controlamos. Verificar que exista un `job_id` estable
antes de confiar en la dedup; si no, un fallback documentado (D3).
(d) A 10×: rate-limit propio de JobSpy; aislado en su módulo sin contaminar a los
otros tres.

**D5 — Ruta HTTP vs navegador por portal.**
(a) Fácil: "fallback transparente" a navegador headless dentro del mismo conector.
(b) Correcta: UNA ruta explícita por portal; conector-navegador de primera clase si hace falta.
(c) **Elegida: ruta explícita.** El "fallback transparente" contradecía "el
navegador no scrapea" y duplicaba en silencio la implementación por portal (dos
rutas que mantener), con challenges JS que nadie resuelve en el cron de las 3am.
(d) Si un portal exige navegador, es un conector-navegador con su propia línea en
el reporte y su propio manejo de challenge. Decisión visible, no un modo oculto.

**D6 — Generación de cartas.**
(a) Fácil-avara: generar una carta para toda oferta que pasa el filtro, dentro de `run`.
(b) Correcta: puntuar en `run` (barato, con tope de gasto); redactar cartas de
forma perezosa, bajo demanda.
(c) **Elegida: perezosa.** Generar cartas para el ~90% de ofertas a las que
nunca se aplica gasta tokens en la frontera equivocada.
(d) `run` solo puntúa, con un **tope de llamadas LLM por corrida** que aborta
fail-loud si el filtro local deja pasar más de lo esperado. Estado por oferta
`PUNTUADA | SIN_PUNTAJE | ERROR` (el paso LLM también es fail-loud, no solo los
conectores). `jobwatch carta <id>` redacta bajo demanda, eligiendo entre las
cartas base existentes del usuario.

**D7 — Frontera de normalización.**
(a) Fácil-confusa: una etapa "normalizador" separada + conectores que emiten
crudo (un contrato mentiroso).
(b) Correcta: normalización dentro del conector; el conector emite `Vacante` limpio.
(c) **Elegida: dentro del conector.** El contrato `buscar()->list[Vacante]`
obliga a que la normalización sucia (salario "$2.000.000 a $3.000.000 COP",
"Bogotá D.C." vs "Bogota", modalidad) tenga un dueño claro: cada conector.
(d) Duplicación menor de lógica de normalización entre conectores → se extrae a
un helper compartido `normalizar.py` si crece, sin cambiar la frontera.

## 6. Deduplicación de dos niveles

1. **Primaria — exacta:** `id_estable = hash(portal + id nativo)`. Caza reposts
   exactos dentro de un mismo portal.
2. **Secundaria — contenido:** `fingerprint_contenido = normalizar(empresa) +
   normalizar(titulo) + ubicacion`. Caza la misma oferta en varios portales o
   re-publicada con id nuevo. Se colapsa en una fila marcada "vista en N portales".

Una oferta es **nueva** si ni su `id_estable` ni su `fingerprint_contenido`
existen en el store.

## 7. Matcher híbrido

1. **Filtro local** (gratis, determinista): keywords de exclusión, salario
   mínimo, modalidad, señales de basura. Descarta ~80%.
2. **Puntuación LLM** (solo sobrevivientes): entrada = `Vacante` + el CV del
   usuario; salida = `{ puntaje 0-100, razon }`. Con un tope de llamadas por
   corrida y estado por oferta (D6). Cada oferta se puntúa una sola vez (solo las
   nuevas).

El CV es un archivo provisto por el usuario, configurado localmente e ignorado
por git — nunca se commitea.

## 8. Store y monitoreo

- **SQLite** (`jobwatch.db`): tabla `vacantes` (clave `id_estable`, índice en
  `fingerprint_contenido`), tabla `corridas` (timestamp, estado por conector).
- **Scheduler:** cron del sistema / Programador de Tareas ejecutando
  `jobwatch run`.
- **Reporte** (`reportes/YYYY-MM-DD.md`): ofertas nuevas puntuadas, ordenadas,
  con enlaces; encabezado con estado por conector (OK/ERROR); una nota sobre
  cuáles se vieron en varios portales.

## 9. Dependencias

`curl_cffi`, `extruct`, `python-jobspy`, `pydantic`, un SDK de LLM
(matcher/cartas). Fase 0 (dev): `mitmproxy2swagger`, `jsluice`,
`curlconverter`/`har2requests`. Futuro (sesión): `nodriver` o `camoufox`.

## 10. Uso responsable / ToS

El acceso automatizado puede estar restringido por los Términos de Servicio de
un portal. A volumen personal y bajo (leyendo listados públicos que ya se
muestran, con pausas entre peticiones) el riesgo práctico es un bloqueo temporal
de IP, no exposición legal. Mitigación: pausas razonables entre peticiones, sin
paralelismo agresivo, respetando el bajo volumen personal, y honrando los
términos de cada sitio y su `robots.txt`. `curl_cffi` provee compatibilidad TLS
de grado navegador para sitios que rechazan clientes no-navegador — no se usa
para vulnerar autenticación ni controles de acceso.
