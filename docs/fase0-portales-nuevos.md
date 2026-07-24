# Fase 0 — Sondeo de los tres portales candidatos

Sondeo ejecutado el **2026-07-24** sobre los tres portales que Juan pidió evaluar,
siguiendo el runbook de `docs/endpoints.md` (`curl_cffi` con `impersonate="chrome124"`).
Término de prueba: **"gerente de proyectos"**, el mismo que se usó para los cuatro
conectores actuales, para que los números sean comparables.

Todo lo que sigue está **medido**, no inferido. Donde una afirmación separa "el
parámetro filtra" de "el parámetro se ignora", se comprobó con un **control negativo**:
un parámetro inventado (`?zzz=nada`) sobre la misma URL. Si el resultado con el
parámetro real es idéntico al del inventado, el portal lo está ignorando.

---

## Veredicto en una tabla

| Portal | HTTP | Listado | Búsqueda | Remoto server-side | Recencia server-side | Paginación | Veredicto |
|---|---|---|---|---|---|---|---|
| **occ.com.mx** | 200 | SSR, 22 tarjetas | ruta `/empleos/de-{slug}/` | **sí** (ruta) | **sí** (`?tm=N`) | `?page=N` | **Adoptar** — el mejor de los tres, y el primero con ambos filtros |
| **vacantes.com** | 200 | SSR (Next.js), 12/pág | `?q=` | **sí** (`?modality=remote`) | no visto | `?page=N` | **Marginal** — 187 vacantes en total; y `robots.txt` prohíbe el listado con query |
| **jobleads.com** | 200 listado / **403 detalle** | SSR, 10 fijas | `?keywords=` | **no** | **no** | **no existe** | **Descartar** — tope de 10 sin declarar, y el detalle está tras Cloudflare |

---

## occ.com.mx — el candidato fuerte

**Listado:** `https://www.occ.com.mx/empleos/de-{slug}/` → 200, ~414 KB, SSR completo.
`{slug}` = término con guiones, igual que Computrabajo.

- **22 tarjetas por página**, `div.card-job-offer`.
- **id nativo** = `data-id` (entero, p. ej. `21260647`), también en `id="jobcard-{id}"`.
- Dentro de la tarjeta: `h2` = título; el primer `span.mr-2.text-sm.font-light` = **fecha
  relativa en español** (`Hoy`, `Ayer`, `Hace 3 días`, `Hace 2 semanas`, `Hace 1 mes`);
  empresa y ubicación en el bloque final (`div.no-alter-loc-text > p` = ubicación).
- **La tarjeta NO trae descripción ni modalidad, y no trae `href`.** La descripción exige
  la etapa `_enriquecer` que ya existe desde PR #3.

### ⚠️ El `ItemList` JSON-LD está incompleto: 16 items para 22 tarjetas

Es la trampa de este portal. Hay un `ItemList` en JSON-LD y es tentador usarlo como
fuente —es el patrón de elempleo y Magneto— pero **solo lista 16 de las 22 tarjetas**.
Un conector que lo tomara perdería 6 vacantes por página **en silencio**, que es
exactamente lo que prohíbe el principio fail-loud (D4/B2). **La fuente primaria es el DOM.**

No hace falta el `ItemList` ni siquiera para la URL de detalle: **el detalle resuelve solo
con el id**. Medido — las tres formas devuelven la misma página de 131 KB:

```
/empleo/oferta/21260471                            200  131KB
/empleo/oferta/21260471-x                          200  131KB   ← slug arbitrario
/empleo/oferta/21260471-technical-project-manager  200  131KB
```

Así que la URL de detalle se construye desde `data-id` y ya.

### Filtros server-side: los dos, y de verdad

Es el **primer portal de los cinco con modalidad y recencia en el servidor**.

- **Modalidad:** segmento de ruta, no query — `/empleos/de-{slug}/tipo-home-office-remoto/`.
  El portal declara los conteos en el propio filtro: Presencial (347), Híbrido (112).
