# Plan A — Motor multi-portal (jobwatch) — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Añadir los tres conectores colombianos (Computrabajo, elempleo, Magneto) al motor de jobwatch y saldar las dos deudas heredadas (dedup en-lote con colapso "vista en N portales", y propagación de `detalle` por conector al reporte), incluyendo la migración de schema que ambas requieren.

**Architecture:** Cada conector es un archivo nuevo en `src/jobwatch/conectores/` que cumple el contrato existente `buscar(criterios, fetch=None) -> ResultadoConector`, con el fetch (curl_cffi) inyectado como callable para testear offline contra fixtures de HTML recortado. La normalización vive dentro del conector (D7). El colapso en-lote y la propagación de `detalle` se implementan en la estructura actual (`orquestador.correr` + `store` + `reporte.render`). Diseño de referencia: `docs/design-skill.md` (§6, D11–D13) y `docs/design.md` (§3.1, §6).

**Tech Stack:** Python ≥3.10, `beautifulsoup4` + `lxml` (parsing HTML), `curl_cffi` (fetch), `pydantic` (modelos), `pytest` + `ruff`.

## Global Constraints

- Python ≥ 3.10; `ruff` line-length 100; `pytest` resuelve imports vía `pythonpath = ["src", "."]`.
- **Repo público:** commits con email noreply (identidad local ya configurada); **nada personal** (nunca `data/`, `secrets/`, `*.db`, `discovery/captures/`). Copy de cara al usuario en **español**.
- **TDD estricto:** test que falla → implementación mínima → correr → commit. Un commit por tarea (o sub-deliverable claro).
- **Conectores offline:** el fetch se inyecta; los tests NUNCA tocan la red. Fixtures en `tests/conectores/fixtures/{portal}.html` (ya creados, HTML real recortado).
- **Fail-loud (D2):** excepción de fetch → `EstadoConector.ERROR` con `detalle`; filas inválidas se cuentan en `detalle` ("N filas omitidas"), no se tragan en silencio.
- **Contrato de conector (D7):** `def buscar(criterios: Criterios, fetch=None) -> ResultadoConector`. El conector construye su propia URL y normaliza dentro (emite `Vacante` limpio).

---

## File Structure

- Create: `src/jobwatch/conectores/_comun.py` — helpers compartidos (fetch por defecto, slug, id-de-url, coincidencia de término, normalización de texto).
- Create: `src/jobwatch/conectores/computrabajo.py`, `elempleo.py`, `magneto.py` — los tres conectores.
- Create: `tests/conectores/test_computrabajo.py`, `test_elempleo.py`, `test_magneto.py`, `test_comun.py`.
- Modify: `src/jobwatch/modelos.py` — campo `portales` en `Vacante`, constante `PRIORIDAD_PORTAL`.
- Modify: `src/jobwatch/orquestador.py` — colapso en-lote + propagar `resultados` (con `detalle`).
- Modify: `src/jobwatch/store.py` — migración `PRAGMA user_version` + columna `portales`; `registrar_corrida` guarda `{portal:{estado,detalle}}`.
- Modify: `src/jobwatch/reporte.py` — render de `detalle` por conector y nota "vista en N portales".
- Modify: `src/jobwatch/cli.py` — cablear los tres conectores.
- Modify: `pyproject.toml` — añadir `beautifulsoup4`.
- Modify (tests existentes): `tests/test_reporte.py`, `tests/test_store.py`, `tests/test_orquestador.py` — adaptar a las firmas nuevas.

Fixtures (ya existentes, NO recrear): `tests/conectores/fixtures/computrabajo.html`, `elempleo.html`, `magneto.html`.

---

### Task 1: Helpers compartidos + dependencia de parser

**Files:**
- Modify: `pyproject.toml` (dependencies)
- Create: `src/jobwatch/conectores/_comun.py`
- Test: `tests/conectores/test_comun.py`

**Interfaces:**
- Produces:
  - `fetch_curl(url: str) -> str` — GET con curl_cffi `chrome124`, `raise_for_status`, devuelve `r.text`. (Import perezoso de curl_cffi para tests offline.)
  - `slug(termino: str) -> str` — `"Gerente de Proyectos" -> "gerente-de-proyectos"`.
  - `id_de_url(url: str) -> str` — dígitos finales de una URL (`".../algo-1004184" -> "1004184"`); `""` si no hay.
  - `texto(node) -> str` — `get_text()` colapsado a espacios simples y `strip()`; `""` si `node` es `None`.
  - `coincide_termino(titulo: str, terminos: str) -> bool` — `True` si todos los tokens significativos (len≥3, sin stopwords) del término aparecen como palabra en el título normalizado; `True` si no hay tokens significativos.

- [ ] **Step 1: Añadir `beautifulsoup4` a `pyproject.toml`.** En `[project].dependencies`, añadir la línea (mantener orden alfabético relativo):

```toml
    "beautifulsoup4>=4.12",
```

- [ ] **Step 2: Instalar en el venv.**

Run: `.venv/bin/pip install -e . -q`
Expected: instala sin error (bs4 y lxml quedan disponibles).

- [ ] **Step 3: Escribir el test de los helpers.**

Crear `tests/conectores/test_comun.py`:

```python
from bs4 import BeautifulSoup

from jobwatch.conectores._comun import (
    coincide_termino, id_de_url, slug, texto,
)


def test_slug():
    assert slug("Gerente de Proyectos") == "gerente-de-proyectos"


def test_id_de_url_toma_digitos_finales():
    assert id_de_url("https://x/co/empleos/gestor-en-sitio-1004184") == "1004184"
    assert id_de_url("https://x/co/ofertas-trabajo/gerente-1886730317") == "1886730317"
    assert id_de_url("https://x/sin-numero") == ""


def test_texto_colapsa_espacios_y_tolera_none():
    sopa = BeautifulSoup("<a>  Hola   mundo\n </a>", "lxml")
    assert texto(sopa.a) == "Hola mundo"
    assert texto(None) == ""


def test_coincide_termino():
    assert coincide_termino("Gerente de proyectos", "gerente de proyectos") is True
    assert coincide_termino("Gestor de servicio en sitio", "gerente de proyectos") is False
    # acentos y mayúsculas no importan; 'de' es stopword y se ignora
    assert coincide_termino("GESTIÓN de Proyéctos TI", "proyectos") is True
```

