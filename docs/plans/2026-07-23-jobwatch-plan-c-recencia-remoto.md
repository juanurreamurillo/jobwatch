# Plan C — Modalidad remoto + recencia — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Que los conectores busquen por *cargo + modalidad remoto + publicadas en los últimos N días*, con cobertura completa por paginación y fecha best-effort.

**Architecture:** Los conectores HTTP quedan **agnósticos de fecha para filtrar**: cablean modalidad a la URL, paginan hasta agotar, pueblan `Vacante.fecha_publicacion` y devuelven `(vacantes, omitidas, n_crudo)`. La parada de paginación es por **tarjetas crudas** (`n_crudo`), no por vacantes filtradas. El filtro de recencia se **centraliza** en `cosechar` con `hoy` inyectado desde la fecha de corrida (semántica uniforme). Indeed pasa por JobSpy y por el mismo filtro central.

**Tech Stack:** Python 3.12, Pydantic, BeautifulSoup+lxml, curl_cffi, python-jobspy, pytest, ruff.

## Global Constraints

- Diseño de referencia: `docs/design-plan-c.md` (decisiones D16–D22). Descubrimiento y raw_signal: `docs/plan-c-descubrimiento.md`.
- `curl_cffi` con `impersonate="chrome124"` (constante `IMPERSONATE` en `_comun.py`). No añadir dependencias nuevas.
- **Repo público, nada personal.** Copy de cara al usuario en **español**. Nunca commitear `data/`, `reportes/`, `secrets/`, `*.db`, ni HTML crudo sin recortar.
- **Tests offline** contra fixtures recortados en `tests/conectores/fixtures/`. `fetch` se inyecta en `buscar(criterios, fetch=...)`; ningún test pega a la red.
- Fail-loud (D2): un conector roto/bloqueado devuelve `estado=ERROR`; una cobertura parcial se declara en `detalle`, nunca en silencio.
- Cada tarea termina con `.venv/bin/pytest -q` verde y `.venv/bin/ruff check src tests` limpio.
- Predicado de recencia (D16, corrige off-by-one): conservar oferta datable si `(hoy - fecha).days < dias`; conservar toda no-fechable; `dias=None` = sin filtro.

---

### Task 1: Parser de fecha relativa (`normalizar.parsear_fecha_relativa`)

**Files:**
- Modify: `src/jobwatch/normalizar.py`
- Test: `tests/test_normalizar.py`

**Interfaces:**
- Produces: `parsear_fecha_relativa(texto: str, hoy: datetime.date) -> datetime.date | None`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_normalizar.py  (añadir)
from datetime import date
from jobwatch.normalizar import parsear_fecha_relativa

HOY = date(2026, 7, 23)

def test_fecha_relativa_hoy_y_ayer():
    assert parsear_fecha_relativa("Hoy", HOY) == HOY
    assert parsear_fecha_relativa("Ayer", HOY) == date(2026, 7, 22)

def test_fecha_relativa_horas_es_hoy():
    assert parsear_fecha_relativa("Hace 3 horas", HOY) == HOY
    assert parsear_fecha_relativa("Hace  2  minutos", HOY) == HOY

def test_fecha_relativa_dias_semanas_meses():
    assert parsear_fecha_relativa("Hace 2 días", HOY) == date(2026, 7, 21)
    assert parsear_fecha_relativa("Hace 1 semana", HOY) == date(2026, 7, 16)
    assert parsear_fecha_relativa("Hace 3 semanas", HOY) == date(2026, 7, 2)
    assert parsear_fecha_relativa("Hace 1 mes", HOY) == date(2026, 6, 23)

def test_fecha_relativa_no_fechable_es_none():
    assert parsear_fecha_relativa("", HOY) is None
    assert parsear_fecha_relativa("Publicación reciente", HOY) is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/test_normalizar.py -k fecha_relativa -v`
Expected: FAIL con `ImportError` / `cannot import name 'parsear_fecha_relativa'`.

- [ ] **Step 3: Write minimal implementation**

```python
# src/jobwatch/normalizar.py  (añadir imports arriba)
from datetime import date, timedelta

# ... (al final del archivo)
_UNIDAD_DIAS = {"hora": 0, "minuto": 0, "segundo": 0, "dia": 1, "día": 1,
                "semana": 7, "mes": 30, "año": 365, "ano": 365}

def parsear_fecha_relativa(texto: str, hoy: date) -> date | None:
    """Best-effort (D19): 'Hoy'/'Ayer'/'Hace N horas|días|semanas|meses' -> date.
    No fechable -> None. `hoy` se inyecta (tests deterministas)."""
    t = texto.strip().lower()
    if not t:
        return None
    if t.startswith("hoy"):
        return hoy
    if t.startswith("ayer"):
        return hoy - timedelta(days=1)
    m = re.search(r"hace\s+(\d+)\s+(hora|minuto|segundo|d[ií]a|semana|mes|a[nñ]o)", t)
    if not m:
        return None
    n = int(m.group(1))
    unidad = m.group(2)
    factor = _UNIDAD_DIAS.get(unidad)
    if factor is None:
        return None
    return hoy - timedelta(days=n * factor)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/pytest tests/test_normalizar.py -k fecha_relativa -v`
Expected: PASS (4 tests).

- [ ] **Step 5: Commit**

```bash
git add src/jobwatch/normalizar.py tests/test_normalizar.py
git commit -m "feat: parsear_fecha_relativa (fecha best-effort, Plan C D19)"
```

---

### Task 2: Campo `Criterios.dias`

**Files:**
- Modify: `src/jobwatch/modelos.py:61-66` (clase `Criterios`)
- Test: `tests/test_modelos.py`

**Interfaces:**
- Produces: `Criterios(..., dias: int | None = None)`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_modelos.py  (añadir)
from jobwatch.modelos import Criterios

def test_criterios_dias_default_none():
    assert Criterios(terminos="x").dias is None

def test_criterios_dias_se_asigna():
    assert Criterios(terminos="x", dias=2).dias == 2
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/test_modelos.py -k dias -v`
Expected: FAIL con `AttributeError`/`ValidationError` (campo desconocido).

