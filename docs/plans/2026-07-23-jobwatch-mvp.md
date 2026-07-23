# jobwatch MVP — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the codeable, testable core of jobwatch — models, normalization, SQLite store with two-level dedup, hybrid matcher, the Indeed connector (the only one that does not depend on Phase 0), report renderer, and CLI — leaving the Computrabajo/elempleo/Magneto connectors for a later plan once Phase 0 has discovered their real endpoints.

**Architecture:** A four-stage pipeline (connectors → hybrid matcher → SQLite store → Markdown report). Every connector returns a `ResultadoConector` with an explicit `estado` (fail-loud). Normalization lives inside connectors, producing a Pydantic `Vacante` whose `id_estable` and `fingerprint_contenido` are computed automatically. The LLM (scoring, letters) and JobSpy (Indeed) are injected as callables so every unit is testable offline with fakes.

**Tech Stack:** Python ≥3.10, `pydantic` v2, `curl_cffi`, `extruct`, `python-jobspy`, stdlib `sqlite3`/`argparse`/`hashlib`, `pytest`.

## Global Constraints

- Python ≥ 3.10 (`pyproject.toml`, `requires-python`).
- Dependencies (floors, verbatim): `curl_cffi>=0.7`, `extruct>=0.16`, `pydantic>=2.0`, `python-jobspy>=1.1`. Dev: `pytest>=8.0`, `ruff>=0.5`.
- Package layout: `src/jobwatch/…`, tests in `tests/…`, `ruff` line-length 100, target `py310`.
- **User-facing copy is Spanish** (report text, CLI help, error messages). Code identifiers follow the design's Spanish domain names (`Vacante`, `buscar`, `estado`, etc.).
- **Fail-loud everywhere:** connectors and the LLM step return an explicit state; a failure is never silently an empty result.
- **Never** read or write anything under `secrets/`, `data/`, `reportes/`, or `*.db` into git (already in `.gitignore`).
- No network or real-LLM calls in tests — inject fakes.
- TDD: failing test first, minimal implementation, frequent commits.

---

## File structure

| File | Responsibility |
|---|---|
| `src/jobwatch/modelos.py` | Enums (`Modalidad`, `EstadoConector`, `EstadoOferta`), `Criterios`, `Vacante` (auto-computes `id_estable` + `fingerprint_contenido`), `OfertaPuntuada`, `ResultadoConector`. |
| `src/jobwatch/normalizar.py` | Pure text/domain normalizers: `normalizar_texto`, `normalizar_ubicacion`, `normalizar_modalidad`, `parsear_salario`. |
| `src/jobwatch/store.py` | SQLite schema init, `es_nueva` (two-level dedup), `persistir`, `registrar_corrida`. |
| `src/jobwatch/matcher.py` | `filtro_local` (cheap deterministic), `puntuar` (LLM with per-run cap, fail-loud, per-offer state). |
| `src/jobwatch/conectores/base.py` | `Conector` protocol + shared re-exports. |
| `src/jobwatch/conectores/indeed.py` | JobSpy → `Vacante` adapter, own failure detection. |
| `src/jobwatch/reporte.py` | Render the run into Markdown (new offers + per-connector status). |
| `src/jobwatch/cartas.py` | On-demand cover-letter generation (LLM injected). |
| `src/jobwatch/cli.py` | `argparse` entry: `run`, `carta`. |
| `tests/…` | One test module per source module. |

---

### Task 1: Core models (`modelos.py`)

**Files:**
- Create: `src/jobwatch/modelos.py`
- Test: `tests/test_modelos.py`

**Interfaces:**
- Consumes: nothing.
- Produces:
  - `class Modalidad(str, Enum)`: `REMOTO="remoto"`, `HIBRIDO="hibrido"`, `PRESENCIAL="presencial"`, `DESCONOCIDO="desconocido"`.
  - `class EstadoConector(str, Enum)`: `OK="ok"`, `ERROR="error"`, `SESION_EXPIRADA="sesion_expirada"`.
  - `class EstadoOferta(str, Enum)`: `PUNTUADA="puntuada"`, `SIN_PUNTAJE="sin_puntaje"`, `ERROR="error"`.
  - `class Criterios(BaseModel)`: `terminos: str`, `ubicacion: str | None = None`, `modalidad: Modalidad | None = None`, `salario_min: int | None = None`, `excluir: list[str] = []`.
  - `class Vacante(BaseModel)`: fields `id_nativo: str`, `portal: str`, `titulo: str`, `empresa: str`, `ubicacion: str`, `modalidad: Modalidad = Modalidad.DESCONOCIDO`, `salario_raw: str = ""`, `salario_min: int | None = None`, `salario_max: int | None = None`, `url: str`, `fecha_publicacion: str | None = None`, `descripcion_raw: str = ""`, plus computed `id_estable: str` and `fingerprint_contenido: str`.
  - `calcular_id_estable(portal: str, id_nativo: str) -> str`
  - `calcular_fingerprint(empresa: str, titulo: str, ubicacion: str) -> str`
  - `class OfertaPuntuada(BaseModel)`: `vacante: Vacante`, `estado: EstadoOferta`, `puntaje: int | None = None`, `razon: str = ""`.
  - `class ResultadoConector(BaseModel)`: `estado: EstadoConector`, `vacantes: list[Vacante] = []`, `detalle: str = ""`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_modelos.py
from jobwatch.modelos import (
    Vacante, Modalidad, EstadoConector, ResultadoConector,
    calcular_id_estable, calcular_fingerprint,
)


def _vacante(**over):
    base = dict(
        id_nativo="123", portal="indeed", titulo="Gerente de Proyectos TI",
        empresa="ACME S.A.S.", ubicacion="Bogotá D.C.", url="https://x/123",
    )
    base.update(over)
    return Vacante(**base)


def test_id_estable_es_estable_y_depende_de_portal_e_id():
    v = _vacante()
    assert v.id_estable == calcular_id_estable("indeed", "123")
    # mismo id nativo, distinto portal -> distinto id_estable
    assert _vacante(portal="magneto").id_estable != v.id_estable
    # mismo portal+id, distinta URL -> MISMO id_estable (D3)
    assert _vacante(url="https://x/123?utm=abc").id_estable == v.id_estable