- [ ] **Step 4: Correr el test y verlo fallar.**

Run: `.venv/bin/pytest tests/conectores/test_comun.py -q`
Expected: FAIL — `ModuleNotFoundError: jobwatch.conectores._comun`.

- [ ] **Step 5: Implementar `_comun.py`.**

Crear `src/jobwatch/conectores/_comun.py`:

```python
from __future__ import annotations

import re

from jobwatch.modelos import _clave

IMPERSONATE = "chrome124"  # perfil de navegador reciente para curl_cffi

_STOPWORDS = {"de", "la", "el", "en", "y", "a", "del", "los", "las", "para", "con"}


def fetch_curl(url: str) -> str:
    """GET con TLS de grado navegador. Import perezoso para mantener tests offline."""
    from curl_cffi import requests

    r = requests.get(url, impersonate=IMPERSONATE, timeout=30)
    r.raise_for_status()
    return r.text or ""


def slug(termino: str) -> str:
    return "-".join(termino.lower().split())


def id_de_url(url: str) -> str:
    m = re.search(r"(\d+)(?:[/?#].*)?$", url)
    return m.group(1) if m else ""


def texto(node) -> str:
    if node is None:
        return ""
    return " ".join(node.get_text().split())


def coincide_termino(titulo: str, terminos: str) -> bool:
    t = _clave(titulo)
    toks = [w for w in _clave(terminos).split() if len(w) >= 3 and w not in _STOPWORDS]
    if not toks:
        return True
    return all(re.search(rf"\b{re.escape(w)}\b", t) for w in toks)
```

- [ ] **Step 6: Correr el test y verlo pasar.**

Run: `.venv/bin/pytest tests/conectores/test_comun.py -q`
Expected: PASS (4 tests).

- [ ] **Step 7: Lint + commit.**

```bash
.venv/bin/ruff check src tests
git add pyproject.toml src/jobwatch/conectores/_comun.py tests/conectores/test_comun.py
git commit -m "feat: shared connector helpers (fetch, slug, id-from-url, term match)"
```

---

### Task 2: Conector Computrabajo

**Files:**
- Create: `src/jobwatch/conectores/computrabajo.py`
- Test: `tests/conectores/test_computrabajo.py`

**Interfaces:**
- Consumes: `_comun.{fetch_curl, slug, texto}`; `modelos.{Criterios, EstadoConector, ResultadoConector, Vacante}`; `normalizar.{normalizar_ubicacion, parsear_salario}`.
- Produces: `buscar(criterios: Criterios, fetch=None) -> ResultadoConector` con `portal="computrabajo"`.

Selectores reales (verificados contra el fixture):
- contenedor: `article.box_offer` (match por token de clase; hay clases extra como `sel`/`outstanding`).
- `id_nativo`: atributo `data-id` (hex mayúsculas de 32).
- `titulo` + `url`: `h2 a.js-o-link` — texto y `href` (relativo → resolver contra el host; quitar el `#lc=…`).
- `empresa`: `a[offer-grid-article-company-url]` (anclar por el atributo, no por posición).
- `ubicacion`: `p.fs16.fc_base.mt5:not(.dFlex) > span.mr10` (el `:not(.dFlex)` descarta el `<p>` de empresa, que comparte clases).
- `salario` (opcional): presente solo si existe `span.i_salary`; texto de `div.fs13.mt15 span.dIB.mr10`.

- [ ] **Step 1: Escribir el test.**

Crear `tests/conectores/test_computrabajo.py`:

```python
from pathlib import Path

from jobwatch.conectores.computrabajo import buscar
from jobwatch.modelos import Criterios, EstadoConector

FIXTURE = (Path(__file__).parent / "fixtures" / "computrabajo.html").read_text(encoding="utf-8")


def _fetch_ok(url):
    return FIXTURE


def test_parsea_dos_ofertas_del_fixture():
    r = buscar(Criterios(terminos="gerente de proyectos"), fetch=_fetch_ok)
    assert r.estado is EstadoConector.OK
    assert len(r.vacantes) == 2
    v0, v1 = r.vacantes
    assert v0.portal == "computrabajo"
    assert v0.id_nativo == "067CFDC9FD215E0B61373E686DCF3405"
    assert v0.titulo == "Director de Proyectos Fotovoltaico"
    assert v0.empresa == "GLOBALEM S.A.S"
    assert v0.ubicacion == "Bogotá"
    assert v0.url.startswith("https://co.computrabajo.com/ofertas-de-trabajo/")
    assert "#" not in v0.url          # el fragmento #lc= se quitó
    assert v0.salario_max is None     # oferta 1 no trae salario


def test_extrae_salario_cuando_existe():
    r = buscar(Criterios(terminos="x"), fetch=_fetch_ok)
    v1 = r.vacantes[1]
    assert v1.empresa == "Proservis"
    assert v1.ubicacion == "Cali"
    assert v1.salario_max == 8_529_999


def test_fetch_falla_es_error_fail_loud():
    def explota(url):
        raise RuntimeError("403 bloqueado")
    r = buscar(Criterios(terminos="x"), fetch=explota)
    assert r.estado is EstadoConector.ERROR and "403 bloqueado" in r.detalle
```

- [ ] **Step 2: Correr y ver fallar.**

Run: `.venv/bin/pytest tests/conectores/test_computrabajo.py -q`
Expected: FAIL — `ModuleNotFoundError: jobwatch.conectores.computrabajo`.

- [ ] **Step 3: Implementar el conector.**

Crear `src/jobwatch/conectores/computrabajo.py`:

```python
from __future__ import annotations

from urllib.parse import urljoin

from bs4 import BeautifulSoup

from jobwatch.conectores._comun import fetch_curl, slug, texto
from jobwatch.modelos import Criterios, EstadoConector, ResultadoConector, Vacante
from jobwatch.normalizar import normalizar_ubicacion, parsear_salario

HOST = "https://co.computrabajo.com"


def _url(criterios: Criterios) -> str:
    return f"{HOST}/trabajo-de-{slug(criterios.terminos)}"


def _a_vacante(art) -> Vacante:
    a = art.select_one("h2 a.js-o-link")
    href = a.get("href", "").split("#")[0] if a else ""
    empresa = art.select_one("a[offer-grid-article-company-url]")
    ubic = art.select_one("p.fs16.fc_base.mt5:not(.dFlex) > span.mr10")
    salario_raw = ""
    if art.select_one("span.i_salary"):
        salario_raw = texto(art.select_one("div.fs13.mt15 span.dIB.mr10"))
    smin, smax = parsear_salario(salario_raw) if salario_raw else (None, None)
    return Vacante(
        id_nativo=art.get("data-id", ""),
        portal="computrabajo",
        titulo=texto(a),
        empresa=texto(empresa),
        ubicacion=normalizar_ubicacion(texto(ubic)),
        salario_raw=salario_raw,
        salario_min=smin,
        salario_max=smax,
        url=urljoin(HOST, href),
    )


def buscar(criterios: Criterios, fetch=None) -> ResultadoConector:
    fetch = fetch or fetch_curl
    try:
        html = fetch(_url(criterios))
    except Exception as e:  # fail-loud (D2)
        return ResultadoConector(estado=EstadoConector.ERROR, detalle=str(e))

    sopa = BeautifulSoup(html, "lxml")
    vacantes: list[Vacante] = []
    omitidas = 0
    for art in sopa.select("article.box_offer"):
        try:
            v = _a_vacante(art)
            if not v.id_nativo or not v.titulo:
                omitidas += 1
                continue
            vacantes.append(v)
        except Exception:
            omitidas += 1

    detalle = f"{omitidas} filas omitidas por datos inválidos" if omitidas else ""
    return ResultadoConector(estado=EstadoConector.OK, vacantes=vacantes, detalle=detalle)
```

- [ ] **Step 4: Correr y ver pasar.**

Run: `.venv/bin/pytest tests/conectores/test_computrabajo.py -q`
Expected: PASS (3 tests).

- [ ] **Step 5: Lint + commit.**

```bash
.venv/bin/ruff check src tests
git add src/jobwatch/conectores/computrabajo.py tests/conectores/test_computrabajo.py
git commit -m "feat: Computrabajo connector (DOM parse, injected fetch, fail-loud)"
```

---

### Task 3: Conector elempleo

**Files:**
- Create: `src/jobwatch/conectores/elempleo.py`
- Test: `tests/conectores/test_elempleo.py`

**Interfaces:**
- Consumes: `_comun.{fetch_curl, slug}`; `modelos.*`; `normalizar.{normalizar_ubicacion, parsear_salario}`.
- Produces: `buscar(criterios, fetch=None) -> ResultadoConector` con `portal="elempleo"`.

Estrategia (doble fuente): iterar el JSON-LD `ItemList` para obtener `@id` (URL absoluta de detalle) e id nativo (dígitos finales); emparejar por id con el card del DOM, cuyo `data-ga4-offerdata` es un **JSON decodificado** con `title`, `company`, `location`, `salary` (fuente limpia, preferible a los selectores por clase).

- [ ] **Step 1: Escribir el test.**

Crear `tests/conectores/test_elempleo.py`:

```python
from pathlib import Path

from jobwatch.conectores.elempleo import buscar
from jobwatch.modelos import Criterios, EstadoConector

FIXTURE = (Path(__file__).parent / "fixtures" / "elempleo.html").read_text(encoding="utf-8")


def test_parsea_itemlist_y_cards():
    r = buscar(Criterios(terminos="gerente de proyectos"), fetch=lambda url: FIXTURE)
    assert r.estado is EstadoConector.OK
    assert len(r.vacantes) == 2
    porid = {v.id_nativo: v for v in r.vacantes}
    v = porid["1886730317"]
    assert v.portal == "elempleo"
    assert v.titulo == "Gerente de proyectos"
    assert v.empresa == "ENTELGY COLOMBIA S.A.S"
    assert v.ubicacion == "Bogotá"
    assert v.url == "https://www.elempleo.com/co/ofertas-trabajo/gerente-de-proyectos-1886730317"
    assert v.salario_min is None            # "Salario confidencial" -> sin números
    assert porid["1886741235"].empresa == "JAHV MC GREGOR S.A.S"


def test_fetch_falla_es_error():
    def explota(url):
        raise RuntimeError("timeout")
    r = buscar(Criterios(terminos="x"), fetch=explota)
    assert r.estado is EstadoConector.ERROR and "timeout" in r.detalle
```

- [ ] **Step 2: Correr y ver fallar.**

Run: `.venv/bin/pytest tests/conectores/test_elempleo.py -q`
Expected: FAIL — `ModuleNotFoundError: jobwatch.conectores.elempleo`.

- [ ] **Step 3: Implementar el conector.**

Crear `src/jobwatch/conectores/elempleo.py`:

```python
from __future__ import annotations

import json

from bs4 import BeautifulSoup

from jobwatch.conectores._comun import fetch_curl, id_de_url, slug
from jobwatch.modelos import Criterios, EstadoConector, ResultadoConector, Vacante
from jobwatch.normalizar import normalizar_ubicacion, parsear_salario

HOST = "https://www.elempleo.com"


def _url(criterios: Criterios) -> str:
    return f"{HOST}/co/ofertas-empleo/trabajo-{slug(criterios.terminos)}"


def _items_jsonld(sopa) -> list[dict]:
    """Items del ItemList: {id, url, name}. Tolera varios bloques JSON-LD."""
    items: list[dict] = []
    for script in sopa.select('script[type="application/ld+json"]'):
        try:
            datos = json.loads(script.string or "")
        except Exception:
            continue
        if datos.get("@type") != "ItemList":
            continue
        for el in datos.get("itemListElement", []):
            item = el.get("item", {})
            url = item.get("@id", "")
            items.append({"id": id_de_url(url), "url": url, "name": item.get("name", "")})
    return items


def _cards_por_id(sopa) -> dict[str, dict]:
    """Índice id -> JSON de data-ga4-offerdata (title, company, location, salary)."""
    porid: dict[str, dict] = {}
    for div in sopa.select("[data-ga4-offerdata]"):
        try:
            datos = json.loads(div["data-ga4-offerdata"])
            porid[str(datos["id"])] = datos
        except Exception:
            continue
    return porid


def buscar(criterios: Criterios, fetch=None) -> ResultadoConector:
    fetch = fetch or fetch_curl
    try:
        html = fetch(_url(criterios))
    except Exception as e:
        return ResultadoConector(estado=EstadoConector.ERROR, detalle=str(e))

    sopa = BeautifulSoup(html, "lxml")
    cards = _cards_por_id(sopa)
    vacantes: list[Vacante] = []
    omitidas = 0
    for it in _items_jsonld(sopa):
        card = cards.get(it["id"])
        if not it["id"] or card is None:
            omitidas += 1
            continue
        try:
            salario_raw = str(card.get("salary", "") or "")
            smin, smax = parsear_salario(salario_raw)
            vacantes.append(Vacante(
                id_nativo=it["id"],
                portal="elempleo",
                titulo=str(card.get("title") or it["name"]),
                empresa=str(card.get("company", "")),
                ubicacion=normalizar_ubicacion(str(card.get("location", ""))),
                salario_raw=salario_raw,
                salario_min=smin,
                salario_max=smax,
                url=it["url"],
            ))
        except Exception:
            omitidas += 1

    detalle = f"{omitidas} filas omitidas por datos inválidos" if omitidas else ""
    return ResultadoConector(estado=EstadoConector.OK, vacantes=vacantes, detalle=detalle)
```

- [ ] **Step 4: Correr y ver pasar.**

Run: `.venv/bin/pytest tests/conectores/test_elempleo.py -q`
Expected: PASS (2 tests).

- [ ] **Step 5: Lint + commit.**

```bash
.venv/bin/ruff check src tests
git add src/jobwatch/conectores/elempleo.py tests/conectores/test_elempleo.py
git commit -m "feat: elempleo connector (JSON-LD ItemList + data-ga4 card match)"
```

---

### Task 4: Conector Magneto

**Files:**
- Create: `src/jobwatch/conectores/magneto.py`
- Test: `tests/conectores/test_magneto.py`

**Interfaces:**
- Consumes: `_comun.{fetch_curl, id_de_url, texto, coincide_termino}`; `modelos.*`; `normalizar.{normalizar_ubicacion, parsear_salario}`.
- Produces: `buscar(criterios, fetch=None) -> ResultadoConector` con `portal="magneto"`.

Notas reales (verificadas): el JSON-LD `ItemList` solo trae `{position, url}` (sin `name`). **`?search=` NO filtra** el listado (devuelve un feed genérico) → el conector filtra **client-side** por el término (`coincide_termino`). Las clases del card llevan un hash de módulo (`_13c81`) frágil → anclar por estructura: `article` que contenga `h2 a[href*="/co/empleos/"]`. Campos del card: título/url en `h2 a`; empresa (antes de `|`) en `h3`; salario en el 1er `<p>`, ubicación en el 2º. Sin fecha en SSR. Riesgo D5 documentado abajo.

- [ ] **Step 1: Escribir el test.**

Crear `tests/conectores/test_magneto.py`:

```python
from pathlib import Path

from jobwatch.conectores.magneto import buscar
from jobwatch.modelos import Criterios, EstadoConector

FIXTURE = (Path(__file__).parent / "fixtures" / "magneto.html").read_text(encoding="utf-8")


def test_extrae_campos_cuando_el_termino_coincide():
    # el feed trae "Gestor de servicio en sitio"; con ese término el card pasa el filtro
    r = buscar(Criterios(terminos="gestor de servicio"), fetch=lambda url: FIXTURE)
    assert r.estado is EstadoConector.OK
    assert len(r.vacantes) == 1
    v = r.vacantes[0]
    assert v.portal == "magneto"
    assert v.id_nativo == "1004184"
    assert v.titulo == "Gestor de servicio en sitio"
    assert v.empresa == "Confidencial"
    assert v.ubicacion == "Bogotá"
    assert v.url.endswith("/co/empleos/gestor-de-servicio-en-sitio-1004184")
    assert v.salario_min == 500_000 and v.salario_max == 3_000_000


def test_filtra_client_side_cuando_search_no_filtra():
    # el portal ignora ?search=; ningún card del feed es "gerente de proyectos"
    r = buscar(Criterios(terminos="gerente de proyectos"), fetch=lambda url: FIXTURE)
    assert r.estado is EstadoConector.OK and r.vacantes == []


def test_fetch_falla_es_error():
    def explota(url):
        raise RuntimeError("503")
    r = buscar(Criterios(terminos="x"), fetch=explota)
    assert r.estado is EstadoConector.ERROR and "503" in r.detalle
```

- [ ] **Step 2: Correr y ver fallar.**

Run: `.venv/bin/pytest tests/conectores/test_magneto.py -q`
Expected: FAIL — `ModuleNotFoundError: jobwatch.conectores.magneto`.

- [ ] **Step 3: Implementar el conector.**

Crear `src/jobwatch/conectores/magneto.py`:

```python
from __future__ import annotations

from bs4 import BeautifulSoup

from jobwatch.conectores._comun import (
    coincide_termino, fetch_curl, id_de_url, texto,
)
from jobwatch.modelos import Criterios, EstadoConector, ResultadoConector, Vacante
from jobwatch.normalizar import normalizar_ubicacion, parsear_salario

HOST = "https://www.magneto365.com"


def _url(criterios: Criterios) -> str:
    from urllib.parse import quote_plus

    # NOTA (D5): ?search= no filtra el listado (feed genérico); el filtrado real
    # es client-side por término. Reconfirmar el parámetro correcto en un probe futuro.
    return f"{HOST}/co/trabajos/buscar?search={quote_plus(criterios.terminos)}"


def _a_vacante(art) -> Vacante:
    a = art.select_one('h2 a[href*="/co/empleos/"]')
    url = a.get("href", "")
    h3 = art.select_one("h3")
    empresa = texto(h3).split("|")[0].strip()
    ps = art.select("p")
    salario_raw = texto(ps[0]) if ps else ""
    ubicacion = texto(ps[1]) if len(ps) > 1 else ""
    smin, smax = parsear_salario(salario_raw)
    return Vacante(
        id_nativo=id_de_url(url),
        portal="magneto",
        titulo=a.get("title") or texto(a),
        empresa=empresa,
        ubicacion=normalizar_ubicacion(ubicacion),
        salario_raw=salario_raw,
        salario_min=smin,
        salario_max=smax,
        url=url,
    )


def buscar(criterios: Criterios, fetch=None) -> ResultadoConector:
    fetch = fetch or fetch_curl
    try:
        html = fetch(_url(criterios))
    except Exception as e:
        return ResultadoConector(estado=EstadoConector.ERROR, detalle=str(e))

    sopa = BeautifulSoup(html, "lxml")
    vacantes: list[Vacante] = []
    omitidas = 0
    for art in sopa.select("article"):
        if art.select_one('h2 a[href*="/co/empleos/"]') is None:
            continue  # no es un card de oferta (p. ej. el panel de detalle)
        try:
            v = _a_vacante(art)
            if not v.id_nativo or not v.titulo:
                omitidas += 1
                continue
            if not coincide_termino(v.titulo, criterios.terminos):
                continue  # el feed no filtra; descartar lo que no coincide
            vacantes.append(v)
        except Exception:
            omitidas += 1

    detalle = f"{omitidas} filas omitidas por datos inválidos" if omitidas else ""
    return ResultadoConector(estado=EstadoConector.OK, vacantes=vacantes, detalle=detalle)
```

- [ ] **Step 4: Correr y ver pasar.**

Run: `.venv/bin/pytest tests/conectores/test_magneto.py -q`
Expected: PASS (3 tests).

- [ ] **Step 5: Lint + commit.**

```bash
.venv/bin/ruff check src tests
git add src/jobwatch/conectores/magneto.py tests/conectores/test_magneto.py
git commit -m "feat: Magneto connector (JSON-LD feed, client-side term filter)"
```

---

### Task 5: `portales` en `Vacante` + `PRIORIDAD_PORTAL` + colapso en-lote

**Files:**
- Modify: `src/jobwatch/modelos.py`
- Modify: `src/jobwatch/orquestador.py`
- Test: `tests/test_orquestador.py` (añadir casos; adaptar los existentes en Task 7)

**Interfaces:**
- Produces:
  - `Vacante.portales: list[str]` — por defecto `[self.portal]` (se computa en el validador si viene vacío).
  - `PRIORIDAD_PORTAL: list[str]` en `modelos.py`.
  - `colapsar_lote(vacantes: list[Vacante]) -> list[Vacante]` en `orquestador.py` — agrupa por `fingerprint_contenido`, elige la fila canónica por `PRIORIDAD_PORTAL` y fija `portales` = unión ordenada por prioridad.

- [ ] **Step 1: Escribir el test del colapso.**

Añadir a `tests/test_orquestador.py`:

```python
from jobwatch.modelos import Vacante
from jobwatch.orquestador import colapsar_lote


def _v(portal, empresa="ACME", titulo="Gerente de Proyectos", ubic="Bogotá", idn="1"):
    return Vacante(id_nativo=idn, portal=portal, titulo=titulo, empresa=empresa,
                   ubicacion=ubic, url=f"https://{portal}/{idn}")


def test_portales_por_defecto_es_el_propio_portal():
    assert _v("magneto").portales == ["magneto"]


def test_colapsa_misma_oferta_en_dos_portales_por_prioridad():
    # misma empresa+titulo+ubicacion -> mismo fingerprint; distinto portal
    vs = [_v("magneto", idn="9"), _v("computrabajo", idn="1")]
    out = colapsar_lote(vs)
    assert len(out) == 1
    canon = out[0]
    assert canon.portal == "computrabajo"                 # gana por PRIORIDAD_PORTAL
    assert canon.portales == ["computrabajo", "magneto"]  # unión ordenada por prioridad


def test_no_colapsa_ofertas_distintas():
    vs = [_v("computrabajo", empresa="A"), _v("elempleo", empresa="B")]
    assert len(colapsar_lote(vs)) == 2
```

- [ ] **Step 2: Correr y ver fallar.**

Run: `.venv/bin/pytest tests/test_orquestador.py -q -k "colaps or portales"`
Expected: FAIL — `ImportError: cannot import name 'colapsar_lote'` (y `portales` no existe).

- [ ] **Step 3: Añadir `portales` y `PRIORIDAD_PORTAL` a `modelos.py`.**

En `src/jobwatch/modelos.py`, tras las funciones de hashing (después de `calcular_fingerprint`), añadir la constante:

```python
# Prioridad para elegir la fila canónica al colapsar una oferta vista en varios
# portales (D11). Orden por estabilidad del id nativo observada en Fase 0.
PRIORIDAD_PORTAL = ["computrabajo", "elempleo", "magneto", "indeed"]
```

En la clase `Vacante`, añadir el campo (junto a los otros con default):

```python
    portales: list[str] = []
```