- [ ] **Step 3: Write minimal implementation**

```python
# src/jobwatch/modelos.py  (dentro de class Criterios)
class Criterios(BaseModel):
    terminos: str
    ubicacion: str | None = None
    modalidad: Modalidad | None = None
    salario_min: int | None = None
    excluir: list[str] = []
    dias: int | None = None
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/pytest tests/test_modelos.py -k dias -v`
Expected: PASS (2 tests).

- [ ] **Step 5: Commit**

```bash
git add src/jobwatch/modelos.py tests/test_modelos.py
git commit -m "feat: Criterios.dias (ventana de recencia, Plan C)"
```

---

### Task 3: Filtro de recencia central + cableado en `cosechar` (D22)

**Files:**
- Modify: `src/jobwatch/matcher.py`
- Modify: `src/jobwatch/nucleo.py:55-88` (`cosechar`)
- Test: `tests/test_matcher_filtro.py`, `tests/test_nucleo.py`

**Interfaces:**
- Produces: `matcher.filtro_recencia(v: Vacante, dias: int | None, hoy: date) -> bool`
- Consumes: `parsear_fecha_relativa` (no; el conector ya pobló `fecha_publicacion` ISO); `Vacante.fecha_publicacion: str | None`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_matcher_filtro.py  (añadir)
from datetime import date
from jobwatch.matcher import filtro_recencia
from jobwatch.modelos import Vacante

HOY = date(2026, 7, 23)

def _v(fecha):
    return Vacante(id_nativo="1", portal="x", titulo="t", empresa="e",
                   ubicacion="u", url="http://x", fecha_publicacion=fecha)

def test_recencia_none_no_filtra():
    assert filtro_recencia(_v("2020-01-01"), None, HOY) is True

def test_recencia_dias2_es_hoy_y_ayer():
    assert filtro_recencia(_v("2026-07-23"), 2, HOY) is True   # hoy
    assert filtro_recencia(_v("2026-07-22"), 2, HOY) is True   # ayer
    assert filtro_recencia(_v("2026-07-21"), 2, HOY) is False  # anteayer FUERA

def test_recencia_no_fechable_se_incluye():
    assert filtro_recencia(_v(None), 2, HOY) is True
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/test_matcher_filtro.py -k recencia -v`
Expected: FAIL con `ImportError` (`filtro_recencia`).

- [ ] **Step 3: Write minimal implementation**

```python
# src/jobwatch/matcher.py  (añadir imports + función)
from datetime import date

def filtro_recencia(v: Vacante, dias: int | None, hoy: date) -> bool:
    """Recorte de recencia central (D22). Conserva no-fechables (D19). `dias=None`
    = sin filtro. Predicado exacto (D16): datable pasa si (hoy - fecha).days < dias."""
    if dias is None:
        return True
    if not v.fecha_publicacion:
        return True  # no fechable -> incluir marcada (D19)
    try:
        f = date.fromisoformat(v.fecha_publicacion[:10])
    except ValueError:
        return True  # ilegible -> tratar como no fechable
    return (hoy - f).days < dias
```

```python
# src/jobwatch/nucleo.py
# 1) imports:
from datetime import date
from jobwatch.matcher import filtro_local, filtro_recencia
# 2) en cosechar, tras el bucle de conectores, cambiar el filtro:
    hoy = date.fromisoformat(fecha)
    nuevas = [
        v for v in colapsar_lote(cosechadas)
        if store.es_nueva(v)
        and filtro_local(v, criterios)
        and filtro_recencia(v, criterios.dias, hoy)
    ]
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/pytest tests/test_matcher_filtro.py tests/test_nucleo.py -q`
Expected: PASS (incluye los nuevos + los previos de nucleo sin romper).

- [ ] **Step 5: Commit**

```bash
git add src/jobwatch/matcher.py src/jobwatch/nucleo.py tests/test_matcher_filtro.py
git commit -m "feat: filtro_recencia central en cosechar con hoy inyectado (Plan C D22/D16)"
```

---

### Task 4: Contrato de paginación en `ejecutar` (`extraer -> (vacantes, omitidas, n_crudo)`)

**Files:**
- Modify: `src/jobwatch/conectores/_comun.py:44-54` (`ejecutar`)
- Test: `tests/conectores/test_comun.py`

**Interfaces:**
- Produces: `ejecutar(criterios, url_fn, fetch, extraer, max_paginas=50, pausa=None) -> ResultadoConector`
  - `url_fn: Callable[[Criterios, int], str]` (pagina 1-based)
  - `extraer: Callable[[str, Criterios], tuple[list[Vacante], int, int]]` (vacantes, omitidas, n_crudo)
- Consumes (por conectores): deben adaptar `_url(criterios, pagina)` y `_extraer -> (vacantes, omitidas, n_crudo)`.

- [ ] **Step 1: Write the failing test**

```python
# tests/conectores/test_comun.py  (añadir)
from jobwatch.conectores._comun import ejecutar
from jobwatch.modelos import Criterios, EstadoConector, Vacante