- **Recencia:** `?tm=N` con **N ∈ {0,1,2,3,7,14,30,60}** — granularidad más fina que el
  `pubdate=[1,3,7,15]` de Computrabajo. **`tm=2` existe**, así que el caso `dias=2` que
  en los otros portales cae en una ventana más ancha, aquí es exacto.
- **Salario:** `?smin=`/`?smax=`. **Paginación:** `?page=N`.

Medido sobre el total que declara el propio portal, con el control negativo al final:

| URL | total declarado | tarjetas |
|---|---|---|
| base | 482 | 22 |
| `?tm=1` | 27 | 22 |
| `?tm=3` | 57 | 22 |
| `?tm=30` | 270 | 22 |
| `/tipo-home-office-remoto/` | 23 | 22 |
| `/tipo-home-office-remoto/?tm=7` | **2** | **4** |
| `?zzz=nada` (control) | 482 | 22 |

El control negativo devuelve el mismo conjunto de ids que la base (md5 `5a508d51`),
mientras `tm` y la ruta de remoto sí lo cambian: **los filtros son reales**.

### ⚠️ Las tarjetas "Recomendada" son anuncios que ignoran los filtros

La fila `/tipo-home-office-remoto/?tm=7` de arriba delata el problema: el portal declara
**total = 2** pero pinta **4 tarjetas**. Las 4, en detalle:

```
id=21262900  fecha='Hace 2 días'    tag=Recomendada     ← viola tm=7? no, pero:
id=21260647  fecha='Hace 3 días'    tag=Recomendada
id=21260471  fecha='Hace 3 días'    (sin tag)           ← resultado real 1 de 2
id=21256297  fecha='Hace 1 semana'  (sin tag)           ← resultado real 2 de 2
```

Y con `?tm=1` (último día) las dos primeras tarjetas son **esas mismas dos**, con fechas
"Hace 2 días" y "Hace 3 días" — **violando el filtro que se pidió**. Son anuncios fijos
que se insertan en toda búsqueda, sean cuales sean los filtros.

Dos consecuencias, y conviene no confundirlas:

1. **No basta con descartar las que llevan tag `Recomendada`.** En la corrida de `?tm=1`
   la oferta `21264018` lleva ese tag *y* cumple el filtro ("Ayer"). El tag marca
   "promocionada", no "irrelevante": descartarlas a ciegas también tira vacantes buenas.
2. **La defensa correcta ya está construida.** Es D16 — *el filtro server-side es solo un
   reductor de volumen; el filtro exacto lo aplica `cosechar`*. Este portal es la cuarta
   confirmación independiente de ese principio, y esta vez con un mecanismo nuevo:
   no es que el filtro falle, es que el portal **inyecta filas que no lo respetan**.
   Nada que cambiar en el core.

La que **sí** abre un hueco es la modalidad: los otros conectores derivan la modalidad de
`criterios.modalidad` cuando el filtro es server-side (patrón computrabajo/elempleo). Aquí
eso marcaría las dos promocionadas como REMOTO siendo falso. La modalidad de OCC **solo es
verificable en el detalle** (`Espacio de trabajo: Desde Casa`), es decir, dentro de
`_enriquecer`. Decisión de diseño pendiente, no resuelta aquí.

### Detalle

`/empleo/oferta/{id}` → 200, 131 KB, ~7.800 caracteres de texto. Trae la descripción y
`Espacio de trabajo: Desde Casa` (vocabulario a fijar: las plantillas del listado usan
`Remoto` / `Presencial y remoto` / `Presencial`).

⚠️ **El `JobPosting` JSON-LD del detalle no parsea con `json.loads`.** El `<script>` contiene
**dos objetos JSON concatenados** → `Extra data: line 40 column 2`. Hay que usar
`json.JSONDecoder().raw_decode()`. Además sus claves están **capitalizadas** y no son
schema.org estándar (`"Url"`, `"Title"`, no `"url"`, `"title"`), así que el extractor
JSON-LD de Magneto no se reutiliza tal cual.

