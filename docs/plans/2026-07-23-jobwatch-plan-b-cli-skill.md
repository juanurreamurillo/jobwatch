# Plan B — CLI + Skill de Claude Code · Plan de Implementación

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Extraer un core in-process (`cosechar`/`validar_scores`/`reportar`), partir `run` en `harvest` + `report` con `run_id` y validación fail-loud, y empaquetar jobwatch como skill pública de Claude Code que puntúa sin API key.

**Architecture:** El pipeline determinista se parte en dos fases alrededor del único paso LLM (§3 del diseño). Un **core in-process** (`nucleo.py`) concentra la lógica; el CLI es solo un adaptador de serialización JSON en el borde. `harvest` (solo-lectura) emite candidatas + `run_id`; el agente (o el SDK en `run`) puntúa; `report` valida fail-loud contra el `run_id` y persiste+renderiza. Un solo pipeline, dos puntos de entrada (DRY).

**Tech Stack:** Python ≥3.10, pydantic 2, sqlite3 (stdlib), argparse (stdlib), pytest, ruff. Sin dependencias nuevas de runtime (el bundle de skill son 3 archivos de texto; publicar añade `build`+`twine` como extras dev).

**Spec de referencia:** `docs/design-skill.md` (D8–D15) que extiende `docs/design.md` (D1–D7). Léelos antes de empezar. Estado del repo: Plan A mergeado (PR #1), 69 tests verdes, ruff limpio, en `main`.

## Global Constraints

- **Copy de cara al usuario en español.** Mensajes de CLI, `SKILL.md`, reporte.
- **Repo público — cero datos personales.** El bundle trae solo *plantillas*; nunca un CV ni una config rellena. Commits con email noreply de GitHub (ya configurado). Nunca commitear `secrets/`, `data/`, `reportes/`, `*.db`, `discovery/captures/` (ya en `.gitignore`).
- **Fail-loud.** Un productor de puntajes falible (agente) no puede corromper el store: `validar_scores` aborta antes de escribir si algo no cuadra (D14).
- **Un solo pipeline (DRY).** `harvest`/`report`/`run` invocan el **mismo** core in-process (§4.0/§4.4/D8). Nada de lógica duplicada.
- **Tests offline.** Sin red, sin `ANTHROPIC_API_KEY`, sin llamadas reales al LLM. Los puntuadores en tests son callables falsos.
- **`harvest` es solo-lectura; `report` hace TODAS las escrituras** (D13). Abandonar a medias no borra ofertas del radar (D2).
- **No romper Plan A.** Los 69 tests existentes deben quedar verdes salvo los explícitamente reemplazados en este plan (Tarea 5 retira `matcher.puntuar` y su test; Tarea 2 reubica el import de `colapsar_lote`).
- **ruff:** `line-length = 100`, `target-version = py310`. Correr `.venv/bin/ruff check src tests` limpio antes de cada commit.
- **Entorno:** `.venv/bin/pytest -q` corre todo; `pythonpath = ["src", "."]` ya resuelto en `pyproject.toml`.

### Dos aclaraciones de implementación (no estructurales; anotadas para veto de Juan)

1. **`cosechar` recibe `fecha`.** La firma ilustrativa de §4.0 la omite, pero `run_id` = hash de `id_estable` ordenados **+ fecha** (§4.1). Pasar `fecha` como parámetro mantiene el core puro y testeable sin reloj. La costura no cambia.
2. **El JSON de `harvest` emite el `Vacante` completo por candidata, no el subconjunto ilustrativo de §4.1.** `report` debe reconstruir el `Vacante` para persistir, y el subconjunto de §4.1 (sin `portal`/`id_nativo`) no permite recomputar `id_estable`. El payload real es un **superconjunto** round-trippable de los campos documentados; el contrato con el agente (que solo lee `titulo`/`empresa`/`descripcion_raw`/`id_estable`) se preserva.

---

## File Structure

**Nuevos:**
- `src/jobwatch/nucleo.py` — el core in-process: `calcular_run_id`, `_prioridad`, `colapsar_lote` (movidos de `orquestador`), `TopeExcedido`, `ScoresInvalidos`, `PuntuadorLLM`, `cosechar`, `validar_scores`, `reportar`, `puntuar_en_proceso`.
- `src/jobwatch/config.py` — `cargar_criterios(ruta) -> Criterios` (§4.6).
- `skill/SKILL.md` — frontmatter (name/description=trigger) + flujo de 5 pasos (§5).
- `skill/jobwatch.config.example.json` — plantilla de `Criterios`.
- `skill/references/scoring-rubric.md` — rúbrica 0–100.
- `tests/test_nucleo.py` — cosechar/validar_scores/reportar/run_id/puntuar_en_proceso.
- `tests/test_config.py` — `cargar_criterios`.
- `tests/test_cli_harvest.py`, `tests/test_cli_report.py` — subcomandos vía `main([...])`.
- `tests/test_skill_bundle.py` — la plantilla deserializa a `Criterios`; archivos del bundle existen.

**Modificados:**
- `src/jobwatch/modelos.py` — añade `Puntaje`, `LotePuntajes`, `Cosecha`.
- `src/jobwatch/matcher.py` — se queda solo con `filtro_local`; retira `puntuar`/`TopeExcedido`/`PuntuadorLLM` (movidos a `nucleo`).
- `src/jobwatch/orquestador.py` — `correr` reescrito sobre el core; `colapsar_lote`/`_prioridad` movidos a `nucleo` (re-exportados para compat).
- `src/jobwatch/cli.py` — subcomandos `harvest` y `report`; `run` acepta `--config`/`--tope`.
- `tests/test_orquestador.py` — import de `colapsar_lote` desde `nucleo`; tests de `correr` preservados.
- `pyproject.toml` — versión `0.0.1`→`0.1.0`; extra dev `build`/`twine`.
- `docs/HANDOFF.md`, `README.md` — estado post-Plan-B + instrucciones de skill.

**Eliminados:**
- `tests/test_matcher_puntuar.py` — su sujeto (`matcher.puntuar`) se retira; cobertura equivalente en `test_nucleo.py` (tope en `cosechar`, validación en `validar_scores`).

---

## Task 1: Modelos de la costura (`Puntaje`, `LotePuntajes`, `Cosecha`)

**Files:**
- Modify: `src/jobwatch/modelos.py` (añadir al final, tras `ResultadoConector`)
- Test: `tests/test_modelos.py` (añadir tests; no tocar los existentes)

**Interfaces:**
- Consumes: `Vacante`, `ResultadoConector`, `EstadoOferta` (ya en `modelos.py`).
- Produces:
  - `Puntaje(BaseModel)`: `id_estable: str`, `estado: EstadoOferta`, `puntaje: int | None = None`, `razon: str = ""`.
  - `LotePuntajes(BaseModel)`: `run_id: str`, `puntajes: list[Puntaje]`.
  - `Cosecha(BaseModel)`: `run_id: str`, `tope: int`, `estados: dict[str, ResultadoConector]`, `candidatas: list[Vacante]`.

- [ ] **Step 1: Write the failing test**

En `tests/test_modelos.py`, añade:

```python
def test_cosecha_round_trip_json():
    from jobwatch.modelos import Cosecha, EstadoConector, ResultadoConector, Vacante

    v = Vacante(id_nativo="1", portal="computrabajo", titulo="Dev", empresa="ACME",
                ubicacion="Bogotá", url="https://x/1")
    c = Cosecha(
        run_id="abcd1234", tope=50,
        estados={"computrabajo": ResultadoConector(estado=EstadoConector.OK, detalle="")},
        candidatas=[v],
    )
    reconstruida = Cosecha.model_validate_json(c.model_dump_json())
    assert reconstruida.run_id == "abcd1234"
    assert reconstruida.tope == 50
    assert reconstruida.candidatas[0].id_estable == v.id_estable
    assert reconstruida.estados["computrabajo"].estado is EstadoConector.OK


def test_lote_puntajes_estado_enum():
    from jobwatch.modelos import EstadoOferta, LotePuntajes, Puntaje

    lote = LotePuntajes(run_id="x", puntajes=[
        Puntaje(id_estable="a", estado=EstadoOferta.PUNTUADA, puntaje=80, razon="ok"),
        Puntaje(id_estable="b", estado=EstadoOferta.SIN_PUNTAJE, puntaje=None, razon="no aplica"),
    ])
    assert lote.puntajes[0].puntaje == 80
    assert lote.puntajes[1].puntaje is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/test_modelos.py::test_cosecha_round_trip_json -v`
Expected: FAIL with `ImportError: cannot import name 'Cosecha'`

- [ ] **Step 3: Write minimal implementation**

Al final de `src/jobwatch/modelos.py`:

```python
class Puntaje(BaseModel):
    id_estable: str
    estado: EstadoOferta
    puntaje: int | None = None
    razon: str = ""


class LotePuntajes(BaseModel):
    run_id: str
    puntajes: list[Puntaje] = []


class Cosecha(BaseModel):
    run_id: str
    tope: int
    estados: dict[str, ResultadoConector] = {}
    candidatas: list[Vacante] = []
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/pytest tests/test_modelos.py -v`
Expected: PASS (todos, incluidos los previos)

- [ ] **Step 5: Commit**

```bash
git add src/jobwatch/modelos.py tests/test_modelos.py
git commit -m "feat: seam models Puntaje/LotePuntajes/Cosecha (Plan B §4.0)"
```

---

## Task 2: `nucleo.cosechar` + `run_id` + tope determinista (D15) + mudanza de `colapsar_lote`

**Files:**
- Create: `src/jobwatch/nucleo.py`
- Modify: `src/jobwatch/orquestador.py` (re-exportar `colapsar_lote`/`_prioridad` desde `nucleo`)
- Modify: `tests/test_orquestador.py:2` (import de `colapsar_lote` desde `nucleo`)
- Test: `tests/test_nucleo.py`

**Interfaces:**
- Consumes: `filtro_local` (de `matcher`), `Criterios`/`EstadoConector`/`PRIORIDAD_PORTAL`/`ResultadoConector`/`Vacante`/`Cosecha` (de `modelos`), `Store` (de `store`).
- Produces:
  - `PRIORIDAD_PORTAL`-based `_prioridad(portal: str) -> int`.
  - `colapsar_lote(vacantes: list[Vacante]) -> list[Vacante]` (idéntica semántica a la actual de `orquestador`).
  - `calcular_run_id(candidatas: list[Vacante], fecha: str) -> str` (hash sha256[:8] de `id_estable` ordenados + fecha).
  - `class TopeExcedido(Exception)`.
  - `Conector = Callable[[Criterios], ResultadoConector]`.
  - `cosechar(criterios: Criterios, store, conectores: dict[str, Conector], tope: int, fecha: str) -> Cosecha` — SOLO-LECTURA (no persiste); aplica colapso + `es_nueva` + `filtro_local`; si `len(nuevas) > tope` lanza `TopeExcedido`.

- [ ] **Step 1: Write the failing test**

Crea `tests/test_nucleo.py`:

```python
import pytest

from jobwatch.modelos import Criterios, EstadoConector, ResultadoConector, Vacante
from jobwatch.nucleo import TopeExcedido, calcular_run_id, colapsar_lote, cosechar
from jobwatch.store import Store


def _v(idn, portal="indeed", empresa="ACME", titulo="Dev", ubic="Bogotá"):
    return Vacante(id_nativo=idn, portal=portal, empresa=empresa, titulo=titulo,
                   ubicacion=ubic, url=f"https://{portal}/{idn}")


def _ok(vacantes):
    return lambda c: ResultadoConector(estado=EstadoConector.OK, vacantes=vacantes)


def test_run_id_estable_y_sensible_a_fecha():
    vs = [_v("1"), _v("2")]
    a = calcular_run_id(vs, "2026-07-23")
    assert a == calcular_run_id(list(reversed(vs)), "2026-07-23")  # no depende del orden
    assert a != calcular_run_id(vs, "2026-07-24")                  # sí de la fecha


def test_cosechar_dedup_filtro_y_run_id(tmp_path):
    store = Store(str(tmp_path / "t.db"))
    conectores = {"indeed": _ok([_v("2", titulo="Otro Dev")])}
    cosecha = cosechar(Criterios(terminos="dev"), store, conectores, tope=50, fecha="2026-07-23")
    assert len(cosecha.candidatas) == 1
    assert cosecha.run_id == calcular_run_id(cosecha.candidatas, "2026-07-23")
    assert cosecha.tope == 50
    assert cosecha.estados["indeed"].estado is EstadoConector.OK
    store.cerrar()


def test_cosechar_es_solo_lectura(tmp_path):
    store = Store(str(tmp_path / "t.db"))
    v = _v("9")
    cosechar(Criterios(terminos="dev"), store, {"indeed": _ok([v])}, tope=50, fecha="2026-07-23")
    assert store.es_nueva(v) is True  # NADA persistido en harvest (D13)
    store.cerrar()


def test_cosechar_excluye_ya_vistas(tmp_path):
    store = Store(str(tmp_path / "t.db"))
    store.persistir([_v("1")])
    conectores = {"indeed": _ok([_v("1"), _v("2", titulo="Nueva")])}
    cosecha = cosechar(Criterios(terminos="dev"), store, conectores, tope=50, fecha="2026-07-23")
    assert [v.id_nativo for v in cosecha.candidatas] == ["2"]
    store.cerrar()


def test_cosechar_tope_lanza_antes_de_puntuar(tmp_path):
    store = Store(str(tmp_path / "t.db"))
    muchas = [_v(str(i), titulo=f"Dev {i}") for i in range(5)]
    with pytest.raises(TopeExcedido):
        cosechar(Criterios(terminos="dev"), store, {"indeed": _ok(muchas)}, tope=3, fecha="2026-07-23")
    store.cerrar()


def test_cosechar_backstop_conector_que_lanza(tmp_path):
    store = Store(str(tmp_path / "t.db"))
    def malo(c):
        raise RuntimeError("timeout de red")
    conectores = {"malo": malo, "indeed": _ok([_v("1")])}
    cosecha = cosechar(Criterios(terminos="dev"), store, conectores, tope=50, fecha="2026-07-23")
    assert cosecha.estados["malo"].estado is EstadoConector.ERROR
    assert "timeout de red" in cosecha.estados["malo"].detalle
    assert len(cosecha.candidatas) == 1
    store.cerrar()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/test_nucleo.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'jobwatch.nucleo'`

- [ ] **Step 3: Write minimal implementation**

Crea `src/jobwatch/nucleo.py`:

```python
from __future__ import annotations

import hashlib
from typing import Callable

from jobwatch.matcher import filtro_local
from jobwatch.modelos import (
    Cosecha,
    Criterios,
    EstadoConector,
    PRIORIDAD_PORTAL,
    ResultadoConector,
    Vacante,
)

Conector = Callable[[Criterios], ResultadoConector]


class TopeExcedido(Exception):
    pass


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
        canon = min(grupo, key=lambda v: (_prioridad(v.portal), v.portal, v.id_nativo))
        portales = sorted({v.portal for v in grupo}, key=lambda p: (_prioridad(p), p))
        canon.portales = portales
        salida.append(canon)
    return salida


def calcular_run_id(candidatas: list[Vacante], fecha: str) -> str:
    """Hash determinista del conjunto ordenado de id_estable + fecha (§4.1).
    Liga una cosecha a sus puntajes; independiente del orden de las candidatas."""
    ids = "|".join(sorted(v.id_estable for v in candidatas))
    return hashlib.sha256(f"{fecha}|{ids}".encode()).hexdigest()[:8]


def cosechar(
    criterios: Criterios,
    store,
    conectores: dict[str, Conector],
    tope: int,
    fecha: str,
) -> Cosecha:
    """Fase 1, determinista y SOLO-LECTURA (D13): corre conectores, deduplica
    (en-lote + cross-run), filtra localmente, hace cumplir el tope (D15). No persiste."""
    estados: dict[str, ResultadoConector] = {}
    cosechadas: list[Vacante] = []
    for nombre, conector in conectores.items():
        try:
            r = conector(criterios)
        except Exception as e:  # fail-loud sin abortar la corrida (D2)
            r = ResultadoConector(estado=EstadoConector.ERROR, detalle=str(e))
        estados[nombre] = r
        cosechadas.extend(r.vacantes)

    nuevas = [
        v for v in colapsar_lote(cosechadas)
        if store.es_nueva(v) and filtro_local(v, criterios)
    ]
    if len(nuevas) > tope:
        raise TopeExcedido(
            f"tope excedido: {len(nuevas)} > {tope}; revisa el filtro local "
            f"antes de involucrar al LLM."
        )
    return Cosecha(
        run_id=calcular_run_id(nuevas, fecha),
        tope=tope,
        estados=estados,
        candidatas=nuevas,
    )
```

En `src/jobwatch/orquestador.py`, reemplaza las definiciones locales de `_prioridad` y `colapsar_lote` (líneas 13-30) por una re-exportación desde `nucleo` para no romper imports externos:

```python
from jobwatch.nucleo import Conector, TopeExcedido, calcular_run_id, colapsar_lote, cosechar  # noqa: F401
```

(Deja `correr` como está por ahora; se reescribe en la Tarea 5. Elimina el `from jobwatch.matcher import filtro_local, puntuar` que ya no usa directamente si queda huérfano tras la Tarea 5 — por ahora `correr` sigue usándolo, no lo toques aún.)

En `tests/test_orquestador.py` línea 2, cambia el import:

```python
from jobwatch.orquestador import correr
from jobwatch.nucleo import colapsar_lote
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/pytest tests/test_nucleo.py tests/test_orquestador.py -v`
Expected: PASS (nucleo nuevos + orquestador existentes verdes)

- [ ] **Step 5: Commit**

```bash
git add src/jobwatch/nucleo.py src/jobwatch/orquestador.py tests/test_nucleo.py tests/test_orquestador.py
git commit -m "feat: nucleo.cosechar (read-only harvest) + run_id + tope en el core (D13/D15)"
```

---

## Task 3: `nucleo.validar_scores` — fail-loud de la costura agente↔paquete (D14)

**Files:**
- Modify: `src/jobwatch/nucleo.py`
- Test: `tests/test_nucleo.py`

**Interfaces:**
- Consumes: `Cosecha`, `LotePuntajes`, `Puntaje`, `OfertaPuntuada`, `EstadoOferta` (de `modelos`).
- Produces:
  - `class ScoresInvalidos(Exception)`.
  - `validar_scores(cosecha: Cosecha, lote: LotePuntajes) -> list[OfertaPuntuada]` — aborta con `ScoresInvalidos` si (1) `lote.run_id != cosecha.run_id`, (2) el conjunto de `id_estable` de `lote` ≠ el de `cosecha.candidatas` (faltante o inventado), (3) algún `puntaje` de una `PUNTUADA` cae fuera de `0–100`. Si valida, une cada candidata con su `Puntaje` y devuelve `list[OfertaPuntuada]` (incluye `sin_puntaje`).

- [ ] **Step 1: Write the failing test**

Añade a `tests/test_nucleo.py`:

```python
def _cosecha_de(vs, fecha="2026-07-23"):
    from jobwatch.modelos import Cosecha
    return Cosecha(run_id=calcular_run_id(vs, fecha), tope=50, estados={}, candidatas=vs)


def test_validar_scores_ok_incluye_sin_puntaje():
    from jobwatch.modelos import EstadoOferta, LotePuntajes, Puntaje
    from jobwatch.nucleo import validar_scores

    a, b = _v("1"), _v("2", titulo="Otro")
    cosecha = _cosecha_de([a, b])
    lote = LotePuntajes(run_id=cosecha.run_id, puntajes=[
        Puntaje(id_estable=a.id_estable, estado=EstadoOferta.PUNTUADA, puntaje=78, razon="encaja"),
        Puntaje(id_estable=b.id_estable, estado=EstadoOferta.SIN_PUNTAJE, puntaje=None, razon="no aplica"),
    ])
    ofertas = validar_scores(cosecha, lote)
    por_id = {o.vacante.id_estable: o for o in ofertas}
    assert por_id[a.id_estable].puntaje == 78
    assert por_id[b.id_estable].estado is EstadoOferta.SIN_PUNTAJE


def test_validar_scores_run_id_desalineado():
    from jobwatch.modelos import EstadoOferta, LotePuntajes, Puntaje
    from jobwatch.nucleo import ScoresInvalidos, validar_scores

    a = _v("1")
    cosecha = _cosecha_de([a])
    lote = LotePuntajes(run_id="viejo000", puntajes=[
        Puntaje(id_estable=a.id_estable, estado=EstadoOferta.PUNTUADA, puntaje=50)])
    with pytest.raises(ScoresInvalidos, match="run_id"):
        validar_scores(cosecha, lote)


def test_validar_scores_falta_una_candidata():
    from jobwatch.modelos import EstadoOferta, LotePuntajes, Puntaje
    from jobwatch.nucleo import ScoresInvalidos, validar_scores

    a, b = _v("1"), _v("2", titulo="Otro")
    cosecha = _cosecha_de([a, b])
    lote = LotePuntajes(run_id=cosecha.run_id, puntajes=[
        Puntaje(id_estable=a.id_estable, estado=EstadoOferta.PUNTUADA, puntaje=50)])
    with pytest.raises(ScoresInvalidos):
        validar_scores(cosecha, lote)


def test_validar_scores_id_inventado():
    from jobwatch.modelos import EstadoOferta, LotePuntajes, Puntaje
    from jobwatch.nucleo import ScoresInvalidos, validar_scores

    a = _v("1")
    cosecha = _cosecha_de([a])
    lote = LotePuntajes(run_id=cosecha.run_id, puntajes=[
        Puntaje(id_estable=a.id_estable, estado=EstadoOferta.PUNTUADA, puntaje=50),
        Puntaje(id_estable="fantasma", estado=EstadoOferta.PUNTUADA, puntaje=50)])
    with pytest.raises(ScoresInvalidos):
        validar_scores(cosecha, lote)


def test_validar_scores_puntaje_fuera_de_rango():
    from jobwatch.modelos import EstadoOferta, LotePuntajes, Puntaje
    from jobwatch.nucleo import ScoresInvalidos, validar_scores

    a = _v("1")
    cosecha = _cosecha_de([a])
    lote = LotePuntajes(run_id=cosecha.run_id, puntajes=[
        Puntaje(id_estable=a.id_estable, estado=EstadoOferta.PUNTUADA, puntaje=150)])
    with pytest.raises(ScoresInvalidos, match="0.*100|rango"):
        validar_scores(cosecha, lote)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/test_nucleo.py -k validar_scores -v`
Expected: FAIL with `ImportError: cannot import name 'validar_scores'`

- [ ] **Step 3: Write minimal implementation**

Añade a `src/jobwatch/nucleo.py` (import y funciones):

```python
from jobwatch.modelos import (  # amplía el import existente
    Cosecha,
    Criterios,
    EstadoConector,
    EstadoOferta,
    LotePuntajes,
    OfertaPuntuada,
    PRIORIDAD_PORTAL,
    ResultadoConector,
    Vacante,
)


class ScoresInvalidos(Exception):
    pass


def validar_scores(cosecha: Cosecha, lote: LotePuntajes) -> list[OfertaPuntuada]:
    """Fail-loud (D14): exige run_id igual, cobertura TOTAL de id_estable (ni
    faltantes ni inventadas) y puntaje ∈ 0–100 en las puntuadas. Aborta si no."""
    if lote.run_id != cosecha.run_id:
        raise ScoresInvalidos(
            f"run_id desalineado: scores={lote.run_id!r} != candidatas={cosecha.run_id!r}"
        )

    ids_candidatas = {v.id_estable for v in cosecha.candidatas}
    ids_scores = {p.id_estable for p in lote.puntajes}
    if ids_scores != ids_candidatas:
        faltan = ids_candidatas - ids_scores
        sobran = ids_scores - ids_candidatas
        raise ScoresInvalidos(f"cobertura incompleta: faltan={faltan} inventadas={sobran}")

    por_id = {p.id_estable: p for p in lote.puntajes}
    for p in lote.puntajes:
        if p.estado is EstadoOferta.PUNTUADA:
            if p.puntaje is None or not (0 <= p.puntaje <= 100):
                raise ScoresInvalidos(
                    f"puntaje fuera de rango 0–100 para {p.id_estable}: {p.puntaje}"
                )

    ofertas: list[OfertaPuntuada] = []
    for v in cosecha.candidatas:
        p = por_id[v.id_estable]
        ofertas.append(OfertaPuntuada(
            vacante=v, estado=p.estado, puntaje=p.puntaje, razon=p.razon,
        ))
    return ofertas
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/pytest tests/test_nucleo.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/jobwatch/nucleo.py tests/test_nucleo.py
git commit -m "feat: nucleo.validar_scores fail-loud del scoring (D14)"
```

---

## Task 4: `nucleo.reportar` — persiste TODAS las candidatas + renderiza (D12/D13)

**Files:**
- Modify: `src/jobwatch/nucleo.py`
- Test: `tests/test_nucleo.py`

**Interfaces:**
- Consumes: `render` (de `reporte`), `Store.persistir`/`registrar_corrida` (de `store`), `Cosecha`, `OfertaPuntuada`.
- Produces:
  - `reportar(cosecha: Cosecha, ofertas: list[OfertaPuntuada], store, fecha: str) -> str` — persiste **todas** las candidatas (puntuadas y `sin_puntaje`), registra la corrida con `estados`+`detalle`, y devuelve el Markdown de `render(fecha, cosecha.estados, ofertas)`.

- [ ] **Step 1: Write the failing test**

Añade a `tests/test_nucleo.py`:

```python
def test_reportar_persiste_todas_y_renderiza(tmp_path):
    from jobwatch.modelos import EstadoOferta, LotePuntajes, Puntaje
    from jobwatch.nucleo import reportar, validar_scores
    from jobwatch.store import Store

    a, b = _v("1", titulo="Gerente"), _v("2", titulo="Analista")
    cosecha = _cosecha_de([a, b])
    lote = LotePuntajes(run_id=cosecha.run_id, puntajes=[
        Puntaje(id_estable=a.id_estable, estado=EstadoOferta.PUNTUADA, puntaje=90, razon="top"),
        Puntaje(id_estable=b.id_estable, estado=EstadoOferta.SIN_PUNTAJE, razon="fuera"),
    ])
    ofertas = validar_scores(cosecha, lote)
    store = Store(str(tmp_path / "t.db"))
    md = reportar(cosecha, ofertas, store, "2026-07-23")
    # ambas persistidas (incluida la sin_puntaje) -> ya no son nuevas
    assert store.es_nueva(a) is False and store.es_nueva(b) is False
    assert "2026-07-23" in md and "Gerente" in md and "Analista" in md
    store.cerrar()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/test_nucleo.py::test_reportar_persiste_todas_y_renderiza -v`
Expected: FAIL with `ImportError: cannot import name 'reportar'`

- [ ] **Step 3: Write minimal implementation**

Añade a `src/jobwatch/nucleo.py`:

```python
from jobwatch.reporte import render  # junto a los otros imports del módulo


def reportar(cosecha: Cosecha, ofertas: list[OfertaPuntuada], store, fecha: str) -> str:
    """Fase 3, determinista: persiste TODAS las candidatas (puntuadas + sin_puntaje,
    D13) con el hecho multi-portal, registra la corrida con detalle, y renderiza."""
    store.persistir(cosecha.candidatas)
    store.registrar_corrida(cosecha.estados)
    return render(fecha, cosecha.estados, ofertas)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/pytest tests/test_nucleo.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/jobwatch/nucleo.py tests/test_nucleo.py
git commit -m "feat: nucleo.reportar persiste todas las candidatas + renderiza (D12/D13)"
```

---

## Task 5: `puntuar_en_proceso` + refactor de `run` sobre el core (§4.4/D8) — retirar `matcher.puntuar`

**Files:**
- Modify: `src/jobwatch/nucleo.py` (añade `puntuar_en_proceso` + `PuntuadorLLM`)
- Modify: `src/jobwatch/matcher.py` (retira `puntuar`/`TopeExcedido`/`PuntuadorLLM`; deja `filtro_local`)
- Modify: `src/jobwatch/orquestador.py` (`correr` reescrito sobre el core)
- Delete: `tests/test_matcher_puntuar.py`
- Test: `tests/test_nucleo.py`, `tests/test_orquestador.py`

**Interfaces:**
- Consumes: `Cosecha`, `LotePuntajes`, `Puntaje`, `EstadoOferta`, `cosechar`, `validar_scores`, `reportar`.
- Produces:
  - `PuntuadorLLM = Callable[[Vacante, str], dict]` (en `nucleo`).
  - `puntuar_en_proceso(cosecha: Cosecha, cv: str, puntuador: PuntuadorLLM) -> LotePuntajes` — puntúa cada candidata vía el callable; error por-oferta → `Puntaje(estado=SIN_PUNTAJE, razon=str(e))` (fail-loud por oferta, no aborta el lote).
  - `correr(criterios, cv, store, puntuador, conectores, fecha, tope=50) -> tuple[str, dict[str, ResultadoConector]]` — misma firma que Plan A, ahora `cosechar → puntuar_en_proceso → validar_scores → reportar`.

- [ ] **Step 1: Write the failing test**

Añade a `tests/test_nucleo.py`:

```python
def test_puntuar_en_proceso_error_por_oferta_no_aborta():
    from jobwatch.modelos import EstadoOferta
    from jobwatch.nucleo import puntuar_en_proceso

    a, b, c = _v("1"), _v("2", titulo="B"), _v("3", titulo="C")
    cosecha = _cosecha_de([a, b, c])
    def flaky(v, cv):
        if v.id_nativo == "2":
            raise RuntimeError("timeout")
        return {"puntaje": 60, "razon": "ok"}
    lote = puntuar_en_proceso(cosecha, "cv", flaky)
    assert lote.run_id == cosecha.run_id
    por_id = {p.id_estable: p for p in lote.puntajes}
    assert por_id[a.id_estable].estado is EstadoOferta.PUNTUADA
    assert por_id[b.id_estable].estado is EstadoOferta.SIN_PUNTAJE  # el fallo cae a sin_puntaje
```

Los tests de `correr` en `tests/test_orquestador.py` (solo puntua nuevas, error propaga, backstop, colapsa entre conectores) ya cubren el refactor: deben seguir verdes sin cambios de aserción tras esta tarea.

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/test_nucleo.py::test_puntuar_en_proceso_error_por_oferta_no_aborta -v`
Expected: FAIL with `ImportError: cannot import name 'puntuar_en_proceso'`

- [ ] **Step 3: Write minimal implementation**

En `src/jobwatch/nucleo.py` añade (tras `validar_scores`):

```python
from jobwatch.modelos import Puntaje  # amplía el import de modelos con Puntaje

PuntuadorLLM = Callable[[Vacante, str], dict]


def puntuar_en_proceso(cosecha: Cosecha, cv: str, puntuador: PuntuadorLLM) -> LotePuntajes:
    """Ruta API-key (§4.4): puntúa cada candidata con el callable del SDK y arma
    el LotePuntajes que luego valida validar_scores. Fail-loud por oferta."""
    puntajes: list[Puntaje] = []
    for v in cosecha.candidatas:
        try:
            r = puntuador(v, cv)
            puntajes.append(Puntaje(
                id_estable=v.id_estable, estado=EstadoOferta.PUNTUADA,
                puntaje=int(r["puntaje"]), razon=str(r.get("razon", "")),
            ))
        except Exception as e:  # no aborta el lote
            puntajes.append(Puntaje(
                id_estable=v.id_estable, estado=EstadoOferta.SIN_PUNTAJE, razon=str(e),
            ))
    return LotePuntajes(run_id=cosecha.run_id, puntajes=puntajes)
```

Reescribe `src/jobwatch/orquestador.py` completo:

```python
from __future__ import annotations

from jobwatch.modelos import Criterios, ResultadoConector
from jobwatch.nucleo import (  # noqa: F401  (re-export para compat)
    Conector,
    PuntuadorLLM,
    TopeExcedido,
    calcular_run_id,
    colapsar_lote,
    cosechar,
    puntuar_en_proceso,
    reportar,
    validar_scores,
)


def correr(
    criterios: Criterios,
    cv: str,
    store,
    puntuador,
    conectores: dict[str, "Conector"],
    fecha: str,
    tope: int = 50,
) -> tuple[str, dict[str, ResultadoConector]]:
    """Ruta API-key sobre el core: un solo pipeline, dos puntos de entrada (§4.4)."""
    cosecha = cosechar(criterios, store, conectores, tope, fecha)
    lote = puntuar_en_proceso(cosecha, cv, puntuador)
    ofertas = validar_scores(cosecha, lote)
    md = reportar(cosecha, ofertas, store, fecha)
    return md, cosecha.estados
```

Reduce `src/jobwatch/matcher.py` a solo `filtro_local` (borra `PuntuadorLLM`, `TopeExcedido`, `puntuar`):

```python
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

Borra el test obsoleto:

```bash
git rm tests/test_matcher_puntuar.py
```

- [ ] **Step 4: Run the full suite**

Run: `.venv/bin/pytest -q && .venv/bin/ruff check src tests`
Expected: PASS, 0 errores de ruff. (Verifica que `test_orquestador.py` sigue verde: el refactor preserva comportamiento.)

- [ ] **Step 5: Commit**

```bash
git add src/jobwatch/nucleo.py src/jobwatch/orquestador.py src/jobwatch/matcher.py tests/
git commit -m "refactor: run sobre el core (cosechar→puntuar→validar→reportar); retira matcher.puntuar (§4.4/D8)"
```

---

## Task 6: `config.cargar_criterios` (§4.6)

**Files:**
- Create: `src/jobwatch/config.py`
- Test: `tests/test_config.py`

**Interfaces:**
- Consumes: `Criterios` (de `modelos`).
- Produces: `cargar_criterios(ruta: str) -> Criterios` — lee un JSON y lo deserializa a `Criterios` (términos, ubicación, modalidad, salario_min, excluir). El mismo archivo sirve a `harvest`/`run` y a la ruta cron.

- [ ] **Step 1: Write the failing test**

Crea `tests/test_config.py`:

```python
import json

from jobwatch.config import cargar_criterios
from jobwatch.modelos import Modalidad


def test_cargar_criterios_completo(tmp_path):
    ruta = tmp_path / "c.json"
    ruta.write_text(json.dumps({
        "terminos": "Gerente de Proyectos TI",
        "ubicacion": "Colombia",
        "modalidad": "remoto",
        "salario_min": 5000000,
        "excluir": ["ventas"],
    }), encoding="utf-8")
    c = cargar_criterios(str(ruta))
    assert c.terminos == "Gerente de Proyectos TI"
    assert c.modalidad is Modalidad.REMOTO
    assert c.excluir == ["ventas"]


def test_cargar_criterios_minimo(tmp_path):
    ruta = tmp_path / "c.json"
    ruta.write_text(json.dumps({"terminos": "dev"}), encoding="utf-8")
    c = cargar_criterios(str(ruta))
    assert c.terminos == "dev" and c.ubicacion is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/test_config.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'jobwatch.config'`

- [ ] **Step 3: Write minimal implementation**

Crea `src/jobwatch/config.py`:

```python
from __future__ import annotations

from pathlib import Path

from jobwatch.modelos import Criterios


def cargar_criterios(ruta: str) -> Criterios:
    """Deserializa un archivo JSON de configuración a Criterios (§4.6).
    Compartido por la skill (harvest) y la ruta cron (run)."""
    texto = Path(ruta).read_text(encoding="utf-8")
    return Criterios.model_validate_json(texto)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/pytest tests/test_config.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/jobwatch/config.py tests/test_config.py
git commit -m "feat: config.cargar_criterios (--config, §4.6)"
```

---

## Task 7: CLI `harvest` — solo-lectura, emite candidatas JSON (§4.1)

**Files:**
- Modify: `src/jobwatch/cli.py`
- Test: `tests/test_cli_harvest.py`

**Interfaces:**
- Consumes: `cargar_criterios`, `cosechar`, `TopeExcedido`, los cuatro conectores, `Store`.
- Produces: subcomando `jobwatch harvest --config <f> [--db <f>] [--tope N] --json` que imprime a stdout el JSON `{run_id, tope, estados:{portal:{estado,detalle}}, candidatas:[Vacante...]}` y no toca la BD. Con tope excedido: imprime `{"error": "..."}` y retorna 1. Testeable inyectando `conectores` vía un parámetro `_conectores` opcional de `main` para no golpear la red.

- [ ] **Step 1: Write the failing test**

Crea `tests/test_cli_harvest.py`:

```python
import json

from jobwatch.cli import main
from jobwatch.modelos import EstadoConector, ResultadoConector, Vacante


def _config(tmp_path):
    ruta = tmp_path / "c.json"
    ruta.write_text(json.dumps({"terminos": "dev"}), encoding="utf-8")
    return str(ruta)


def _conectores_falsos():
    v = Vacante(id_nativo="1", portal="computrabajo", titulo="Dev", empresa="ACME",
                ubicacion="Bogotá", url="https://x/1")
    return {"computrabajo": lambda c: ResultadoConector(estado=EstadoConector.OK, vacantes=[v])}


def test_harvest_emite_json_y_no_toca_bd(tmp_path, capsys):
    db = str(tmp_path / "j.db")
    rc = main([
        "harvest", "--config", _config(tmp_path), "--db", db, "--json",
    ], _conectores=_conectores_falsos())
    assert rc == 0
    salida = json.loads(capsys.readouterr().out)
    assert salida["tope"] == 50
    assert salida["estados"]["computrabajo"]["estado"] == "ok"
    assert len(salida["candidatas"]) == 1
    assert salida["candidatas"][0]["titulo"] == "Dev"
    # solo-lectura: reabrir el store lo ve como nuevo
    from jobwatch.store import Store
    s = Store(db)
    assert s.es_nueva(Vacante(**salida["candidatas"][0])) is True
    s.cerrar()


def test_harvest_tope_excedido_error_json(tmp_path, capsys):
    def muchos(c):
        vs = [Vacante(id_nativo=str(i), portal="computrabajo", titulo=f"Dev {i}",
                      empresa="ACME", ubicacion="Bogotá", url=f"https://x/{i}") for i in range(4)]
        return ResultadoConector(estado=EstadoConector.OK, vacantes=vs)
    rc = main([
        "harvest", "--config", _config(tmp_path), "--db", str(tmp_path / "j.db"),
        "--tope", "2", "--json",
    ], _conectores={"computrabajo": muchos})
    assert rc == 1
    assert "error" in json.loads(capsys.readouterr().out)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/test_cli_harvest.py -v`
Expected: FAIL (argparse rechaza `harvest` / `main` no acepta `_conectores`)

- [ ] **Step 3: Write minimal implementation**

En `src/jobwatch/cli.py`, cambia la firma de `main` y añade el subcomando. Firma:

```python
def main(argv: list[str] | None = None, _conectores: dict | None = None) -> int:
```

Registro del subcomando (junto a los `sub.add_parser` existentes):

```python
    p_harvest = sub.add_parser("harvest", help="Cosecha candidatas (solo-lectura) y emite JSON.")
    p_harvest.add_argument("--config", required=True)
    p_harvest.add_argument("--db", default="jobwatch.db")
    p_harvest.add_argument("--tope", type=int, default=50)
    p_harvest.add_argument("--json", action="store_true", help="Emite JSON a stdout.")
```

Helper para los conectores reales (evita duplicar el dict; reutilizable por `run`):

```python
def _conectores_reales() -> dict:
    from jobwatch.conectores import computrabajo, elempleo, indeed, magneto
    return {
        "computrabajo": computrabajo.buscar,
        "elempleo": elempleo.buscar,
        "magneto": magneto.buscar,
        "indeed": indeed.buscar,
    }
```

Rama del comando (antes de `return 1`):

```python
    if args.cmd == "harvest":
        import datetime as _dt
        import json as _json

        from jobwatch.config import cargar_criterios
        from jobwatch.nucleo import TopeExcedido, cosechar
        from jobwatch.store import Store

        criterios = cargar_criterios(args.config)
        conectores = _conectores if _conectores is not None else _conectores_reales()
        store = Store(args.db)
        fecha = _dt.date.today().isoformat()
        try:
            cosecha = cosechar(criterios, store, conectores, args.tope, fecha)
        except TopeExcedido as e:
            store.cerrar()
            print(_json.dumps({"error": str(e)}, ensure_ascii=False))
            return 1
        store.cerrar()

        salida = {
            "run_id": cosecha.run_id,
            "tope": cosecha.tope,
            "estados": {
                p: {"estado": r.estado.value, "detalle": r.detalle}
                for p, r in cosecha.estados.items()
            },
            "candidatas": [_json.loads(v.model_dump_json()) for v in cosecha.candidatas],
        }
        print(_json.dumps(salida, ensure_ascii=False, indent=2))
        return 0
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/pytest tests/test_cli_harvest.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/jobwatch/cli.py tests/test_cli_harvest.py
git commit -m "feat: CLI harvest (solo-lectura, emite candidatas JSON, tope) (§4.1)"
```

---

## Task 8: CLI `report` — validación fail-loud, persiste y renderiza (§4.3)

**Files:**
- Modify: `src/jobwatch/cli.py`
- Test: `tests/test_cli_report.py`

**Interfaces:**
- Consumes: `Cosecha`/`LotePuntajes`/`ResultadoConector`/`EstadoConector`/`Vacante`, `validar_scores`, `reportar`, `ScoresInvalidos`, `Store`.
- Produces: subcomando `jobwatch report --candidatas <f> --scores <f> [--fecha AAAA-MM-DD] [--db <f>]`. Reconstruye la `Cosecha` desde `candidatas.json`, arma `LotePuntajes` desde `scores.json`, llama `validar_scores` (aborta con exit 1 + mensaje a stderr si falla), y si valida: `reportar` + escribe `reportes/AAAA-MM-DD.md` + imprime la ruta.

- [ ] **Step 1: Write the failing test**

Crea `tests/test_cli_report.py`:

```python
import json

from jobwatch.cli import main
from jobwatch.modelos import EstadoConector, ResultadoConector, Vacante
from jobwatch.nucleo import calcular_run_id


def _preparar(tmp_path, run_id_scores=None):
    v = Vacante(id_nativo="1", portal="computrabajo", titulo="Gerente", empresa="ACME",
                ubicacion="Bogotá", url="https://x/1")
    run_id = calcular_run_id([v], "2026-07-23")
    candidatas = tmp_path / "cand.json"
    candidatas.write_text(json.dumps({
        "run_id": run_id, "tope": 50,
        "estados": {"computrabajo": {"estado": "ok", "detalle": ""}},
        "candidatas": [json.loads(v.model_dump_json())],
    }), encoding="utf-8")
    scores = tmp_path / "scores.json"
    scores.write_text(json.dumps({
        "run_id": run_id_scores or run_id,
        "puntajes": [{"id_estable": v.id_estable, "estado": "puntuada",
                      "puntaje": 88, "razon": "encaja"}],
    }), encoding="utf-8")
    return str(candidatas), str(scores), v


def test_report_valida_persiste_y_escribe(tmp_path, capsys, monkeypatch):
    monkeypatch.chdir(tmp_path)
    cand, scores, v = _preparar(tmp_path)
    db = str(tmp_path / "j.db")
    rc = main(["report", "--candidatas", cand, "--scores", scores,
               "--fecha", "2026-07-23", "--db", db])
    assert rc == 0
    reporte = tmp_path / "reportes" / "2026-07-23.md"
    assert reporte.exists() and "Gerente" in reporte.read_text(encoding="utf-8")
    from jobwatch.store import Store
    s = Store(db)
    assert s.es_nueva(v) is False  # persistida
    s.cerrar()


def test_report_run_id_desalineado_aborta(tmp_path, capsys):
    cand, scores, _ = _preparar(tmp_path, run_id_scores="viejo000")
    rc = main(["report", "--candidatas", cand, "--scores", scores,
               "--db", str(tmp_path / "j.db")])
    assert rc == 1
    assert "run_id" in capsys.readouterr().err
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/test_cli_report.py -v`
Expected: FAIL (argparse rechaza `report`)

- [ ] **Step 3: Write minimal implementation**

En `src/jobwatch/cli.py`, registra el subcomando:

```python
    p_report = sub.add_parser("report", help="Valida puntajes y escribe el reporte.")
    p_report.add_argument("--candidatas", required=True)
    p_report.add_argument("--scores", required=True)
    p_report.add_argument("--fecha", default=None)
    p_report.add_argument("--db", default="jobwatch.db")
```

Rama del comando:

```python
    if args.cmd == "report":
        import datetime as _dt
        import json as _json

        from jobwatch.modelos import (
            Cosecha, EstadoConector, LotePuntajes, ResultadoConector, Vacante,
        )
        from jobwatch.nucleo import ScoresInvalidos, reportar, validar_scores
        from jobwatch.store import Store

        cand = _json.loads(Path(args.candidatas).read_text(encoding="utf-8"))
        estados = {
            p: ResultadoConector(estado=EstadoConector(e["estado"]), detalle=e.get("detalle", ""))
            for p, e in cand["estados"].items()
        }
        cosecha = Cosecha(
            run_id=cand["run_id"], tope=cand["tope"], estados=estados,
            candidatas=[Vacante(**v) for v in cand["candidatas"]],
        )
        lote = LotePuntajes.model_validate_json(Path(args.scores).read_text(encoding="utf-8"))

        store = Store(args.db)
        try:
            ofertas = validar_scores(cosecha, lote)
        except ScoresInvalidos as e:
            store.cerrar()
            print(f"Error de validación (scores inválidos): {e}", file=sys.stderr)
            return 1

        fecha = args.fecha or _dt.date.today().isoformat()
        md = reportar(cosecha, ofertas, store, fecha)
        store.cerrar()

        destino = Path("reportes") / f"{fecha}.md"
        destino.parent.mkdir(exist_ok=True)
        destino.write_text(md, encoding="utf-8")
        print(f"Reporte escrito en {destino}")
        return 0
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/pytest tests/test_cli_report.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/jobwatch/cli.py tests/test_cli_report.py
git commit -m "feat: CLI report con validación fail-loud (§4.3/D14)"
```

---

## Task 9: CLI `run` — acepta `--config`/`--tope`, sobre el core (§4.4)

**Files:**
- Modify: `src/jobwatch/cli.py`
- Test: `tests/test_cli_report.py` (añade un test de `run` con conectores inyectados y puntuador falso)

**Interfaces:**
- Consumes: `cargar_criterios`, `correr`, `_conectores_reales`/`_conectores`, `Store`.
- Produces: `run` acepta **o** `--config <f>` **o** `--terminos`/`--ubicacion` (mutuamente: si hay `--config`, gana), más `--tope N` (default 50), reusa `--cv`/`--db`. Sigue usando `puntuador_real` (SDK) salvo un `_puntuador` inyectable para tests. Escribe `reportes/AAAA-MM-DD.md`.

- [ ] **Step 1: Write the failing test**

Añade a `tests/test_cli_report.py`:

```python
def test_run_con_config_y_conectores_inyectados(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    cfg = tmp_path / "c.json"
    cfg.write_text(json.dumps({"terminos": "gerente"}), encoding="utf-8")
    cv = tmp_path / "cv.txt"
    cv.write_text("Gerente de proyectos con 10 años.", encoding="utf-8")
    v = Vacante(id_nativo="1", portal="computrabajo", titulo="Gerente", empresa="ACME",
                ubicacion="Bogotá", url="https://x/1")
    conectores = {"computrabajo": lambda c: ResultadoConector(estado=EstadoConector.OK, vacantes=[v])}
    rc = main(
        ["run", "--config", str(cfg), "--cv", str(cv), "--db", str(tmp_path / "j.db")],
        _conectores=conectores, _puntuador=lambda vac, cv: {"puntaje": 91, "razon": "ok"},
    )
    assert rc == 0
    assert (tmp_path / "reportes").exists()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/test_cli_report.py::test_run_con_config_y_conectores_inyectados -v`
Expected: FAIL (`run` no acepta `--config`; `main` no acepta `_puntuador`)

- [ ] **Step 3: Write minimal implementation**

Amplía la firma de `main`:

```python
def main(argv: list[str] | None = None, _conectores: dict | None = None,
         _puntuador=None) -> int:
```

En el parser de `run`, haz `--terminos` opcional y añade `--config`/`--tope`:

```python
    p_run.add_argument("--terminos", default=None)
    p_run.add_argument("--config", default=None)
    p_run.add_argument("--tope", type=int, default=50)
```

Reescribe la rama `run` para usar `--config` o `--terminos`, el core y las inyecciones:

```python
    if args.cmd == "run":
        from jobwatch.config import cargar_criterios
        from jobwatch.llm import puntuador_real
        from jobwatch.modelos import Criterios
        from jobwatch.orquestador import correr
        from jobwatch.store import Store

        if args.config:
            criterios = cargar_criterios(args.config)
        elif args.terminos:
            criterios = Criterios(terminos=args.terminos, ubicacion=args.ubicacion)
        else:
            print("Error: pasa --config o --terminos.", file=sys.stderr)
            return 1

        cv = Path(args.cv).read_text(encoding="utf-8")
        store = Store(args.db)
        conectores = _conectores if _conectores is not None else _conectores_reales()
        puntuador = _puntuador if _puntuador is not None else puntuador_real
        fecha = _dt.date.today().isoformat()
        md, _ = correr(criterios, cv, store, puntuador, conectores, fecha, args.tope)
        store.cerrar()

        destino = Path("reportes") / f"{fecha}.md"
        destino.parent.mkdir(exist_ok=True)
        destino.write_text(md, encoding="utf-8")
        print(f"Reporte escrito en {destino}")
        return 0
```

- [ ] **Step 4: Run the full suite**

Run: `.venv/bin/pytest -q && .venv/bin/ruff check src tests`
Expected: PASS, ruff limpio.

- [ ] **Step 5: Commit**

```bash
git add src/jobwatch/cli.py tests/test_cli_report.py
git commit -m "feat: run acepta --config/--tope sobre el core (§4.4)"
```

---

## Task 10: Bundle de la skill — `SKILL.md` + config de ejemplo + rúbrica (§5)

**Files:**
- Create: `skill/SKILL.md`
- Create: `skill/jobwatch.config.example.json`
- Create: `skill/references/scoring-rubric.md`
- Test: `tests/test_skill_bundle.py`

**Interfaces:**
- Produces: el directorio distribuible de la skill (cero datos personales). `SKILL.md` instruye el flujo de 5 pasos; la config de ejemplo deserializa a `Criterios`; la rúbrica es la referencia 0–100 que Claude aplica al puntuar en contexto.

- [ ] **Step 1: Write the failing test**

Crea `tests/test_skill_bundle.py`:

```python
from pathlib import Path

from jobwatch.config import cargar_criterios

_SKILL = Path(__file__).resolve().parents[1] / "skill"


def test_bundle_existe():
    assert (_SKILL / "SKILL.md").exists()
    assert (_SKILL / "jobwatch.config.example.json").exists()
    assert (_SKILL / "references" / "scoring-rubric.md").exists()


def test_config_ejemplo_deserializa_a_criterios():
    c = cargar_criterios(str(_SKILL / "jobwatch.config.example.json"))
    assert c.terminos  # no vacío


def test_skill_frontmatter_tiene_trigger():
    texto = (_SKILL / "SKILL.md").read_text(encoding="utf-8")
    assert texto.startswith("---")
    assert "name: jobwatch" in texto
    assert "/jobwatch" in texto  # el trigger aparece en el frontmatter


def test_bundle_sin_datos_personales():
    # Ningún archivo del bundle debe traer un CV ni rutas personales.
    for p in _SKILL.rglob("*"):
        if p.is_file():
            t = p.read_text(encoding="utf-8", errors="ignore").lower()
            assert "juan" not in t and "data/cv.txt" not in t or p.name == "SKILL.md"
```

Nota: `SKILL.md` puede mencionar `data/cv.txt` como instrucción de setup; el resto del bundle no. El test lo exceptúa solo para `SKILL.md`.

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/test_skill_bundle.py -v`
Expected: FAIL (los archivos no existen)

- [ ] **Step 3: Write the bundle files**

`skill/jobwatch.config.example.json`:

```json
{
  "terminos": "Gerente de Proyectos TI",
  "ubicacion": "Colombia",
  "modalidad": "remoto",
  "salario_min": null,
  "excluir": ["ventas", "call center"]
}
```

`skill/references/scoring-rubric.md`:

```markdown
# Rúbrica de puntuación 0–100

Puntúa cada vacante contra el CV del usuario. Devuelve un entero 0–100 y una
razón de una frase. Sé consistente entre corridas: aplica siempre estas bandas.

## Bandas

- **85–100 — Encaje fuerte.** El rol coincide con el título/seniority del CV y la
  mayoría de requisitos clave están cubiertos. Modalidad/ubicación compatibles.
- **60–84 — Buen encaje.** Rol relacionado; varios requisitos cubiertos, algunos
  huecos salvables. Vale la pena postular.
- **30–59 — Encaje débil.** Solapamiento parcial (área correcta, seniority o
  stack distinto). Postular solo si el volumen es bajo.
- **0–29 — Encaje pobre.** Rol, seniority o dominio esencialmente distintos.

## Señales (en orden de peso)

1. **Rol y seniority** — ¿el título y el nivel corresponden a la trayectoria del CV?
2. **Requisitos duros** — herramientas, certificaciones, años de experiencia exigidos.
3. **Dominio/industria** — ¿el sector encaja con la experiencia previa?
4. **Modalidad y ubicación** — remoto/híbrido/presencial vs. lo que busca el CV.
5. **Salario** — si la vacante lo declara y está por debajo del mínimo, baja la banda.

## `sin_puntaje`

Si la vacante no trae información suficiente para juzgar el encaje (descripción
vacía o irrelevante al CV), márcala `estado: "sin_puntaje"`, `puntaje: null`, y
explica por qué en la razón. No la descartes: se reporta igual.
```

`skill/SKILL.md`:

```markdown
---
name: jobwatch
description: "Agrega ofertas de empleo de portales colombianos, deduplica, puntúa contra tu CV y reporta solo lo nuevo — desde Claude Code, sin API key. Trigger: /jobwatch"
---

# /jobwatch

Corre el agregador de empleos jobwatch desde tu sesión de Claude Code. El motor
determinista (conectores, dedup, store, reporte) es el paquete Python `jobwatch`;
tú (Claude) haces el único paso que necesita un LLM: **puntuar las candidatas
contra el CV del usuario**. Sin API key.

## Pre-vuelo

1. ¿Está instalado el CLI? Corre `jobwatch --help`. Si falla, instruye al usuario:
   `pipx install jobwatch` (o `pipx install git+https://github.com/juanurreamurillo/jobwatch`).
2. ¿Existe `jobwatch.config.json` en el directorio actual? Si no, copia la
   plantilla `jobwatch.config.example.json` de esta skill y pide al usuario que
   ajuste términos/ubicación/modalidad.
3. ¿Existe `data/cv.txt`? Si no, pide al usuario que guarde su CV en texto plano
   ahí (`data/` debe estar en su `.gitignore`).

## Flujo

1. **Cosecha (determinista, solo-lectura):**
   ```
   jobwatch harvest --config jobwatch.config.json --json > candidatas.json
   ```
   Si el comando devuelve `{"error": "tope excedido..."}`, dile al usuario que
   afine el filtro (términos/exclusiones) — hay demasiadas candidatas para puntuar.

2. **Puntúa en contexto.** Lee `data/cv.txt` y las `candidatas` de `candidatas.json`.
   Aplica `references/scoring-rubric.md` (para consistencia entre corridas). Para
   CADA candidata (una por `id_estable`, sin faltar ni inventar ninguna) produce un
   objeto `{id_estable, estado, puntaje, razon}` con `estado` ∈ `puntuada|sin_puntaje`.
   Escribe `scores.json` con la forma:
   ```json
   { "run_id": "<el run_id de candidatas.json>", "puntajes": [ ... ] }
   ```
   Respeta el `run_id` exacto de `candidatas.json` — `report` lo valida.

3. **Reporta (determinista):**
   ```
   jobwatch report --candidatas candidatas.json --scores scores.json
   ```
   Valida fail-loud (run_id, cobertura, rango 0–100), persiste y escribe
   `reportes/AAAA-MM-DD.md`. Si aborta, revisa que `scores.json` cubra todas las
   candidatas con el `run_id` correcto y vuelve a puntuar.

4. **Muestra** la ruta del reporte al usuario. Ofrece redactar una carta para las
   mejores: `jobwatch carta <id_estable> --cv data/cv.txt`.

## Programación (opcional)

Para correr esto en cron, el usuario puede usar `/schedule` de Claude Code sobre
`/jobwatch` (Claude-en-esa-sesión puntúa). Para automatización 100% headless sin
Claude, existe `jobwatch run --config ... --cv data/cv.txt` con `ANTHROPIC_API_KEY`.
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/pytest tests/test_skill_bundle.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add skill/ tests/test_skill_bundle.py
git commit -m "feat: bundle de la skill (SKILL.md + config ejemplo + rúbrica) (§5)"
```

---

## Task 11: Preparación de release a PyPI (D10/§9) + docs

**Files:**
- Modify: `pyproject.toml` (versión + extra `dev` con `build`/`twine`)
- Modify: `docs/HANDOFF.md`, `README.md`
- Test: verificación de build (no TDD; el criterio es "el sdist/wheel se construye").

**Interfaces:**
- Produces: paquete construible y publicable. La subida real (`twine upload`) queda gated en el token de PyPI de Juan (paso manual, documentado, no ejecutado por el agente).

- [ ] **Step 1: Bump de versión y extras de build**

En `pyproject.toml`: sube `version = "0.0.1"` → `version = "0.1.0"`, cambia el clasificador `Development Status :: 1 - Planning` → `Development Status :: 4 - Beta`, y añade a `[project.optional-dependencies].dev`:

```toml
dev = [
    "pytest>=8.0",
    "ruff>=0.5",
    "build>=1.0",
    "twine>=5.0",
]
```

- [ ] **Step 2: Verifica que el paquete se construye**

```bash
.venv/bin/pip install -e ".[dev]"
.venv/bin/python -m build
.venv/bin/twine check dist/*
```
Expected: `dist/jobwatch-0.1.0.tar.gz` y `.whl` creados; `twine check` → `PASSED`.
(Añade `dist/` y `*.egg-info/` a `.gitignore` si no están.)

- [ ] **Step 3: Documenta la publicación (no la ejecutes)**

En `README.md`, sección de instalación, añade:

```markdown
## Instalación

```bash
pipx install jobwatch          # cuando esté publicado en PyPI
# o desde el repo:
pipx install git+https://github.com/juanurreamurillo/jobwatch
```

### Como skill de Claude Code

Instala el paquete (arriba) y la skill del directorio `skill/`. En tu sesión,
`/jobwatch` cosecha, puntúa contra tu CV y reporta — sin API key. Ver
[`skill/SKILL.md`](skill/SKILL.md).
```

En `docs/HANDOFF.md`, actualiza el estado: Plan B completo (core in-process,
`harvest`/`report`/`run` sobre un solo pipeline, validación fail-loud, `--config`,
bundle de skill, release 0.1.0 listo para `twine upload`). El comando de publicación,
para que Juan lo corra con su token:

```bash
.venv/bin/twine upload dist/*   # requiere ~/.pypirc o TWINE_* con el token de PyPI de Juan
```

- [ ] **Step 4: Corre toda la suite + ruff una última vez**

Run: `.venv/bin/pytest -q && .venv/bin/ruff check src tests`
Expected: PASS, ruff limpio.

- [ ] **Step 5: Commit**

```bash
git add pyproject.toml README.md docs/HANDOFF.md .gitignore
git commit -m "chore: release 0.1.0 — build/twine, docs de instalación y skill (D10/§9)"
```

---

## Self-Review (cobertura vs. `docs/design-skill.md`)

- **§4.0 core in-process** (`cosechar`/`validar_scores`/`reportar`) → Tareas 2, 3, 4. ✅
- **§4.1 `harvest` + tope determinista (D15) + run_id** → Tareas 2, 7. ✅
- **§4.2/§4.3 `report` + fail-loud (D14)** → Tareas 3, 8. ✅
- **§4.4 `run` sobre el core (D8)** → Tareas 5, 9. ✅
- **§4.6 `--config`** → Tareas 6, 7, 9. ✅
- **§5 bundle de skill (SKILL.md, config, rúbrica)** → Tarea 10. ✅
- **§6.1 dedup en-lote (D11)** → ya en Plan A; `colapsar_lote` reubicado a `nucleo` (Tarea 2), comportamiento preservado por los tests de `test_orquestador`. ✅
- **§6.2 `detalle` al reporte** → ya en Plan A; `reportar` propaga `cosecha.estados` (Tarea 4). ✅
- **§6.3 migración schema** → ya en Plan A (`store._migrar`); sin cambios. ✅
- **§9/D10 publicar a PyPI** → Tarea 11 (subida gated en token de Juan). ✅
- **D12 paquete renderiza** → Tarea 4 (`reportar` llama `render`; el agente solo puntúa). ✅
- **D13 harvest solo-lectura / report escribe** → Tareas 2 (test read-only), 4, 8. ✅

**Consistencia de tipos:** `Cosecha`/`LotePuntajes`/`Puntaje` (Tarea 1) usados con las mismas firmas en `cosechar`/`validar_scores`/`reportar`/`puntuar_en_proceso` (Tareas 2–5) y reconstruidos idénticamente en el CLI (Tareas 7–9). `PuntuadorLLM`, `TopeExcedido`, `ScoresInvalidos`, `Conector` centralizados en `nucleo` y re-exportados por `orquestador`.

**Sin placeholders:** cada paso trae el código o comando real.