def _v(i):
    return Vacante(id_nativo=str(i), portal="x", titulo=f"t{i}", empresa="e",
                   ubicacion="u", url=f"http://x/{i}")

def test_ejecutar_pagina_hasta_pagina_vacia():
    paginas = {1: "p1", 2: "p2", 3: ""}  # p3 vacía = fin
    urls = []
    def url_fn(c, p): urls.append(p); return paginas.get(p, "")
    def extraer(html, c):
        if not html:
            return ([], 0, 0)           # n_crudo=0 -> parada
        n = 1 if html == "p1" else 1
        return ([_v(html)], 0, n)       # 1 tarjeta cruda
    r = ejecutar(Criterios(terminos="x"), url_fn, lambda u: u, extraer)
    assert r.estado is EstadoConector.OK
    assert [v.titulo for v in r.vacantes] == ["tp1", "tp2"]
    assert urls == [1, 2, 3]            # visitó hasta la vacía y paró

def test_ejecutar_para_por_crudo_no_por_filtrado():
    # página intermedia con tarjetas crudas pero 0 vacantes filtradas NO para
    def url_fn(c, p): return f"p{p}" if p <= 3 else ""
    def extraer(html, c):
        if html == "":       return ([], 0, 0)
        if html == "p2":     return ([], 0, 20)   # 20 crudas, 0 tras filtrar
        return ([_v(html)], 0, 20)
    r = ejecutar(Criterios(terminos="x"), url_fn, lambda u: u, extraer)
    assert [v.titulo for v in r.vacantes] == ["tp1", "tp3"]  # p2 no cortó

def test_ejecutar_tope_paginas_declara_parcial():
    def url_fn(c, p): return f"p{p}"        # nunca vacía
    def extraer(html, c): return ([_v(html)], 0, 20)
    r = ejecutar(Criterios(terminos="x"), url_fn, lambda u: u, extraer, max_paginas=3)
    assert r.estado is EstadoConector.OK
    assert "tope" in r.detalle.lower()      # cobertura parcial declarada (B2)

def test_ejecutar_error_en_pagina1_es_error():
    def url_fn(c, p): return f"p{p}"
    def boom(u): raise RuntimeError("bloqueado")
    r = ejecutar(Criterios(terminos="x"), url_fn, boom, lambda h, c: ([], 0, 0))
    assert r.estado is EstadoConector.ERROR

def test_ejecutar_error_tras_pagina1_es_parcial():
    def url_fn(c, p): return f"p{p}"
    def fetch(u):
        if u == "p2": raise RuntimeError("500")
        return u
    def extraer(html, c): return ([_v(html)], 0, 20)
    r = ejecutar(Criterios(terminos="x"), url_fn, fetch, extraer)
    assert r.estado is EstadoConector.OK
    assert [v.titulo for v in r.vacantes] == ["tp1"]
    assert "página 2" in r.detalle.lower() or "pagina 2" in r.detalle.lower()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/conectores/test_comun.py -k ejecutar -v`
Expected: FAIL (la firma vieja de `ejecutar` recibe `url_fn(criterios)` sin página y `extraer` devuelve 2-tupla).

- [ ] **Step 3: Write minimal implementation**

```python
# src/jobwatch/conectores/_comun.py  (reemplazar la función ejecutar)
def ejecutar(criterios, url_fn, fetch, extraer, max_paginas: int = 50, pausa=None):
    """Envoltorio fail-loud + paginación (D17). Recorre páginas por `_url(c, pagina)`
    hasta: página con 0 tarjetas crudas (fin normal), error tras la pág. 1 (fin +
    parcial), o tope de páginas (parcial). Error en pág. 1 = ERROR."""
    import time
    fetch = fetch or fetch_curl
    vacantes: list[Vacante] = []
    omitidas_total = 0
    for pagina in range(1, max_paginas + 1):
        try:
            html = fetch(url_fn(criterios, pagina))
            vs, omitidas, n_crudo = extraer(html, criterios)
        except Exception as e:  # fail-loud
            if pagina == 1:
                return ResultadoConector(estado=EstadoConector.ERROR, detalle=str(e))
            return ResultadoConector(
                estado=EstadoConector.OK, vacantes=vacantes,
                detalle=f"cobertura parcial: fin en página {pagina} por error: {e}",
            )
        if n_crudo == 0:  # página vacía = agotado real
            det = f"{omitidas_total} filas omitidas por datos inválidos" if omitidas_total else ""
            return ResultadoConector(estado=EstadoConector.OK, vacantes=vacantes, detalle=det)
        vacantes.extend(vs)
        omitidas_total += omitidas
        if pausa:
            time.sleep(pausa)
    return ResultadoConector(
        estado=EstadoConector.OK, vacantes=vacantes,
        detalle=f"cobertura parcial: tope de {max_paginas} páginas alcanzado",
    )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/pytest tests/conectores/test_comun.py -k ejecutar -v`
Expected: PASS (5 tests). Los tests de conectores existentes fallarán hasta las Tasks 5–7 (contrato nuevo) — es esperado; se arreglan por conector.

- [ ] **Step 5: Commit**

```bash
git add src/jobwatch/conectores/_comun.py tests/conectores/test_comun.py
git commit -m "feat: paginación fail-loud en ejecutar; extraer devuelve n_crudo (Plan C D17/B1/B2)"
```

---

### Task 5: Computrabajo — remoto + pubdate + paginación + fecha

**Files:**
- Modify: `src/jobwatch/conectores/computrabajo.py`
- Test: `tests/conectores/test_computrabajo.py`
- Fixture: `tests/conectores/fixtures/computrabajo.html` (ya existe; verificar que tiene `p.fs13.fc_aux` con fecha relativa — si no, recapturar recortado)

**Interfaces:**
- Produces: `_url(criterios: Criterios, pagina: int) -> str`; `_extraer(html, criterios) -> (list[Vacante], int, int)`
- Consumes: `ejecutar` (Task 4), `parsear_fecha_relativa` (Task 1).

- [ ] **Step 1: Write the failing test**

```python
# tests/conectores/test_computrabajo.py  (añadir)
from jobwatch.conectores.computrabajo import _url
from jobwatch.modelos import Criterios, Modalidad