def test_fingerprint_ignora_variaciones_menores():
    a = _vacante(empresa="ACME S.A.S.", titulo="Gerente de Proyectos TI", ubicacion="Bogotá D.C.")
    b = _vacante(id_nativo="999", empresa="acme sas", titulo="gerente de proyectos ti", ubicacion="bogota")
    assert a.fingerprint_contenido == b.fingerprint_contenido == calcular_fingerprint(
        "ACME S.A.S.", "Gerente de Proyectos TI", "Bogotá D.C."
    )


def test_resultado_conector_por_defecto_ok_vacio():
    r = ResultadoConector(estado=EstadoConector.OK)
    assert r.vacantes == [] and r.detalle == ""


def test_modalidad_default_desconocido():
    assert _vacante().modalidad == Modalidad.DESCONOCIDO
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_modelos.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'jobwatch.modelos'`

- [ ] **Step 3: Write minimal implementation**

```python
# src/jobwatch/modelos.py
from __future__ import annotations

import hashlib
import unicodedata
from enum import Enum

from pydantic import BaseModel, model_validator


class Modalidad(str, Enum):
    REMOTO = "remoto"
    HIBRIDO = "hibrido"
    PRESENCIAL = "presencial"
    DESCONOCIDO = "desconocido"


class EstadoConector(str, Enum):
    OK = "ok"
    ERROR = "error"
    SESION_EXPIRADA = "sesion_expirada"


class EstadoOferta(str, Enum):
    PUNTUADA = "puntuada"
    SIN_PUNTAJE = "sin_puntaje"
    ERROR = "error"


def _clave(texto: str) -> str:
    """Lowercase, strip accents and non-alphanumerics -> comparison key."""
    sin_acentos = "".join(
        c for c in unicodedata.normalize("NFKD", texto) if not unicodedata.combining(c)
    )
    return "".join(c for c in sin_acentos.lower() if c.isalnum() or c == " ").strip()


def calcular_id_estable(portal: str, id_nativo: str) -> str:
    return hashlib.sha256(f"{portal}:{id_nativo}".encode()).hexdigest()[:16]


def calcular_fingerprint(empresa: str, titulo: str, ubicacion: str) -> str:
    crudo = "|".join(_clave(x) for x in (empresa, titulo, ubicacion))
    return hashlib.sha256(crudo.encode()).hexdigest()[:16]


class Criterios(BaseModel):
    terminos: str
    ubicacion: str | None = None
    modalidad: Modalidad | None = None
    salario_min: int | None = None
    excluir: list[str] = []


class Vacante(BaseModel):
    id_nativo: str
    portal: str
    titulo: str
    empresa: str
    ubicacion: str
    modalidad: Modalidad = Modalidad.DESCONOCIDO
    salario_raw: str = ""
    salario_min: int | None = None
    salario_max: int | None = None
    url: str
    fecha_publicacion: str | None = None
    descripcion_raw: str = ""
    id_estable: str = ""
    fingerprint_contenido: str = ""

    @model_validator(mode="after")
    def _computar(self) -> "Vacante":
        object.__setattr__(self, "id_estable", calcular_id_estable(self.portal, self.id_nativo))
        object.__setattr__(
            self, "fingerprint_contenido",
            calcular_fingerprint(self.empresa, self.titulo, self.ubicacion),
        )
        return self


class OfertaPuntuada(BaseModel):
    vacante: Vacante
    estado: EstadoOferta
    puntaje: int | None = None
    razon: str = ""


class ResultadoConector(BaseModel):
    estado: EstadoConector
    vacantes: list[Vacante] = []
    detalle: str = ""
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_modelos.py -v`
Expected: PASS (4 tests)

- [ ] **Step 5: Commit**

```bash
git add src/jobwatch/modelos.py tests/test_modelos.py
git commit -m "feat: core models with computed id_estable and fingerprint"
```

---

### Task 2: Normalization helpers (`normalizar.py`)

**Files:**
- Create: `src/jobwatch/normalizar.py`
- Test: `tests/test_normalizar.py`

**Interfaces:**
- Consumes: `Modalidad` from `modelos`.
- Produces:
  - `normalizar_texto(s: str) -> str` — trim + collapse internal whitespace.
  - `normalizar_ubicacion(s: str) -> str` — canonical city (e.g. "Bogotá D.C." → "Bogotá").
  - `normalizar_modalidad(s: str) -> Modalidad`.
  - `parsear_salario(s: str) -> tuple[int | None, int | None]` — `(min, max)` in whole COP, or `(None, None)`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_normalizar.py
from jobwatch.modelos import Modalidad
from jobwatch.normalizar import (
    normalizar_texto, normalizar_ubicacion, normalizar_modalidad, parsear_salario,
)


def test_normalizar_texto_colapsa_espacios():
    assert normalizar_texto("  Gerente   de\tProyectos ") == "Gerente de Proyectos"


def test_normalizar_ubicacion_canoniza_bogota():
    assert normalizar_ubicacion("Bogotá D.C.") == "Bogotá"
    assert normalizar_ubicacion("Bogota, Colombia") == "Bogotá"
    assert normalizar_ubicacion("Medellín") == "Medellín"


def test_normalizar_modalidad_mapea_sinonimos():
    assert normalizar_modalidad("Trabajo remoto") == Modalidad.REMOTO
    assert normalizar_modalidad("Híbrido") == Modalidad.HIBRIDO
    assert normalizar_modalidad("Presencial") == Modalidad.PRESENCIAL
    assert normalizar_modalidad("cualquier cosa") == Modalidad.DESCONOCIDO


def test_parsear_salario_rango_y_unico():
    assert parsear_salario("$2.000.000 a $3.000.000 COP") == (2_000_000, 3_000_000)
    assert parsear_salario("$4.500.000") == (4_500_000, 4_500_000)
    assert parsear_salario("A convenir") == (None, None)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_normalizar.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'jobwatch.normalizar'`

- [ ] **Step 3: Write minimal implementation**