Y en el validador `_computar`, tras fijar `fingerprint_contenido`, añadir:

```python
        if not self.portales:
            object.__setattr__(self, "portales", [self.portal])
```

- [ ] **Step 4: Implementar `colapsar_lote` en `orquestador.py`.**

En `src/jobwatch/orquestador.py`, añadir el import y la función:

```python
from jobwatch.modelos import PRIORIDAD_PORTAL, Vacante
```

```python
def _prioridad(portal: str) -> int:
    return PRIORIDAD_PORTAL.index(portal) if portal in PRIORIDAD_PORTAL else len(PRIORIDAD_PORTAL)


def colapsar_lote(vacantes: list[Vacante]) -> list[Vacante]:
    """Colapsa por fingerprint_contenido dentro del lote (D11): elige la fila
    canónica por PRIORIDAD_PORTAL y fija portales = unión ordenada por prioridad."""
    grupos: dict[str, list[Vacante]] = {}
    for v in vacantes:
        grupos.setdefault(v.fingerprint_contenido, []).append(v)

    salida: list[Vacante] = []
    for grupo in grupos.values():
        canon = min(grupo, key=lambda v: _prioridad(v.portal))
        portales = sorted({v.portal for v in grupo}, key=_prioridad)
        canon.portales = portales
        salida.append(canon)
    return salida
```

- [ ] **Step 5: Correr y ver pasar.**

Run: `.venv/bin/pytest tests/test_orquestador.py -q -k "colaps or portales"`
Expected: PASS (3 tests).

- [ ] **Step 6: Lint + commit.**

```bash
.venv/bin/ruff check src tests
git add src/jobwatch/modelos.py src/jobwatch/orquestador.py tests/test_orquestador.py
git commit -m "feat: in-batch collapse with portales[] and PRIORIDAD_PORTAL (D11)"
```

---

### Task 6: Migración de schema + persistir `portales`

**Files:**
- Modify: `src/jobwatch/store.py`
- Test: `tests/test_store.py`

**Interfaces:**
- Produces: schema versionado con `PRAGMA user_version`; columna `vacantes.portales TEXT NOT NULL DEFAULT '[]'`; `persistir` guarda `portales` (JSON). Retrocompatible con un `jobwatch.db` v0 existente (ALTER TABLE).

- [ ] **Step 1: Escribir el test.**

Añadir a `tests/test_store.py`:

```python
import json
import sqlite3

from jobwatch.store import Store


def test_persistir_guarda_portales(tmp_path):
    ruta = str(tmp_path / "j.db")
    store = Store(ruta)
    from jobwatch.modelos import Vacante
    v = Vacante(id_nativo="1", portal="computrabajo", titulo="X", empresa="ACME",
                ubicacion="Bogotá", url="https://x/1", portales=["computrabajo", "magneto"])
    store.persistir([v])
    store.cerrar()
    con = sqlite3.connect(ruta)
    fila = con.execute("SELECT portales FROM vacantes WHERE id_estable = ?", (v.id_estable,)).fetchone()
    assert json.loads(fila[0]) == ["computrabajo", "magneto"]


def test_migra_base_v0_existente(tmp_path):
    ruta = str(tmp_path / "viejo.db")
    # base v0: tabla vacantes SIN columna portales, user_version 0
    con = sqlite3.connect(ruta)
    con.executescript(
        """
        CREATE TABLE vacantes (
            id_estable TEXT PRIMARY KEY, fingerprint_contenido TEXT NOT NULL,
            portal TEXT NOT NULL, titulo TEXT NOT NULL, empresa TEXT NOT NULL,
            url TEXT NOT NULL, datos TEXT NOT NULL);
        CREATE TABLE corridas (id INTEGER PRIMARY KEY AUTOINCREMENT, estados TEXT NOT NULL);
        """
    )
    con.commit()
    con.close()
    # abrir con Store debe migrar sin perder la fila y añadir la columna
    store = Store(ruta)
    assert store.con.execute("PRAGMA user_version").fetchone()[0] == 1
    cols = [r[1] for r in store.con.execute("PRAGMA table_info(vacantes)")]
    assert "portales" in cols
    store.cerrar()
```

- [ ] **Step 2: Correr y ver fallar.**

Run: `.venv/bin/pytest tests/test_store.py -q -k "portales or migra"`
Expected: FAIL — no existe la columna `portales` / `user_version` sigue en 0.

- [ ] **Step 3: Implementar la migración en `store.py`.**

Reemplazar `_init_schema` por un esquema base + migraciones versionadas, y actualizar `persistir`.

En `_init_schema`, tras crear las tablas base (dejar el `CREATE TABLE IF NOT EXISTS` actual **sin** la columna `portales` para no divergir de bases v0), añadir al final del método:

```python
        self._migrar()
```

Añadir el método de migración:

```python
    def _migrar(self) -> None:
        version = self.con.execute("PRAGMA user_version").fetchone()[0]
        if version < 1:
            cols = [r[1] for r in self.con.execute("PRAGMA table_info(vacantes)")]
            if "portales" not in cols:
                self.con.execute(
                    "ALTER TABLE vacantes ADD COLUMN portales TEXT NOT NULL DEFAULT '[]'"
                )
            self.con.execute("PRAGMA user_version = 1")
            self.con.commit()
```

Actualizar `persistir` para incluir `portales` (JSON):

```python
    def persistir(self, vacantes: list[Vacante]) -> None:
        import json
        self.con.executemany(
            """
            INSERT INTO vacantes
                (id_estable, fingerprint_contenido, portal, titulo, empresa, url, portales, datos)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(id_estable) DO NOTHING
            """,
            [
                (v.id_estable, v.fingerprint_contenido, v.portal, v.titulo,
                 v.empresa, v.url, json.dumps(v.portales), v.model_dump_json())
                for v in vacantes
            ],
        )
        self.con.commit()
```

(Mover el `import json` al tope del archivo si el linter lo prefiere; ya existe uno en `store.py`.)

