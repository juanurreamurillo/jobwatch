from __future__ import annotations

import json
import re

from jobwatch.conectores._comun import ejecutar, slug
from jobwatch.modelos import Criterios, Modalidad, ResultadoConector, Vacante
from jobwatch.normalizar import normalizar_ubicacion

HOST = "https://www.magneto365.com"

_PUSH_RE = re.compile(r'self\.__next_f\.push\(\[1,("(?:[^"\\]|\\.)*")\]\)')


def _url(criterios: Criterios, pagina: int = 1) -> str:
    ruta = f"/co/trabajos/buscar/{slug(criterios.terminos)}"
    if pagina > 1:
        ruta += f"/pagina-{pagina}"
    return f"{HOST}{ruta}"


def _reconstruir_flight(html: str) -> str:
    """Concatena los payloads de self.__next_f.push([1,"..."]) decodificando cada
    uno como literal JSON (preserva UTF-8 y \\uXXXX; no rompe multibyte)."""
    trozos = _PUSH_RE.findall(html)
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
        if isinstance(arr, list) and any(
            isinstance(x, dict) and "publishDate" in x for x in arr
        ):
            return [x for x in arr if isinstance(x, dict) and "id" in x]
    return []


def _a_vacante(row: dict) -> Vacante:
    cities = row.get("cities") or []
    pub = str(row.get("publishDate") or "")
    fecha = pub[:10] if pub[:2] == "20" else None
    return Vacante(
        id_nativo=str(row.get("id", "")),
        portal="magneto",
        titulo=str(row.get("title", "")),
        empresa=str(row.get("companyName", "")),
        ubicacion=normalizar_ubicacion(str(cities[0]) if cities else ""),
        modalidad=Modalidad.REMOTO if row.get("isRemote") else Modalidad.DESCONOCIDO,
        salario_raw=str(row.get("salary", "") or ""),
        salario_min=row.get("minSalary"),
        salario_max=row.get("maxSalary"),
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
                omitidas += 1
                continue
            if criterios.modalidad is Modalidad.REMOTO and v.modalidad is not Modalidad.REMOTO:
                continue  # filtro remoto local (server no lo hace en la ruta de término)
            vacantes.append(v)
        except Exception:
            omitidas += 1
    return vacantes, omitidas, len(rows)  # n_crudo = filas crudas del flight


def buscar(criterios: Criterios, fetch=None) -> ResultadoConector:
    return ejecutar(criterios, _url, fetch, _extraer, pausa=1.5)