### Fin de paginación: silencioso

`?page=99` → **HTTP 200 con 0 tarjetas** (232 KB), no un 404. El `es_fin` de este portal
es "cero tarjetas crudas", que colisiona con el backlog ya conocido de D17: *parser roto →
`n_crudo=0` → fin normal silencioso*. En OCC eso deja de ser hipotético. Buen momento para
retomar el flag `cobertura_completa` que el dueño difirió — el portal **declara el total**
(`482`, `27`, `2`), así que aquí sí hay con qué contrastar la cobertura.

### Lo que OCC abre y `Criterios` no modela

Es **mexicano**. jobwatch asume Colombia en varios sitios: `country_indeed="colombia"`,
dominios `co.`, `normalizar_ubicacion` con ciudades colombianas, salarios en COP. Este
conector no es "uno más": abre la **dimensión de geografía**. Nada de eso se decide en
este documento.

`robots.txt` de OCC, además, es explícito y generoso: `Disallow:/rest` pero
**`Allow:/rest?server=jobs`**. Hay una API JSON que el propio portal autoriza a los
rastreadores. No se llegó a caracterizar (`/rest?server=jobs` sin `service` devuelve
`SVR-03 Petición no autorizada`); queda como pista, no como hallazgo.

---

## vacantes.com — real, correcto, y muy pequeño

**Listado:** `https://vacantes.com/es/vacantes/` → 200, ~545 KB, Next.js con SSR.
La raíz redirige a `/en/`; hay `/es/`, `/en/` y **`/ca/`** (catalán).

- **12 vacantes por página**; URL de detalle `/es/vacantes/{slug}-{hash8}/`, con **id
  nativo** = hash hex de 8 al final del slug.
- **Búsqueda:** `?q=`, confirmado por el propio `SearchAction` de su JSON-LD
  (`https://vacantes.com/es/vacantes/?q={search_term_string}`).
- **Modalidad server-side real:** `?modality=remote` (también `hybrid`, `on_site`) y
  `?type=part_time`.
- **Paginación:** `?page=N` funciona (página 2 devuelve 12 detalles distintos). `?p=2` se
  ignora —control negativo— y `/pagina-2/` da 404.

**El tamaño es el problema.** Totales que declara el portal:

| Consulta | vacantes |
|---|---|
| listado completo | **187** |
| `?modality=remote` | **77** |
| `?q=gerente de proyectos` | **2** |

187 vacantes en todo el portal. A cambio, la **densidad remota es del 41 %** (77/187), muy
por encima de las bolsas grandes, y la geografía es pan-hispana, no colombiana —
Colombia 26, México 21, Argentina 19, España 16, Barcelona 14, Bogotá 7, Madrid 7.

### ⚠️ `robots.txt` prohíbe justamente el listado con query

```
Allow: /vacantes/
Disallow: /api/
Disallow: /*/vacantes/*?
```

El listado **desnudo** está permitido; el listado **con query string** no. Y buscar es
`?q=`, filtrar es `?modality=`, y paginar es `?page=` — las tres son query. Es decir:
**la forma natural de usar este portal es la que `robots.txt` desautoriza.**

Hay una salida limpia que el tamaño del portal hace viable, y merece señalarse porque no
es obvia: **recorrer `/es/vacantes/` entero y filtrar en local**. Son 187 vacantes ≈ 16
páginas... salvo que paginar exige `?page=N`, que vuelve a caer en la prohibición. Queda
como pregunta abierta, no resuelta: si existe una paginación sin query, el recorrido
completo es legítimo y barato; si no, adoptar este portal significa decidir
explícitamente qué peso se le da a su `robots.txt`. **No es una decisión técnica.**

Nota aparte: `api.vacantes.com` existe (responde con formato NestJS) y **no tiene
`robots.txt` propio** — 404 —, así que la regla `Disallow: /api/` del sitio no lo cubre.
No se sondeó más allá de eso.