```python
# src/jobwatch/normalizar.py
from __future__ import annotations

import re

from jobwatch.modelos import Modalidad

_CIUDADES = {
    "bogota": "Bogotá", "bogotá": "Bogotá",
    "medellin": "Medellín", "medellín": "Medellín",
    "cali": "Cali", "barranquilla": "Barranquilla", "cartagena": "Cartagena",
}


def normalizar_texto(s: str) -> str:
    return re.sub(r"\s+", " ", s).strip()


def normalizar_ubicacion(s: str) -> str:
    s = normalizar_texto(s)
    # take the first segment before a comma, drop "D.C." and similar suffixes
    primero = s.split(",")[0]
    primero = re.sub(r"\bd\.?\s*c\.?\b", "", primero, flags=re.IGNORECASE).strip()
    return _CIUDADES.get(primero.lower(), primero)


def normalizar_modalidad(s: str) -> Modalidad:
    t = s.lower()
    if "remoto" in t or "teletrabajo" in t:
        return Modalidad.REMOTO
    if "híbrido" in t or "hibrido" in t:
        return Modalidad.HIBRIDO
    if "presencial" in t:
        return Modalidad.PRESENCIAL
    return Modalidad.DESCONOCIDO


def parsear_salario(s: str) -> tuple[int | None, int | None]:
    numeros = re.findall(r"\d[\d.]*", s)
    valores = [int(n.replace(".", "")) for n in numeros if len(n.replace(".", "")) >= 5]
    if not valores:
        return (None, None)
    if len(valores) == 1:
        return (valores[0], valores[0])
    return (min(valores), max(valores))
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_normalizar.py -v`
Expected: PASS (4 tests)

- [ ] **Step 5: Commit**

```bash
git add src/jobwatch/normalizar.py tests/test_normalizar.py
git commit -m "feat: normalization helpers for text, location, mode, salary"
```

---

### Task 3: SQLite store with two-level dedup (`store.py`)

**Files:**
- Create: `src/jobwatch/store.py`
- Test: `tests/test_store.py`

**Interfaces:**
- Consumes: `Vacante`, `EstadoConector` from `modelos`.
- Produces:
  - `class Store` with:
    - `__init__(self, ruta: str = "jobwatch.db")` — opens connection, calls `_init_schema`.
    - `es_nueva(self, v: Vacante) -> bool` — True if neither `id_estable` nor `fingerprint_contenido` exists.
    - `persistir(self, vacantes: list[Vacante]) -> None` — upsert by `id_estable`.
    - `registrar_corrida(self, estados: dict[str, EstadoConector]) -> int` — store per-connector status, return run id.
    - `cerrar(self) -> None`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_store.py
from jobwatch.modelos import EstadoConector, Vacante
from jobwatch.store import Store


def _v(id_nativo="1", portal="indeed", empresa="ACME", titulo="Dev", ubicacion="Bogotá"):
    return Vacante(id_nativo=id_nativo, portal=portal, empresa=empresa, titulo=titulo,
                   ubicacion=ubicacion, url=f"https://x/{id_nativo}")


def test_es_nueva_true_para_store_vacio(tmp_path):
    s = Store(str(tmp_path / "t.db"))
    assert s.es_nueva(_v()) is True
    s.cerrar()


def test_persistir_hace_que_deje_de_ser_nueva(tmp_path):
    s = Store(str(tmp_path / "t.db"))
    v = _v()
    s.persistir([v])
    assert s.es_nueva(v) is False
    s.cerrar()


def test_dedup_secundaria_por_fingerprint(tmp_path):
    s = Store(str(tmp_path / "t.db"))
    s.persistir([_v(id_nativo="1", portal="computrabajo")])
    # misma oferta, otro portal + otro id nativo -> distinto id_estable, MISMO fingerprint
    otra = _v(id_nativo="2", portal="elempleo")
    assert s.es_nueva(otra) is False
    s.cerrar()


def test_registrar_corrida_devuelve_id_incremental(tmp_path):
    s = Store(str(tmp_path / "t.db"))
    id1 = s.registrar_corrida({"indeed": EstadoConector.OK})
    id2 = s.registrar_corrida({"indeed": EstadoConector.ERROR})
    assert id2 > id1
    s.cerrar()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_store.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'jobwatch.store'`

- [ ] **Step 3: Write minimal implementation**

```python
# src/jobwatch/store.py
from __future__ import annotations

import json
import sqlite3

from jobwatch.modelos import EstadoConector, Vacante


class Store:
    def __init__(self, ruta: str = "jobwatch.db") -> None:
        self.con = sqlite3.connect(ruta)
        self._init_schema()

    def _init_schema(self) -> None:
        self.con.executescript(
            """
            CREATE TABLE IF NOT EXISTS vacantes (
                id_estable TEXT PRIMARY KEY,
                fingerprint_contenido TEXT NOT NULL,
                portal TEXT NOT NULL,
                titulo TEXT NOT NULL,
                empresa TEXT NOT NULL,
                url TEXT NOT NULL,
                datos TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_fingerprint
                ON vacantes(fingerprint_contenido);
            CREATE TABLE IF NOT EXISTS corridas (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                estados TEXT NOT NULL
            );
            """
        )
        self.con.commit()

    def es_nueva(self, v: Vacante) -> bool:
        cur = self.con.execute(
            "SELECT 1 FROM vacantes WHERE id_estable = ? OR fingerprint_contenido = ? LIMIT 1",
            (v.id_estable, v.fingerprint_contenido),
        )
        return cur.fetchone() is None

    def persistir(self, vacantes: list[Vacante]) -> None:
        self.con.executemany(
            """
            INSERT INTO vacantes
                (id_estable, fingerprint_contenido, portal, titulo, empresa, url, datos)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(id_estable) DO NOTHING
            """,
            [
                (v.id_estable, v.fingerprint_contenido, v.portal, v.titulo,
                 v.empresa, v.url, v.model_dump_json())
                for v in vacantes
            ],
        )
        self.con.commit()

    def registrar_corrida(self, estados: dict[str, EstadoConector]) -> int:
        serializable = {k: e.value for k, e in estados.items()}
        cur = self.con.execute(
            "INSERT INTO corridas (estados) VALUES (?)", (json.dumps(serializable),)
        )
        self.con.commit()
        return int(cur.lastrowid)

    def cerrar(self) -> None:
        self.con.close()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_store.py -v`
Expected: PASS (4 tests)

- [ ] **Step 5: Commit**

```bash
git add src/jobwatch/store.py tests/test_store.py
git commit -m "feat: SQLite store with two-level deduplication"
```

---

### Task 4: Local filter (`matcher.filtro_local`)

**Files:**
- Create: `src/jobwatch/matcher.py`
- Test: `tests/test_matcher_filtro.py`

**Interfaces:**
- Consumes: `Vacante`, `Criterios`, `Modalidad` from `modelos`.
- Produces: `filtro_local(v: Vacante, c: Criterios) -> bool` — True if the offer survives (worth LLM scoring). Rejects on: an exclusion keyword present in title/description, salary below `c.salario_min` (only when the offer exposes `salario_max`), or a modalidad mismatch (only when `c.modalidad` is set and the offer's modalidad is known and different).

- [ ] **Step 1: Write the failing test**

```python
# tests/test_matcher_filtro.py
from jobwatch.modelos import Criterios, Modalidad, Vacante
from jobwatch.matcher import filtro_local