def test_url_remoto_pubdate_paginado():
    c = Criterios(terminos="gerente de proyectos", modalidad=Modalidad.REMOTO, dias=2)
    u = _url(c, 2)
    assert "/trabajo-de-gerente-de-proyectos-en-remoto" in u
    assert "pubdate=3" in u          # menor de {1,3,7,15} >= 2
    assert "by=publicationtime" in u
    assert "p=2" in u

def test_url_sin_modalidad_ni_dias():
    u = _url(Criterios(terminos="gerente"), 1)
    assert u.endswith("/trabajo-de-gerente")   # sin -en-remoto, sin params, p=1 implícito/omitido
```

(Añadir también un test de `_extraer` sobre la fixture que verifique que `fecha_publicacion` se puebla y que devuelve la 3-tupla. Ejemplo:)

```python
from jobwatch.conectores.computrabajo import _extraer
from datetime import date

def test_extraer_puebla_fecha_y_ncrudo():
    html = open("tests/conectores/fixtures/computrabajo.html", encoding="utf-8").read()
    vacantes, omitidas, n_crudo = _extraer(html, Criterios(terminos="gerente"))
    assert n_crudo >= 1
    assert len(vacantes) >= 1
    # al menos una con fecha ISO poblada (parseada del texto relativo)
    assert any(v.fecha_publicacion and len(v.fecha_publicacion) == 10 for v in vacantes)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/conectores/test_computrabajo.py -v`
Expected: FAIL (`_url` no acepta `pagina`; `_extraer` devuelve 2-tupla; fecha no poblada).

- [ ] **Step 3: Write minimal implementation**

```python
# src/jobwatch/conectores/computrabajo.py  (reemplazar _url, _a_vacante, _extraer, buscar)
from datetime import date
from jobwatch.conectores._comun import ejecutar, slug, texto
from jobwatch.modelos import Criterios, Modalidad, ResultadoConector, Vacante
from jobwatch.normalizar import normalizar_ubicacion, parsear_salario, parsear_fecha_relativa

_PUBDATE = [1, 3, 7, 15]  # ventanas server discretas (descubrimiento)

def _pubdate_para(dias: int | None) -> int | None:
    if dias is None:
        return None
    for v in _PUBDATE:
        if v >= dias:
            return v
    return _PUBDATE[-1]

def _url(criterios: Criterios, pagina: int = 1) -> str:
    ruta = f"/trabajo-de-{slug(criterios.terminos)}"
    if criterios.modalidad is Modalidad.REMOTO:
        ruta += "-en-remoto"
    params = []
    pd = _pubdate_para(criterios.dias)
    if pd is not None:
        params += [f"pubdate={pd}", "by=publicationtime"]
    if pagina > 1:
        params.append(f"p={pagina}")
    qs = ("?" + "&".join(params)) if params else ""
    return f"{HOST}{ruta}{qs}"

def _a_vacante(art) -> Vacante:
    a = art.select_one("h2 a.js-o-link")
    href = a.get("href", "").split("#")[0] if a else ""
    empresa = art.select_one("a[offer-grid-article-company-url]")
    ubic = art.select_one("p.fs16.fc_base.mt5:not(.dFlex) > span.mr10")
    salario_raw = ""
    if art.select_one("span.i_salary"):
        salario_raw = texto(art.select_one("div.fs13.mt15 span.dIB.mr10"))
    smin, smax = parsear_salario(salario_raw) if salario_raw else (None, None)
    fecha_el = art.select_one("p.fs13.fc_aux")
    f = parsear_fecha_relativa(texto(fecha_el), date.today()) if fecha_el else None
    modalidad = Modalidad.REMOTO if "-en-remoto" in href or "remoto" in texto(art).lower() else Modalidad.DESCONOCIDO
    return Vacante(
        id_nativo=art.get("data-id", ""), portal="computrabajo",
        titulo=texto(a), empresa=texto(empresa),
        ubicacion=normalizar_ubicacion(texto(ubic)),
        modalidad=modalidad,
        salario_raw=salario_raw, salario_min=smin, salario_max=smax,
        url=urljoin(HOST, href),
        fecha_publicacion=f.isoformat() if f else None,
    )