---

## jobleads.com — descartar

**Listado:** `https://www.jobleads.com/co/jobs` → 200, ~228 KB, Nuxt.

### Casi lo declaro roto por buscar mal el parámetro

El parámetro de búsqueda **no es `q`**. Medido: `?q=contador`, `?q=enfermera` y
`?q=gerente de proyectos` devuelven las **mismas 10 ofertas**, todas "software engineer",
byte por byte iguales a la página sin query. La conclusión tentadora era "jobleads ignora
el término". **Es falsa**: `?keywords=` sí funciona.

```
?q=contador          → md5 bce42f0d  (1º: mid-level-software-engineer)   idéntico a sin query
?keywords=contador   → md5 dfd5b08e  (1º: asistente-contable--bogota)    ✓
?keywords=enfermera  → md5 1cf164c1  (1º: aux-enfermeria-y-sst--bogota)  ✓
```

Es la misma lección que ya costó una conclusión falsa en Magneto: **el parámetro que uno
prueba primero no es necesariamente el que el portal usa**. Un control negativo la habría
atrapado igual, y por eso se corre siempre.

### Lo que sí lo descalifica

Con `?keywords=` fijo, **todo lo demás se ignora**. Cada una de estas devuelve el md5
idéntico al de la consulta base — el mismo que el del parámetro inventado:

```
?keywords=gerente de proyectos                 md5 c580661e   10 ofertas
  + &workplace=remote                          md5 c580661e   ← ignorado
  + &remote=true                               md5 c580661e   ← ignorado
  + &age=1                                     md5 c580661e   ← ignorado
  + &page=2                                    md5 c580661e   ← ignorado
  + &page=99                                   md5 c580661e   ← ignorado
  + &zzz=nada  (control negativo)              md5 c580661e
```

1. **Tope duro de 10 ofertas, sin paginación y sin total declarado.** `page=2` y `page=99`
   devuelven la página 1. Es el mismo defecto por el que se rechazó `ai_search_jobs` de
   Magneto —truncar en silencio— pero **peor**: aquel al menos reportaba `total=23`. Aquí
   no hay ningún número contra el que declarar cobertura parcial. Incompatible con B2/D2.
2. **Sin filtro de remoto ni de recencia.** Las dos dimensiones que Plan C hizo centrales.
3. **El detalle está tras Cloudflare.** `/co/job/{slug}--{ciudad}--{hash}` → **403 "Just a
   moment... Enable JavaScript and cookies to continue"**, incluso con `chrome124`, que sí
   pasa el Cloudflare de Computrabajo. Sin detalle no hay descripción, y sin descripción no
   se puede decidir si la oferta exige inglés — la pregunta central del buscador (defecto
   #1 de PR #3).

Los tres riesgos que se habían anticipado para un agregador (muro de registro, colisión
con el dedup) ni siquiera llegan a evaluarse: **el portal no entrega suficiente material
para probarlos**. Adoptarlo exigiría promoverlo a conector-navegador (nodriver/Camoufox)
y aun así toparía con el tope de 10.

---

## Cómo reproducir

Los scripts del sondeo son de usar y tirar; lo reproducible es el método:

1. Home + `robots.txt` de cada portal. **`robots.txt` primero** — en dos de los tres
   cambió el veredicto.
2. Listado con el término de prueba; contar filas crudas en el DOM y comparar con el
   total que declare el portal. Si no coinciden, buscar por qué **antes** de diseñar.
3. Cada parámetro sospechoso contra un **control negativo** (`?zzz=nada`) sobre la misma
   URL. Igual md5 de ids ⇒ el portal lo ignora.
4. Probar más de un valor del parámetro de búsqueda (`contador` vs `enfermera`): un solo
   valor no distingue "filtra" de "devuelve siempre lo mismo".
5. Una página de detalle real: status, descripción, modalidad, y si el JSON-LD parsea.