def _v(**over):
    base = dict(id_nativo="1", portal="indeed", titulo="Gerente de Proyectos TI",
                empresa="ACME", ubicacion="Bogotá", url="https://x/1")
    base.update(over)
    return Vacante(**base)


def test_sobrevive_por_defecto():
    assert filtro_local(_v(), Criterios(terminos="gerente")) is True


def test_rechaza_por_keyword_excluida():
    v = _v(titulo="Gerente de Ventas puerta a puerta")
    assert filtro_local(v, Criterios(terminos="gerente", excluir=["ventas"])) is False


def test_rechaza_por_salario_bajo_solo_si_hay_dato():
    caro = _v(salario_max=5_000_000)
    barato = _v(salario_max=1_000_000)
    sin_dato = _v()
    c = Criterios(terminos="x", salario_min=3_000_000)
    assert filtro_local(caro, c) is True
    assert filtro_local(barato, c) is False
    assert filtro_local(sin_dato, c) is True  # sin dato no se descarta


def test_rechaza_por_modalidad_solo_si_conocida():
    c = Criterios(terminos="x", modalidad=Modalidad.REMOTO)
    assert filtro_local(_v(modalidad=Modalidad.PRESENCIAL), c) is False
    assert filtro_local(_v(modalidad=Modalidad.REMOTO), c) is True
    assert filtro_local(_v(modalidad=Modalidad.DESCONOCIDO), c) is True
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_matcher_filtro.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'jobwatch.matcher'`

- [ ] **Step 3: Write minimal implementation**

```python
# src/jobwatch/matcher.py
from __future__ import annotations

from jobwatch.modelos import Criterios, Modalidad, Vacante


def filtro_local(v: Vacante, c: Criterios) -> bool:
    texto = f"{v.titulo} {v.descripcion_raw}".lower()
    if any(kw.lower() in texto for kw in c.excluir):
        return False
    if c.salario_min is not None and v.salario_max is not None:
        if v.salario_max < c.salario_min:
            return False
    if c.modalidad is not None and v.modalidad is not Modalidad.DESCONOCIDO:
        if v.modalidad is not c.modalidad:
            return False
    return True
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_matcher_filtro.py -v`
Expected: PASS (4 tests)

- [ ] **Step 5: Commit**

```bash
git add src/jobwatch/matcher.py tests/test_matcher_filtro.py
git commit -m "feat: cheap deterministic local filter"
```

---

### Task 5: LLM scoring with cap + fail-loud (`matcher.puntuar`)

**Files:**
- Modify: `src/jobwatch/matcher.py`
- Test: `tests/test_matcher_puntuar.py`

**Interfaces:**
- Consumes: `Vacante`, `OfertaPuntuada`, `EstadoOferta` from `modelos`.
- Produces:
  - `PuntuadorLLM = Callable[[Vacante, str], dict]` — takes `(vacante, cv)`, returns `{"puntaje": int, "razon": str}`. Injected; real implementation wired in the CLI task.
  - `puntuar(vacantes: list[Vacante], cv: str, puntuador: PuntuadorLLM, tope: int = 50) -> list[OfertaPuntuada]` — scores each; on a `puntuador` exception, that offer gets `EstadoOferta.ERROR` (fail-loud, does not abort the batch); if `len(vacantes) > tope`, raises `TopeExcedido` before calling the LLM at all.
  - `class TopeExcedido(Exception)`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_matcher_puntuar.py
import pytest

from jobwatch.modelos import EstadoOferta, Vacante
from jobwatch.matcher import puntuar, TopeExcedido


def _v(id_nativo):
    return Vacante(id_nativo=id_nativo, portal="indeed", titulo="Dev", empresa="ACME",
                   ubicacion="Bogotá", url=f"https://x/{id_nativo}")


def test_puntua_cada_oferta():
    def fake(v, cv):
        return {"puntaje": 80, "razon": "encaja"}
    res = puntuar([_v("1"), _v("2")], "mi cv", fake)
    assert [o.estado for o in res] == [EstadoOferta.PUNTUADA, EstadoOferta.PUNTUADA]
    assert res[0].puntaje == 80 and res[0].razon == "encaja"


def test_fallo_de_una_no_aborta_el_lote():
    def flaky(v, cv):
        if v.id_nativo == "2":
            raise RuntimeError("timeout")
        return {"puntaje": 50, "razon": "ok"}
    res = puntuar([_v("1"), _v("2"), _v("3")], "cv", flaky)
    assert [o.estado for o in res] == [
        EstadoOferta.PUNTUADA, EstadoOferta.ERROR, EstadoOferta.PUNTUADA,
    ]


def test_tope_excedido_no_llama_al_llm():
    llamadas = []
    def espia(v, cv):
        llamadas.append(v)
        return {"puntaje": 1, "razon": ""}
    with pytest.raises(TopeExcedido):
        puntuar([_v(str(i)) for i in range(5)], "cv", espia, tope=3)
    assert llamadas == []
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_matcher_puntuar.py -v`
Expected: FAIL with `ImportError: cannot import name 'puntuar'`

- [ ] **Step 3: Write minimal implementation (append to `matcher.py`)**

```python
# src/jobwatch/matcher.py  (add these imports at top and code at bottom)
from typing import Callable

from jobwatch.modelos import EstadoOferta, OfertaPuntuada

PuntuadorLLM = Callable[[Vacante, str], dict]


class TopeExcedido(Exception):
    pass


def puntuar(
    vacantes: list[Vacante],
    cv: str,
    puntuador: PuntuadorLLM,
    tope: int = 50,
) -> list[OfertaPuntuada]:
    if len(vacantes) > tope:
        raise TopeExcedido(
            f"{len(vacantes)} ofertas superan el tope de {tope}; "
            f"revisa el filtro local antes de gastar en el LLM."
        )
    resultado: list[OfertaPuntuada] = []
    for v in vacantes:
        try:
            r = puntuador(v, cv)
            resultado.append(
                OfertaPuntuada(
                    vacante=v, estado=EstadoOferta.PUNTUADA,
                    puntaje=int(r["puntaje"]), razon=str(r.get("razon", "")),
                )
            )
        except Exception as e:  # fail-loud per offer, no aborta el lote
            resultado.append(
                OfertaPuntuada(vacante=v, estado=EstadoOferta.ERROR, razon=str(e))
            )
    return resultado
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_matcher_puntuar.py -v`
Expected: PASS (3 tests)