def _extraer(html: str, criterios: Criterios) -> tuple[list[Vacante], int, int]:
    sopa = BeautifulSoup(html, "lxml")
    arts = sopa.select("article.box_offer")
    vacantes: list[Vacante] = []
    omitidas = 0
    for art in arts:
        try:
            v = _a_vacante(art)
            if not v.id_nativo or not v.titulo:
                omitidas += 1; continue
            vacantes.append(v)
        except Exception:
            omitidas += 1
    return vacantes, omitidas, len(arts)  # n_crudo = tarjetas crudas

def buscar(criterios: Criterios, fetch=None) -> ResultadoConector:
    return ejecutar(criterios, _url, fetch, _extraer, pausa=1.0)
```

> Nota: `date.today()` aquí es aceptable porque la fecha se **re-filtra** exacto en el core (D22) con `hoy` inyectado; el valor del conector solo puebla el ISO. Los tests de `_extraer` que dependan de la fecha exacta deben tolerar el día real o mockear `date`. Preferir aserciones de forma (`len==10`), no de valor.

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/pytest tests/conectores/test_computrabajo.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/jobwatch/conectores/computrabajo.py tests/conectores/test_computrabajo.py
git commit -m "feat: computrabajo remoto+pubdate+paginación+fecha (Plan C)"
```

---

### Task 6: elempleo — modalidad-remoto + PublishDate + paginación /{N} + fecha

**Files:**
- Modify: `src/jobwatch/conectores/elempleo.py`
- Test: `tests/conectores/test_elempleo.py`
- Fixture: `tests/conectores/fixtures/elempleo.html` (verificar que tiene `span.info-publish-date`; recapturar recortado si no)

**Interfaces:**
- Produces: `_url(criterios, pagina) -> str`; `_extraer(html, criterios) -> (list[Vacante], int, int)`

- [ ] **Step 1: Write the failing test**

```python
# tests/conectores/test_elempleo.py  (añadir)
from jobwatch.conectores.elempleo import _url
from jobwatch.modelos import Criterios, Modalidad

def test_url_modalidad_remoto_publishdate_y_pagina():
    c = Criterios(terminos="gerente de proyectos", modalidad=Modalidad.REMOTO, dias=2)
    assert _url(c, 1).endswith("trabajo-gerente-de-proyectos-modalidad-remoto?PublishDate=hoy")
    assert _url(c, 3).endswith("trabajo-gerente-de-proyectos-modalidad-remoto/3?PublishDate=hoy")

def test_url_sin_modalidad_ni_dias():
    assert _url(Criterios(terminos="gerente"), 1).endswith("/co/ofertas-empleo/trabajo-gerente")
```

(Y un test de `_extraer` que verifique 3-tupla + fecha poblada desde `span.info-publish-date`.)

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/conectores/test_elempleo.py -v`
Expected: FAIL (`_url` sin `pagina`, `_extraer` 2-tupla, sin fecha).

- [ ] **Step 3: Write minimal implementation**

```python
# src/jobwatch/conectores/elempleo.py  (reemplazar _url, _extraer, buscar; añadir fecha por card)
from datetime import date
from jobwatch.modelos import Criterios, Modalidad, ResultadoConector, Vacante
from jobwatch.normalizar import normalizar_ubicacion, parsear_salario, parsear_fecha_relativa

def _url(criterios: Criterios, pagina: int = 1) -> str:
    ruta = f"/co/ofertas-empleo/trabajo-{slug(criterios.terminos)}"
    if criterios.modalidad is Modalidad.REMOTO:
        ruta += "-modalidad-remoto"
    if pagina > 1:
        ruta += f"/{pagina}"
    qs = "?PublishDate=hoy" if (criterios.dias is not None and criterios.dias <= 2) else ""
    return f"{HOST}{ruta}{qs}"

def _fechas_por_id(sopa) -> dict[str, str]:
    """id -> texto de fecha relativa (span.info-publish-date dentro del card)."""
    porid: dict[str, str] = {}
    for card in sopa.select("[data-ga4-offerdata]"):
        try:
            oid = str(json.loads(card["data-ga4-offerdata"])["id"])
        except Exception:
            continue
        span = card.select_one(".info-publish-date") or card.find_parent().select_one(".info-publish-date") if card.find_parent() else None
        if span:
            porid[oid] = " ".join(span.get_text().split())
    return porid

def _extraer(html: str, criterios: Criterios) -> tuple[list[Vacante], int, int]:
    sopa = BeautifulSoup(html, "lxml")
    cards = _cards_por_id(sopa)
    fechas = _fechas_por_id(sopa)
    items = _items_jsonld(sopa)
    vacantes: list[Vacante] = []
    omitidas = 0
    for it in items:
        card = cards.get(it["id"])
        if not it["id"] or card is None:
            omitidas += 1; continue
        try:
            salario_raw = str(card.get("salary", "") or "")
            smin, smax = parsear_salario(salario_raw)
            f = parsear_fecha_relativa(fechas.get(it["id"], ""), date.today())
            vacantes.append(Vacante(
                id_nativo=it["id"], portal="elempleo",
                titulo=str(card.get("title") or it["name"]),
                empresa=str(card.get("company", "")),
                ubicacion=normalizar_ubicacion(str(card.get("location", ""))),
                modalidad=Modalidad.REMOTO if criterios.modalidad is Modalidad.REMOTO else Modalidad.DESCONOCIDO,
                salario_raw=salario_raw, salario_min=smin, salario_max=smax,
                url=it["url"], fecha_publicacion=f.isoformat() if f else None,
            ))
        except Exception:
            omitidas += 1
    return vacantes, omitidas, len(items)  # n_crudo = items del ItemList