- [ ] **Step 4: Correr y ver pasar (más toda la suite de store).**

Run: `.venv/bin/pytest tests/test_store.py -q`
Expected: PASS (incluidos los 2 nuevos).

- [ ] **Step 5: Lint + commit.**

```bash
.venv/bin/ruff check src tests
git add src/jobwatch/store.py tests/test_store.py
git commit -m "feat: user_version migration + persist portales column (D11/§6.3)"
```

---

### Task 7: Propagar `detalle` + nota "vista en N portales" al reporte

**Files:**
- Modify: `src/jobwatch/orquestador.py` (firma de `correr`, integrar colapso + resultados)
- Modify: `src/jobwatch/store.py` (`registrar_corrida` guarda `{portal:{estado,detalle}}`)
- Modify: `src/jobwatch/reporte.py` (`render` muestra `detalle` y "vista en N portales")
- Modify: `tests/test_reporte.py`, `tests/test_store.py`, `tests/test_orquestador.py`, `src/jobwatch/cli.py`

**Interfaces:**
- Cambia: `correr(...) -> tuple[str, dict[str, ResultadoConector]]` (antes `dict[str, EstadoConector]`).
- Cambia: `render(fecha, resultados: dict[str, ResultadoConector], ofertas)`.
- Cambia: `store.registrar_corrida(resultados: dict[str, ResultadoConector]) -> int` (guarda estado + detalle).

- [ ] **Step 1: Escribir/adaptar los tests.**

En `tests/test_reporte.py`, adaptar la llamada a `render` para pasar `ResultadoConector` y aserta que el `detalle` y la nota multi-portal aparecen. Añadir:

```python
from jobwatch.modelos import (
    EstadoConector, EstadoOferta, OfertaPuntuada, ResultadoConector, Vacante,
)
from jobwatch.reporte import render


def test_render_muestra_detalle_y_multiportal():
    v = Vacante(id_nativo="1", portal="computrabajo", titulo="Gerente", empresa="ACME",
                ubicacion="Bogotá", url="https://x/1", portales=["computrabajo", "magneto"])
    ofertas = [OfertaPuntuada(vacante=v, estado=EstadoOferta.PUNTUADA, puntaje=80, razon="ok")]
    resultados = {
        "computrabajo": ResultadoConector(estado=EstadoConector.OK, detalle="1 filas omitidas"),
        "indeed": ResultadoConector(estado=EstadoConector.ERROR, detalle="bloqueado: 403"),
    }
    md = render("2026-07-23", resultados, ofertas)
    assert "1 filas omitidas" in md
    assert "bloqueado: 403" in md
    assert "computrabajo, magneto" in md          # nota "vista en N portales"
```

En `tests/test_store.py`, adaptar el test de `registrar_corrida` para pasar `ResultadoConector` y leer el detalle:

```python
def test_registrar_corrida_guarda_estado_y_detalle(tmp_path):
    import json
    from jobwatch.modelos import EstadoConector, ResultadoConector
    store = Store(str(tmp_path / "j.db"))
    store.registrar_corrida({"indeed": ResultadoConector(estado=EstadoConector.ERROR, detalle="x")})
    fila = store.con.execute("SELECT estados FROM corridas").fetchone()
    datos = json.loads(fila[0])
    assert datos["indeed"] == {"estado": "error", "detalle": "x"}
    store.cerrar()
```

- [ ] **Step 2: Correr y ver fallar.**

Run: `.venv/bin/pytest tests/test_reporte.py tests/test_store.py -q`
Expected: FAIL (firmas viejas / claves nuevas ausentes).

- [ ] **Step 3: Actualizar `store.registrar_corrida`.**

```python
    def registrar_corrida(self, resultados: dict[str, "ResultadoConector"]) -> int:
        serializable = {
            portal: {"estado": r.estado.value, "detalle": r.detalle}
            for portal, r in resultados.items()
        }
        cur = self.con.execute(
            "INSERT INTO corridas (estados) VALUES (?)", (json.dumps(serializable),)
        )
        self.con.commit()
        return int(cur.lastrowid)
```

(Ajustar el import de tipo: `from jobwatch.modelos import EstadoConector, ResultadoConector, Vacante`.)

- [ ] **Step 4: Actualizar `reporte.render`.**

```python
from jobwatch.modelos import EstadoConector, EstadoOferta, OfertaPuntuada, ResultadoConector


def render(
    fecha: str,
    resultados: dict[str, ResultadoConector],
    ofertas: list[OfertaPuntuada],
) -> str:
    lineas = [f"# Vacantes nuevas — {fecha}", ""]

    lineas.append("## Estado de conectores")
    for portal, r in resultados.items():
        marca = "⚠️ ERROR" if r.estado is EstadoConector.ERROR else r.estado.value.upper()
        extra = f" — {r.detalle}" if r.detalle else ""
        lineas.append(f"- **{portal}**: {marca}{extra}")
    lineas.append("")

    lineas.append(f"## Ofertas ({len(ofertas)})")
    if not ofertas:
        lineas.append("_Sin ofertas nuevas en esta corrida._")
    for o in sorted(ofertas, key=_orden):
        v = o.vacante
        puntaje = o.puntaje if o.estado is EstadoOferta.PUNTUADA else "—"
        multi = ""
        if len(v.portales) > 1:
            multi = f"\n- Vista en {len(v.portales)} portales: {', '.join(v.portales)}"
        lineas.append(
            f"### [{v.titulo}]({v.url}) · {puntaje}\n"
            f"- Empresa: {v.empresa}\n"
            f"- Ubicación: {v.ubicacion}\n"
            f"- Motivo: {o.razon}{multi}\n"
        )
    return "\n".join(lineas)
```

- [ ] **Step 5: Actualizar `orquestador.correr` (colapso + resultados).**