- [ ] **Step 5: Commit**

```bash
git add src/jobwatch/matcher.py tests/test_matcher_puntuar.py
git commit -m "feat: LLM scoring with per-run cap and fail-loud per offer"
```

---

### Task 6: Indeed connector via JobSpy (`conectores/indeed.py`)

**Files:**
- Create: `src/jobwatch/conectores/__init__.py` (empty)
- Create: `src/jobwatch/conectores/indeed.py`
- Test: `tests/conectores/test_indeed.py`
- Create: `tests/conectores/__init__.py` (empty)

**Interfaces:**
- Consumes: `Criterios`, `Vacante`, `ResultadoConector`, `EstadoConector`, `Modalidad` from `modelos`; `normalizar_ubicacion`, `normalizar_modalidad`, `parsear_salario` from `normalizar`.
- Produces: `buscar(criterios: Criterios, scrape=None) -> ResultadoConector`. `scrape` defaults to `jobspy.scrape_jobs`; injected in tests. Each JobSpy row → `Vacante` (portal `"indeed"`, `id_nativo` from the row's `id`/`job_url`). On exception → `ResultadoConector(estado=ERROR, detalle=...)`. An empty result → `estado=OK, vacantes=[]` (a real empty search, distinct from the ERROR path).

- [ ] **Step 1: Write the failing test**

```python
# tests/conectores/test_indeed.py
from jobwatch.modelos import Criterios, EstadoConector
from jobwatch.conectores.indeed import buscar


class _FakeDF:
    """Minimal stand-in for the pandas DataFrame JobSpy returns."""
    def __init__(self, filas):
        self._filas = filas
    def to_dict(self, orient):
        assert orient == "records"
        return self._filas


def test_mapea_filas_a_vacantes():
    filas = [{
        "id": "abc123", "title": "Gerente de Proyectos TI", "company": "ACME",
        "location": "Bogotá D.C.", "job_url": "https://indeed/abc123",
        "is_remote": True, "min_amount": 4_000_000, "max_amount": 6_000_000,
        "description": "…", "date_posted": "2026-07-20",
    }]
    r = buscar(Criterios(terminos="gerente"), scrape=lambda **kw: _FakeDF(filas))
    assert r.estado == EstadoConector.OK
    assert len(r.vacantes) == 1
    v = r.vacantes[0]
    assert v.portal == "indeed" and v.id_nativo == "abc123"
    assert v.ubicacion == "Bogotá" and v.salario_max == 6_000_000


def test_resultado_vacio_es_ok_no_error():
    r = buscar(Criterios(terminos="x"), scrape=lambda **kw: _FakeDF([]))
    assert r.estado == EstadoConector.OK and r.vacantes == []


def test_excepcion_de_jobspy_es_error_fail_loud():
    def explota(**kw):
        raise RuntimeError("bloqueado")
    r = buscar(Criterios(terminos="x"), scrape=explota)
    assert r.estado == EstadoConector.ERROR and "bloqueado" in r.detalle
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/conectores/test_indeed.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'jobwatch.conectores'`

- [ ] **Step 3: Write minimal implementation**

```python
# src/jobwatch/conectores/indeed.py
from __future__ import annotations

from jobwatch.modelos import (
    Criterios, EstadoConector, Modalidad, ResultadoConector, Vacante,
)
from jobwatch.normalizar import normalizar_ubicacion, parsear_salario


def _id_nativo(fila: dict) -> str:
    return str(fila.get("id") or fila.get("job_url") or "")


def _a_vacante(fila: dict) -> Vacante:
    smin = fila.get("min_amount")
    smax = fila.get("max_amount")
    if smin is None and smax is None:
        smin, smax = parsear_salario(str(fila.get("salary", "") or ""))
    return Vacante(
        id_nativo=_id_nativo(fila),
        portal="indeed",
        titulo=str(fila.get("title", "")),
        empresa=str(fila.get("company", "")),
        ubicacion=normalizar_ubicacion(str(fila.get("location", ""))),
        modalidad=Modalidad.REMOTO if fila.get("is_remote") else Modalidad.DESCONOCIDO,
        salario_min=int(smin) if smin is not None else None,
        salario_max=int(smax) if smax is not None else None,
        url=str(fila.get("job_url", "")),
        fecha_publicacion=str(fila.get("date_posted")) if fila.get("date_posted") else None,
        descripcion_raw=str(fila.get("description", "") or ""),
    )


def buscar(criterios: Criterios, scrape=None) -> ResultadoConector:
    if scrape is None:
        from jobspy import scrape_jobs as scrape  # imported lazily to keep tests offline

    try:
        df = scrape(
            site_name=["indeed"],
            search_term=criterios.terminos,
            location=criterios.ubicacion or "Colombia",
            country_indeed="colombia",
        )
        filas = df.to_dict("records")
    except Exception as e:  # fail-loud (D4): JobSpy is not under our control
        return ResultadoConector(estado=EstadoConector.ERROR, detalle=str(e))

    vacantes = [_a_vacante(f) for f in filas if _id_nativo(f)]
    return ResultadoConector(estado=EstadoConector.OK, vacantes=vacantes)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/conectores/test_indeed.py -v`
Expected: PASS (3 tests)

- [ ] **Step 5: Commit**

```bash
git add src/jobwatch/conectores/ tests/conectores/
git commit -m "feat: Indeed connector via JobSpy with fail-loud adapter"
```

---

### Task 7: Report renderer (`reporte.py`)

**Files:**
- Create: `src/jobwatch/reporte.py`
- Test: `tests/test_reporte.py`

**Interfaces:**
- Consumes: `OfertaPuntuada`, `EstadoConector`, `EstadoOferta` from `modelos`.
- Produces: `render(fecha: str, estados: dict[str, EstadoConector], ofertas: list[OfertaPuntuada]) -> str`. Markdown with: a title bearing `fecha`; a per-connector status line (marking `ERROR` explicitly); offers sorted by `puntaje` desc (scored first, `SIN_PUNTAJE`/`ERROR` last); each row shows title, company, location, score, reason, and link.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_reporte.py
from jobwatch.modelos import (
    EstadoConector, EstadoOferta, OfertaPuntuada, Vacante,
)
from jobwatch.reporte import render


def _op(id_nativo, puntaje, estado=EstadoOferta.PUNTUADA):
    v = Vacante(id_nativo=id_nativo, portal="indeed", titulo=f"Cargo {id_nativo}",
                empresa="ACME", ubicacion="Bogotá", url=f"https://x/{id_nativo}")
    return OfertaPuntuada(vacante=v, estado=estado, puntaje=puntaje, razon="motivo")


def test_render_incluye_fecha_y_estado_de_conector():
    md = render("2026-07-23", {"indeed": EstadoConector.ERROR}, [])
    assert "2026-07-23" in md
    assert "indeed" in md and "ERROR" in md


def test_ofertas_ordenadas_por_puntaje_desc():
    ofertas = [_op("1", 40), _op("2", 90), _op("3", 65)]
    md = render("2026-07-23", {"indeed": EstadoConector.OK}, ofertas)
    assert md.index("Cargo 2") < md.index("Cargo 3") < md.index("Cargo 1")


def test_sin_puntaje_va_al_final():
    ofertas = [_op("1", None, EstadoOferta.ERROR), _op("2", 50)]
    md = render("2026-07-23", {"indeed": EstadoConector.OK}, ofertas)
    assert md.index("Cargo 2") < md.index("Cargo 1")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_reporte.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'jobwatch.reporte'`

- [ ] **Step 3: Write minimal implementation**

```python
# src/jobwatch/reporte.py
from __future__ import annotations

from jobwatch.modelos import EstadoConector, EstadoOferta, OfertaPuntuada


def _orden(o: OfertaPuntuada) -> int:
    # scored offers first (higher score first), unscored/error last
    return -(o.puntaje if o.estado is EstadoOferta.PUNTUADA and o.puntaje is not None else -1)


def render(
    fecha: str,
    estados: dict[str, EstadoConector],
    ofertas: list[OfertaPuntuada],
) -> str:
    lineas = [f"# Vacantes nuevas — {fecha}", ""]

    lineas.append("## Estado de conectores")
    for portal, estado in estados.items():
        marca = "⚠️ ERROR" if estado is EstadoConector.ERROR else estado.value.upper()
        lineas.append(f"- **{portal}**: {marca}")
    lineas.append("")

    lineas.append(f"## Ofertas ({len(ofertas)})")
    if not ofertas:
        lineas.append("_Sin ofertas nuevas en esta corrida._")
    for o in sorted(ofertas, key=_orden):
        v = o.vacante
        puntaje = o.puntaje if o.estado is EstadoOferta.PUNTUADA else "—"
        lineas.append(
            f"### [{v.titulo}]({v.url}) · {puntaje}\n"
            f"- Empresa: {v.empresa}\n"
            f"- Ubicación: {v.ubicacion}\n"
            f"- Motivo: {o.razon}\n"
        )
    return "\n".join(lineas)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_reporte.py -v`
Expected: PASS (3 tests)

- [ ] **Step 5: Commit**

```bash
git add src/jobwatch/reporte.py tests/test_reporte.py
git commit -m "feat: Markdown report renderer with per-connector status"
```

---

### Task 8: Orchestration + CLI (`cli.py`)

**Files:**
- Create: `src/jobwatch/orquestador.py`
- Create: `src/jobwatch/cli.py`
- Test: `tests/test_orquestador.py`

**Interfaces:**
- Consumes: everything above; a registry of connectors `CONECTORES: dict[str, Callable[[Criterios], ResultadoConector]]`.
- Produces:
  - `correr(criterios, cv, store, puntuador, conectores, fecha, tope=50) -> tuple[str, dict]` — runs the full pipeline (harvest → dedup via `store.es_nueva` → `filtro_local` → `puntuar` → `store.persistir` + `store.registrar_corrida`) and returns `(markdown, estados)`.
  - `cli.main(argv=None) -> int` — `argparse` with subcommands `run` and `carta`; wires the real `curl_cffi`/JobSpy connectors and a real LLM `puntuador`. Writes the report to `reportes/<fecha>.md`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_orquestador.py
from jobwatch.modelos import Criterios, EstadoConector, ResultadoConector, Vacante
from jobwatch.orquestador import correr
from jobwatch.store import Store


def _v(id_nativo, empresa="ACME", titulo="Dev"):
    return Vacante(id_nativo=id_nativo, portal="indeed", empresa=empresa, titulo=titulo,
                   ubicacion="Bogotá", url=f"https://x/{id_nativo}")


def _conector_ok(vacantes):
    return lambda c: ResultadoConector(estado=EstadoConector.OK, vacantes=vacantes)


def test_solo_puntua_las_nuevas(tmp_path):
    store = Store(str(tmp_path / "t.db"))
    store.persistir([_v("1")])  # ya vista
    conectores = {"indeed": _conector_ok([_v("1"), _v("2")])}
    puntuadas = []
    def fake(v, cv):
        puntuadas.append(v.id_nativo)
        return {"puntaje": 70, "razon": "ok"}
    md, estados = correr(Criterios(terminos="dev"), "cv", store, fake, conectores, "2026-07-23")
    assert puntuadas == ["2"]           # solo la nueva se puntúa
    assert "2026-07-23" in md
    assert estados["indeed"] == EstadoConector.OK
    store.cerrar()


def test_estado_error_se_propaga_al_reporte(tmp_path):
    store = Store(str(tmp_path / "t.db"))
    conectores = {
        "indeed": lambda c: ResultadoConector(estado=EstadoConector.ERROR, detalle="bloqueado"),
    }
    md, estados = correr(Criterios(terminos="x"), "cv", store, lambda v, cv: {}, conectores, "2026-07-23")
    assert estados["indeed"] == EstadoConector.ERROR
    assert "ERROR" in md
    store.cerrar()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_orquestador.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'jobwatch.orquestador'`

- [ ] **Step 3: Write minimal implementation**

```python
# src/jobwatch/orquestador.py
from __future__ import annotations

from typing import Callable

from jobwatch.matcher import filtro_local, puntuar
from jobwatch.modelos import Criterios, EstadoConector, ResultadoConector
from jobwatch.reporte import render
from jobwatch.store import Store

Conector = Callable[[Criterios], ResultadoConector]


def correr(
    criterios: Criterios,
    cv: str,
    store: Store,
    puntuador,
    conectores: dict[str, Conector],
    fecha: str,
    tope: int = 50,
) -> tuple[str, dict[str, EstadoConector]]:
    estados: dict[str, EstadoConector] = {}
    nuevas = []
    for nombre, conector in conectores.items():
        r = conector(criterios)
        estados[nombre] = r.estado
        for v in r.vacantes:
            if store.es_nueva(v) and filtro_local(v, criterios):
                nuevas.append(v)

    ofertas = puntuar(nuevas, cv, puntuador, tope=tope)
    store.persistir(nuevas)
    store.registrar_corrida(estados)
    return render(fecha, estados, ofertas), estados
```

```python
# src/jobwatch/cli.py
from __future__ import annotations

import argparse
import datetime as _dt
from pathlib import Path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="jobwatch", description="Agregador de empleos.")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_run = sub.add_parser("run", help="Corre la búsqueda y escribe el reporte.")
    p_run.add_argument("--terminos", required=True)
    p_run.add_argument("--ubicacion", default=None)
    p_run.add_argument("--cv", required=True, help="Ruta al archivo de CV (texto).")
    p_run.add_argument("--db", default="jobwatch.db")

    p_carta = sub.add_parser("carta", help="Redacta una carta para una oferta guardada.")
    p_carta.add_argument("id_estable")
    p_carta.add_argument("--db", default="jobwatch.db")

    args = parser.parse_args(argv)

    if args.cmd == "run":
        from jobwatch.conectores import indeed
        from jobwatch.llm import puntuador_real
        from jobwatch.modelos import Criterios
        from jobwatch.orquestador import correr
        from jobwatch.store import Store

        cv = Path(args.cv).read_text(encoding="utf-8")
        criterios = Criterios(terminos=args.terminos, ubicacion=args.ubicacion)
        store = Store(args.db)
        conectores = {"indeed": indeed.buscar}
        fecha = _dt.date.today().isoformat()
        md, _ = correr(criterios, cv, store, puntuador_real, conectores, fecha)
        store.cerrar()

        destino = Path("reportes") / f"{fecha}.md"
        destino.parent.mkdir(exist_ok=True)
        destino.write_text(md, encoding="utf-8")
        print(f"Reporte escrito en {destino}")
        return 0

    if args.cmd == "carta":
        from jobwatch.cartas import redactar_desde_store
        print(redactar_desde_store(args.id_estable, args.db))
        return 0

    return 1


if __name__ == "__main__":
    raise SystemExit(main())
```

> `jobwatch.llm.puntuador_real` and `jobwatch.cartas.redactar_desde_store` are implemented in Task 9. They are imported lazily inside `main`, so the `run`/`carta` wiring is covered by the orchestrator test with fakes; the real LLM path is exercised manually.

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_orquestador.py -v`
Expected: PASS (2 tests)

- [ ] **Step 5: Commit**

```bash
git add src/jobwatch/orquestador.py src/jobwatch/cli.py tests/test_orquestador.py
git commit -m "feat: pipeline orchestrator and CLI"
```

---

### Task 9: LLM adapter + on-demand cover letter (`llm.py`, `cartas.py`)

**Files:**
- Create: `src/jobwatch/llm.py`
- Create: `src/jobwatch/cartas.py`
- Test: `tests/test_cartas.py`

**Interfaces:**
- Consumes: `Vacante` from `modelos`; `Store` from `store`.
- Produces:
  - `llm.puntuador_real(v: Vacante, cv: str) -> dict` — real Anthropic call returning `{"puntaje": int, "razon": str}`. Not unit-tested (network); thin wrapper only.
  - `cartas.redactar(v: Vacante, cv: str, generar: Callable[[str], str]) -> str` — builds a Spanish prompt from the offer + CV, calls injected `generar`, returns the letter. Testable with a fake `generar`.
  - `cartas.redactar_desde_store(id_estable: str, db: str) -> str` — loads the offer JSON from the store and calls `redactar` with the real generator. Raises `ValueError` if the id is unknown.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_cartas.py
import pytest

from jobwatch.modelos import Vacante
from jobwatch.cartas import redactar


def test_redactar_usa_generador_inyectado():
    v = Vacante(id_nativo="1", portal="indeed", titulo="Gerente de Proyectos TI",
                empresa="ACME", ubicacion="Bogotá", url="https://x/1")
    capturado = {}
    def fake_generar(prompt: str) -> str:
        capturado["prompt"] = prompt
        return "Estimados de ACME, ..."
    carta = redactar(v, "PM con 10 años de experiencia en entrega de software…", fake_generar)
    assert carta.startswith("Estimados de ACME")
    # el prompt debe incorporar el cargo y la empresa
    assert "Gerente de Proyectos TI" in capturado["prompt"]
    assert "ACME" in capturado["prompt"]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_cartas.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'jobwatch.cartas'`

- [ ] **Step 3: Write minimal implementation**

```python
# src/jobwatch/cartas.py
from __future__ import annotations

import json
from typing import Callable

from jobwatch.modelos import Vacante


def redactar(v: Vacante, cv: str, generar: Callable[[str], str]) -> str:
    prompt = (
        "Redacta una carta de presentación breve y profesional en español "
        f"para la vacante «{v.titulo}» en {v.empresa} ({v.ubicacion}).\n\n"
        f"Descripción de la vacante:\n{v.descripcion_raw}\n\n"
        f"Perfil del candidato (CV):\n{cv}\n"
    )
    return generar(prompt)


def redactar_desde_store(id_estable: str, db: str) -> str:
    import sqlite3

    from jobwatch.llm import generar_texto

    con = sqlite3.connect(db)
    try:
        fila = con.execute(
            "SELECT datos FROM vacantes WHERE id_estable = ?", (id_estable,)
        ).fetchone()
    finally:
        con.close()
    if fila is None:
        raise ValueError(f"No existe una oferta con id_estable={id_estable}")
    v = Vacante(**json.loads(fila[0]))
    cv = _leer_cv_por_defecto()
    return redactar(v, cv, generar_texto)


def _leer_cv_por_defecto() -> str:
    from pathlib import Path

    ruta = Path("data/cv.txt")
    return ruta.read_text(encoding="utf-8") if ruta.exists() else ""
```

```python
# src/jobwatch/llm.py
from __future__ import annotations

import json
import os

from jobwatch.modelos import Vacante

_MODELO = "claude-sonnet-5"


def _cliente():
    from anthropic import Anthropic

    return Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])


def generar_texto(prompt: str) -> str:
    msg = _cliente().messages.create(
        model=_MODELO, max_tokens=1024,
        messages=[{"role": "user", "content": prompt}],
    )
    return msg.content[0].text


def puntuador_real(v: Vacante, cv: str) -> dict:
    prompt = (
        "Evalúa qué tan bien encaja esta vacante con el CV. "
        'Responde SOLO un JSON {"puntaje": 0-100, "razon": "una frase"}.\n\n'
        f"Vacante: {v.titulo} en {v.empresa}. {v.descripcion_raw}\n\nCV:\n{cv}\n"
    )
    return json.loads(generar_texto(prompt))
```

> `llm.py` is a thin network wrapper — not unit-tested. Before using it, confirm the current model id and SDK usage with the `claude-api` skill.

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_cartas.py -v`
Expected: PASS (1 test)

- [ ] **Step 5: Commit**

```bash
git add src/jobwatch/llm.py src/jobwatch/cartas.py tests/test_cartas.py
git commit -m "feat: LLM adapter and on-demand cover-letter generation"
```

---

### Task 10: Full suite + scheduling recipe

**Files:**
- Modify: `README.md` (add a "Programación" section)
- Test: whole suite

- [ ] **Step 1: Run the whole suite**

Run: `pytest -v`
Expected: PASS (all modules).

- [ ] **Step 2: Lint**

Run: `ruff check src tests`
Expected: no errors (fix any inline).

- [ ] **Step 3: Add scheduling recipe to README**

Append a short Spanish "Programación" section documenting a WSL2 cron entry, e.g.:

```markdown
## Programación

En WSL2, agrega a `crontab -e` una corrida diaria a las 8am:

    0 8 * * * cd /ruta/a/jobwatch && ANTHROPIC_API_KEY=… .venv/bin/jobwatch run \
      --terminos "Gerente de Proyectos TI" --ubicacion "Colombia" --cv data/cv.txt

El reporte queda en `reportes/AAAA-MM-DD.md`.
```

- [ ] **Step 4: Commit**

```bash
git add README.md
git commit -m "docs: scheduling recipe for WSL2 cron"
```

---

## Deferred to a later plan (post Phase 0)

- **Connectors for Computrabajo, elempleo, Magneto.** Each needs its real endpoint/response shape from Phase 0 (`docs/endpoints.md`) before its TDD steps can be written with real payloads. They plug into `CONECTORES` in the orchestrator with the exact same `buscar(criterios) -> ResultadoConector` contract, so no core changes are expected — only new files under `conectores/` + their tests.
- **Session subsystem (`sesion.py`).** Built only if one of those connectors starts returning 401/403 on its listing endpoint (design D1 trigger).

## Self-review notes

- **Spec coverage:** models (§3.2) → T1; normalization (D7, §7) → T2; store + two-level dedup (§6, §8) → T3; local filter (§7) → T4; LLM cap + fail-loud (§7, D6) → T5; Indeed/JobSpy fail-loud adapter (D4, §2) → T6; report + per-connector status (§8, D2) → T7; pipeline + CLI (§3) → T8; lazy letters (D6) → T9; scheduler (§8) → T10. Colombian connectors + session (§2, D1, D5) explicitly deferred with rationale.
- **Type consistency:** `buscar(criterios) -> ResultadoConector`, `EstadoConector`, `EstadoOferta`, `OfertaPuntuada`, `filtro_local`, `puntuar`, `correr` names are consistent across T1–T9.
- **Fakes everywhere:** no test touches the network or a real LLM (`puntuador`, `scrape`, `generar` all injected).

---

## Correcciones aplicadas durante la implementación

El plan se ejecutó con TDD (un subagente por tarea + revisión). Los siguientes ajustes se hicieron sobre el código de referencia de arriba para que los tests pasaran o para endurecer contra datos reales. El código en `src/` es la fuente de verdad; esta lista documenta los deltas.

- **Tarea 1 — fingerprint / normalización D.C.** El `_clave()` de referencia y su test eran inconsistentes con "D.C.". La normalización del sufijo "D.C." se acotó a la ubicación (`_clave_ubicacion`) y se hizo insensible a mayúsculas, para no mutilar nombres de empresa/título que contengan "D.C.".
- **Tarea 2 — regex de ubicación.** Se reposicionó el word-boundary (`\bd\.?\s*c\b\.?`) para no comerse ciudades reales que empiezan por C precedidas de una "D" suelta (p. ej. "D Cali").
- **Tarea 6 — conector Indeed / pandas NaN.** JobSpy real devuelve un DataFrame donde las celdas faltantes son `NaN` (float), no `None`. Se añadió coerción `_sin_nan` y mapeo por-fila con `try/except`, para no crashear (`int(nan)`), no etiquetar mal `is_remote`, ni corromper `id_nativo`. Las filas inválidas se cuentan en `detalle`.
- **Tarea 8 — fixture de test.** Los datos de prueba colisionaban bajo la dedup secundaria (mismo fingerprint); se les dio un título distinto para probar la intención real ("solo se puntúa la nueva").
- **Tarea 9 — extracción del LLM.** `content[0].text` falla cuando el modelo emite un bloque de *thinking* primero; se extrae el primer bloque de tipo `text`. El parseo de JSON se hizo tolerante a fences/prosa. El comando `carta` recibe `--cv` y falla explícito si el CV está vacío, en vez de generar con un CV en blanco.

### Pendientes conocidos (para el plan de conectores post-Fase 0)

- **Dedup dentro de la misma corrida.** `correr()` deduplica solo contra el estado del store de corridas previas, no dentro del lote actual. Con varios conectores, la misma oferta vista en dos portales en la misma corrida se persistiría dos veces. Es inocuo mientras Indeed sea el único conector; debe añadirse dedup por `fingerprint_contenido` dentro del lote cuando lleguen los conectores colombianos (promesa §6 del diseño, "vista en N portales").
- **Propagación de `detalle` al reporte.** Hoy el reporte muestra `ERROR` por conector pero no el motivo (`detalle`). Enriquecer el render para mostrar "bloqueado" vs "rate-limited" fortalecería la señal fail-loud (D2).