def buscar(criterios: Criterios, fetch=None) -> ResultadoConector:
    return ejecutar(criterios, _url, fetch, _extraer, pausa=1.0)
```

> Nota sobre la asociación fecha↔card: verificar contra la fixture la posición real del `span.info-publish-date` respecto del `[data-ga4-offerdata]` (hermano, hijo o ancestro común). Ajustar el selector de `_fechas_por_id` a lo que muestre la fixture; el test de `_extraer` lo valida.

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/pytest tests/conectores/test_elempleo.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/jobwatch/conectores/elempleo.py tests/conectores/test_elempleo.py
git commit -m "feat: elempleo modalidad-remoto+PublishDate+paginación+fecha (Plan C)"
```

---

### Task 7: Magneto — ruta de término /pagina-N + parser del flight RSC

**Files:**
- Modify: `src/jobwatch/conectores/magneto.py`
- Test: `tests/conectores/test_magneto.py`
- Fixture: `tests/conectores/fixtures/magneto-flight.html` (NUEVO; capturar recortado, ver Step 0)

**Interfaces:**
- Produces: `_url(criterios, pagina) -> str`; `_reconstruir_flight(html) -> str`; `_rows_del_flight(html) -> list[dict]`; `_extraer(html, criterios) -> (list[Vacante], int, int)`

- [ ] **Step 0: Capturar la fixture recortada (una vez)**

```bash
.venv/bin/python - <<'PY'
from curl_cffi import requests
import re
h = requests.get("https://www.magneto365.com/co/trabajos/buscar/gerente-de-proyectos",
                 impersonate="chrome124", timeout=30).text
# Conservar solo los <script>self.__next_f.push(...) (donde vive el flight) + un <html> mínimo
scripts = re.findall(r'<script>self\.__next_f\.push\(\[1,(?:"(?:[^"\\]|\\.)*")\]\)</script>', h)
open("tests/conectores/fixtures/magneto-flight.html","w",encoding="utf-8").write(
    "<!doctype html><html><body>" + "".join(scripts) + "</body></html>")
print("fixture escrita, scripts:", len(scripts))
PY
```

- [ ] **Step 1: Write the failing test**

```python
# tests/conectores/test_magneto.py  (reemplazar/añadir)
from jobwatch.conectores.magneto import _url, _rows_del_flight, _extraer
from jobwatch.modelos import Criterios, Modalidad

FIX = "tests/conectores/fixtures/magneto-flight.html"

def test_url_ruta_termino_pagina():
    c = Criterios(terminos="gerente de proyectos", modalidad=Modalidad.REMOTO)
    assert _url(c, 1).endswith("/co/trabajos/buscar/gerente-de-proyectos")
    assert _url(c, 3).endswith("/co/trabajos/buscar/gerente-de-proyectos/pagina-3")

def test_rows_del_flight_extrae_vacantes():
    html = open(FIX, encoding="utf-8").read()
    rows = _rows_del_flight(html)
    assert len(rows) >= 1
    r0 = rows[0]
    assert "publishDate" in r0 and "id" in r0 and "title" in r0

def test_extraer_filtra_remoto_y_puebla_fecha_iso():
    html = open(FIX, encoding="utf-8").read()
    c = Criterios(terminos="gerente de proyectos", modalidad=Modalidad.REMOTO)
    vacantes, omitidas, n_crudo = _extraer(html, c)
    assert n_crudo >= 1                         # tarjetas crudas del flight
    assert all(v.modalidad is Modalidad.REMOTO for v in vacantes)   # solo remotas
    assert all(v.fecha_publicacion and v.fecha_publicacion[:2] == "20" for v in vacantes)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/conectores/test_magneto.py -v`
Expected: FAIL (`_url` sin `pagina`, `_rows_del_flight` inexistente).

- [ ] **Step 3: Write minimal implementation**