```python
def correr(
    criterios: Criterios,
    cv: str,
    store: Store,
    puntuador,
    conectores: dict[str, Conector],
    fecha: str,
    tope: int = 50,
) -> tuple[str, dict[str, ResultadoConector]]:
    resultados: dict[str, ResultadoConector] = {}
    cosechadas: list[Vacante] = []
    for nombre, conector in conectores.items():
        r = conector(criterios)
        resultados[nombre] = r
        cosechadas.extend(r.vacantes)

    nuevas = [
        v for v in colapsar_lote(cosechadas)
        if store.es_nueva(v) and filtro_local(v, criterios)
    ]

    ofertas = puntuar(nuevas, cv, puntuador, tope=tope)
    store.persistir(nuevas)
    store.registrar_corrida(resultados)
    return render(fecha, resultados, ofertas), resultados
```

(Actualizar imports en `orquestador.py`: `from jobwatch.modelos import Criterios, PRIORIDAD_PORTAL, ResultadoConector, Vacante`. `EstadoConector` deja de usarse en el return; quitarlo si el linter avisa.)

- [ ] **Step 6: Adaptar `cli.py` (desempaque del return).**

En el bloque `run`, la línea de `correr` ya usa `md, _ = correr(...)`, que sigue siendo válida (el segundo elemento ahora es `dict[str, ResultadoConector]`). Verificar que no se referencie el tipo viejo en `cli.py`. (Sin cambio de código salvo que exista una anotación explícita.)

- [ ] **Step 7: Adaptar el test de orquestador existente.**

En `tests/test_orquestador.py`, si el test end-to-end existente afirma sobre `estados: dict[str, EstadoConector]`, actualizarlo para leer `resultados[nombre].estado`. Ejemplo del ajuste:

```python
    md, resultados = correr(criterios, cv, store, puntuador, conectores, "2026-07-23")
    assert resultados["indeed"].estado is EstadoConector.OK
```

- [ ] **Step 8: Correr TODA la suite.**

Run: `.venv/bin/pytest -q`
Expected: PASS (toda la suite verde, incluidos los tests nuevos y adaptados).

- [ ] **Step 9: Lint + commit.**

```bash
.venv/bin/ruff check src tests
git add src/jobwatch/orquestador.py src/jobwatch/store.py src/jobwatch/reporte.py tests/
git commit -m "feat: propagate connector detalle + 'vista en N portales' to report (D2/§6.2)"
```

---

### Task 8: Cablear los tres conectores en el CLI + verificación end-to-end

**Files:**
- Modify: `src/jobwatch/cli.py`
- Test: `tests/test_orquestador.py` (caso end-to-end multi-conector con fetch falso)

**Interfaces:**
- Consumes: los tres `buscar` + `indeed.buscar`.
- Produces: el `dict` de conectores del `run` incluye los cuatro portales, cada uno con su fetch real (curl_cffi) inyectado por defecto.

- [ ] **Step 1: Escribir el test end-to-end del colapso multi-conector.**

Añadir a `tests/test_orquestador.py` un caso donde dos conectores devuelven la MISMA oferta (mismo fingerprint) y el reporte la muestra una vez, marcada multi-portal:

```python
def test_correr_colapsa_entre_conectores(tmp_path):
    from jobwatch.modelos import Criterios, EstadoConector, ResultadoConector, Vacante
    from jobwatch.orquestador import correr
    from jobwatch.store import Store

    def _mk(portal):
        v = Vacante(id_nativo="1", portal=portal, titulo="Gerente de Proyectos",
                    empresa="ACME", ubicacion="Bogotá", url=f"https://{portal}/1")
        return lambda c: ResultadoConector(estado=EstadoConector.OK, vacantes=[v])

    store = Store(str(tmp_path / "j.db"))
    conectores = {"computrabajo": _mk("computrabajo"), "magneto": _mk("magneto")}
    md, resultados = correr(
        Criterios(terminos="gerente de proyectos"), "cv", store,
        lambda v, cv: {"puntaje": 70, "razon": "ok"}, conectores, "2026-07-23",
    )
    store.cerrar()
    # una sola oferta persistida (colapsada), y el reporte la marca multi-portal
    assert md.count("### [Gerente de Proyectos]") == 1
    assert "Vista en 2 portales: computrabajo, magneto" in md
```

- [ ] **Step 2: Correr y ver fallar/pasar.**

Run: `.venv/bin/pytest tests/test_orquestador.py -q -k "colapsa_entre"`
Expected: PASS si Task 5–7 están hechas (este test valida la integración; si falla, corregir el colapso/return antes de seguir).

- [ ] **Step 3: Cablear los conectores en `cli.py`.**

En el bloque `run` de `cli.py`, reemplazar el import y el `dict`:

```python
        from jobwatch.conectores import computrabajo, elempleo, indeed, magneto
```

```python
        conectores = {
            "computrabajo": computrabajo.buscar,
            "elempleo": elempleo.buscar,
            "magneto": magneto.buscar,
            "indeed": indeed.buscar,
        }
```

- [ ] **Step 4: Correr TODA la suite + lint.**

Run: `.venv/bin/pytest -q && .venv/bin/ruff check src tests`
Expected: PASS + sin hallazgos de lint.

- [ ] **Step 5: Commit.**

```bash
git add src/jobwatch/cli.py tests/test_orquestador.py
git commit -m "feat: wire Colombian connectors into CLI; end-to-end collapse test"
```

---

## Cierre del Plan A

Al terminar las 8 tareas: cuatro conectores (Indeed + los tres colombianos) emiten `Vacante` normalizado; el motor colapsa duplicados en-lote con "vista en N portales" persistido; el reporte muestra `detalle` por conector; la migración de schema es retrocompatible. El agregador multi-portal funciona por la ruta `run`/API-key. **Plan B** (core in-process, split harvest/report, skill, PyPI) parte de aquí.

**Nota abierta (D5, Magneto):** `?search=` no filtra el listado; el conector filtra client-side por término. Reconfirmar el parámetro de búsqueda correcto de Magneto en un probe dedicado antes de confiar en su cobertura.