```python
# src/jobwatch/conectores/magneto.py  (reemplazar el módulo)
from __future__ import annotations
import json
import re
from datetime import date
from jobwatch.conectores._comun import ejecutar, slug
from jobwatch.modelos import Criterios, Modalidad, ResultadoConector, Vacante
from jobwatch.normalizar import normalizar_ubicacion

HOST = "https://www.magneto365.com"

def _url(criterios: Criterios, pagina: int = 1) -> str:
    ruta = f"/co/trabajos/buscar/{slug(criterios.terminos)}"
    if pagina > 1:
        ruta += f"/pagina-{pagina}"
    return f"{HOST}{ruta}"

def _reconstruir_flight(html: str) -> str:
    """Concatena los payloads de self.__next_f.push([1,"..."]) decodificando cada
    uno como literal JSON (preserva UTF-8 y \\uXXXX; no rompe multibyte)."""
    trozos = re.findall(r'self\.__next_f\.push\(\[1,("(?:[^"\\]|\\.)*")\]\)', html)
    return "".join(json.loads(t) for t in trozos)

def _rows_del_flight(html: str) -> list[dict]:
    """Aísla el array `"rows":[...]` de vacantes del flight y lo parsea con
    raw_decode. Se queda con el array cuyos objetos traen publishDate."""
    flight = _reconstruir_flight(html)
    dec = json.JSONDecoder()
    idx = 0
    while (j := flight.find('"rows":', idx)) != -1:
        b = flight.find("[", j)
        try:
            arr, end = dec.raw_decode(flight, b)
            idx = end
        except json.JSONDecodeError:
            idx = j + 7
            continue
        if isinstance(arr, list) and any(isinstance(x, dict) and "publishDate" in x for x in arr):
            return [x for x in arr if isinstance(x, dict) and "id" in x]
    return []

def _a_vacante(row: dict) -> Vacante:
    cities = row.get("cities") or []
    pub = str(row.get("publishDate") or "")
    fecha = pub[:10] if pub[:2] == "20" else None
    return Vacante(
        id_nativo=str(row.get("id", "")), portal="magneto",
        titulo=str(row.get("title", "")),
        empresa=str(row.get("companyName", "")),
        ubicacion=normalizar_ubicacion(str(cities[0]) if cities else ""),
        modalidad=Modalidad.REMOTO if row.get("isRemote") else Modalidad.DESCONOCIDO,
        salario_raw=str(row.get("salary", "") or ""),
        salario_min=row.get("minSalary"), salario_max=row.get("maxSalary"),
        url=f"{HOST}/co/empleos/{row.get('jobSlug', '')}",
        fecha_publicacion=fecha,
    )

def _extraer(html: str, criterios: Criterios) -> tuple[list[Vacante], int, int]:
    rows = _rows_del_flight(html)
    vacantes: list[Vacante] = []
    omitidas = 0
    for row in rows:
        try:
            v = _a_vacante(row)
            if not v.id_nativo or not v.titulo:
                omitidas += 1; continue
            if criterios.modalidad is Modalidad.REMOTO and v.modalidad is not Modalidad.REMOTO:
                continue  # filtro remoto local (server no lo hace en la ruta de término)
            vacantes.append(v)
        except Exception:
            omitidas += 1
    return vacantes, omitidas, len(rows)  # n_crudo = filas crudas del flight

def buscar(criterios: Criterios, fetch=None) -> ResultadoConector:
    return ejecutar(criterios, _url, fetch, _extraer, pausa=1.5)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/pytest tests/conectores/test_magneto.py -q`
Expected: PASS. (Borrar del test viejo las aserciones basadas en `<article>`/`?search=`.)

- [ ] **Step 5: Commit**

```bash
git add src/jobwatch/conectores/magneto.py tests/conectores/test_magneto.py tests/conectores/fixtures/magneto-flight.html
git commit -m "feat: magneto por ruta de término /pagina-N + parser del flight RSC (Plan C D18)"
```

---

### Task 8: Indeed — is_remote + hours_old vía JobSpy + fecha

**Files:**
- Modify: `src/jobwatch/conectores/indeed.py`
- Test: `tests/conectores/test_indeed.py`

**Interfaces:**
- Consumes: `Criterios.modalidad`, `Criterios.dias`. `indeed.buscar(criterios, scrape=None)` (inyección de `scrape` ya existe). JobSpy `scrape_jobs(is_remote=..., hours_old=...)` (verificado: acepta ambos).

- [ ] **Step 1: Write the failing test**

```python
# tests/conectores/test_indeed.py  (añadir; se inyecta `scrape`, sin red ni pandas)
from jobwatch.modelos import Criterios, Modalidad
from jobwatch.conectores import indeed

class _FakeDF:
    def __init__(self, filas): self._filas = filas
    def to_dict(self, orient): return self._filas

def test_indeed_pasa_is_remote_y_hours_old():
    capturado = {}
    def fake_scrape(**kw):
        capturado.update(kw)
        return _FakeDF([])
    indeed.buscar(Criterios(terminos="gerente", modalidad=Modalidad.REMOTO, dias=2),
                  scrape=fake_scrape)
    assert capturado.get("is_remote") is True
    assert capturado.get("hours_old") == 48    # 24 * dias

def test_indeed_sin_dias_no_manda_hours_old():
    capturado = {}
    def fake_scrape(**kw):
        capturado.update(kw); return _FakeDF([])
    indeed.buscar(Criterios(terminos="gerente"), scrape=fake_scrape)
    assert capturado.get("hours_old") is None
    assert capturado.get("is_remote") is False

def test_indeed_puebla_fecha_desde_date_posted():
    fila = {"id": "1", "title": "t", "company": "e", "location": "Bogotá",
            "job_url": "http://x/1", "date_posted": "2026-07-21", "is_remote": True}
    r = indeed.buscar(Criterios(terminos="x"), scrape=lambda **kw: _FakeDF([fila]))
    assert r.vacantes[0].fecha_publicacion == "2026-07-21"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/conectores/test_indeed.py -k "is_remote or hours_old or date_posted" -v`
Expected: FAIL (indeed.buscar no pasa esos params).

- [ ] **Step 3: Write minimal implementation**

```python
# src/jobwatch/conectores/indeed.py  (dentro de buscar, en la llamada scrape(...))
        df = scrape(
            site_name=["indeed"],
            search_term=criterios.terminos,
            location=criterios.ubicacion or "Colombia",
            country_indeed="colombia",
            is_remote=criterios.modalidad is Modalidad.REMOTO,
            hours_old=24 * criterios.dias if criterios.dias else None,
        )
```

```python
# src/jobwatch/conectores/indeed.py  (en _a_vacante, normalizar date_posted con _sin_nan)
        fecha_publicacion=(
            str(_sin_nan(fila.get("date_posted")))[:10]
            if _sin_nan(fila.get("date_posted")) else None
        ),
```

> El filtro de recencia exacto (calendario) lo aplica el core (D22); `hours_old` es
> solo reductor de volumen (ventana rodante, D21). No se filtra fecha aquí.

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/pytest tests/conectores/test_indeed.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/jobwatch/conectores/indeed.py tests/conectores/test_indeed.py
git commit -m "feat: indeed is_remote+hours_old+fecha vía JobSpy (Plan C D21)"
```

---

### Task 9: Reporte "fecha desconocida" + config `dias` + verificación integral

**Files:**
- Modify: `src/jobwatch/reporte.py:34-39` (bloque de cada oferta)
- Test: `tests/test_config.py`, `tests/test_reporte.py`
- Modify (bundle skill): `skill/jobwatch.config.example.json` — añadir `"dias"` de ejemplo

**Interfaces:**
- Consumes: `Criterios.dias` (deserializado por `cargar_criterios` sin cambios — `model_validate_json` ya toma el campo nuevo); `Vacante.fecha_publicacion`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_config.py (añadir) — verifica que dias se deserializa (sin cambiar config.py)
def test_config_carga_dias(tmp_path):
    import json
    from jobwatch.config import cargar_criterios
    p = tmp_path / "c.json"
    p.write_text(json.dumps({"terminos": "x", "dias": 2}), encoding="utf-8")
    assert cargar_criterios(str(p)).dias == 2

# tests/test_reporte.py (añadir)
def test_reporte_marca_fecha_desconocida():
    from jobwatch.reporte import render
    from jobwatch.modelos import (
        EstadoOferta, OfertaPuntuada, Vacante,
    )
    v = Vacante(id_nativo="1", portal="x", titulo="T", empresa="E", ubicacion="U",
                url="http://x", fecha_publicacion=None)
    o = OfertaPuntuada(vacante=v, estado=EstadoOferta.PUNTUADA, puntaje=80, razon="ok")
    md = render("2026-07-23", {}, [o])
    assert "fecha desconocida" in md

def test_reporte_muestra_fecha_cuando_existe():
    from jobwatch.reporte import render
    from jobwatch.modelos import EstadoOferta, OfertaPuntuada, Vacante
    v = Vacante(id_nativo="1", portal="x", titulo="T", empresa="E", ubicacion="U",
                url="http://x", fecha_publicacion="2026-07-22")
    o = OfertaPuntuada(vacante=v, estado=EstadoOferta.PUNTUADA, puntaje=80, razon="ok")
    assert "2026-07-22" in render("2026-07-23", {}, [o])
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/test_config.py tests/test_reporte.py -k "dias or fecha" -v`
Expected: `test_config_carga_dias` PASA ya (dias es campo); los de reporte FALLAN (falta la línea de fecha).

- [ ] **Step 3: Write minimal implementation**

```python
# src/jobwatch/reporte.py  (en render, dentro del for de ofertas, ampliar el bloque)
    for o in sorted(ofertas, key=_orden):
        v = o.vacante
        puntaje = o.puntaje if o.estado is EstadoOferta.PUNTUADA else "—"
        fecha_txt = v.fecha_publicacion or "fecha desconocida"
        multi = ""
        if len(v.portales) > 1:
            multi = f"\n- Vista en {len(v.portales)} portales: {', '.join(v.portales)}"
        lineas.append(
            f"### [{v.titulo}]({v.url}) · {puntaje}\n"
            f"- Empresa: {v.empresa}\n"
            f"- Ubicación: {v.ubicacion}\n"
            f"- Publicada: {fecha_txt}\n"
            f"- Motivo: {o.razon}{multi}\n"
        )
```

Añadir `"dias": 2` al `skill/jobwatch.config.example.json` (junto a `terminos`/`modalidad`), como ejemplo de "ayer y hoy".

- [ ] **Step 4: Verificación integral (offline) + lint**

Run: `.venv/bin/pytest -q && .venv/bin/ruff check src tests`
Expected: TODO verde, ruff limpio.

- [ ] **Step 5: Commit**

```bash
git add -A
git commit -m "feat: config.dias + reporte 'fecha desconocida' (Plan C D19)"
```

---

## Verificación end-to-end opcional (manual, con red — NO en CI)

```bash
ANTHROPIC_API_KEY=… .venv/bin/jobwatch run \
  --terminos "Gerente de Proyectos TI" --ubicacion "Colombia" \
  --modalidad remoto --dias 2 --cv data/cv.txt
```
Esperado: los cuatro conectores corren; el reporte trae solo remotas de la ventana, con "fecha desconocida" donde aplique, y `detalle` de cobertura parcial si algún portal cortó.
