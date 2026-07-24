from __future__ import annotations

import json
import re

from jobwatch.conectores._comun import IMPERSONATE, ejecutar, fetch_curl, slug
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


def extraer_detalle(html: str) -> str:
    """Descripción desde la página de la oferta. A diferencia del listado —que hay
    que reconstruir del flight RSC— el detalle es SSR y publica un
    `schema.org/JobPosting` en `<script type="application/ld+json">`. Es fuente
    estructurada y estándar, así que no depende de ningún selector de DOM.
    Descubrimiento del 2026-07-24: la página no hace ninguna petición JSON propia;
    todo llega con el documento inicial."""
    from bs4 import BeautifulSoup

    sopa = BeautifulSoup(html, "lxml")
    for script in sopa.select('script[type="application/ld+json"]'):
        try:
            datos = json.loads(script.string or "")
        except Exception:
            continue
        for d in datos if isinstance(datos, list) else [datos]:
            if isinstance(d, dict) and d.get("@type") == "JobPosting":
                return " ".join(str(d.get("description") or "").split())
    return ""


MCP = "https://api.magneto365.com/agents/v1/mcp"


def slug_de_url(url: str) -> str:
    """Último segmento de ruta, sin query string. El propio MCP devuelve urls con
    `?utm_source=openai&utm_medium=mcp`."""
    return url.split("?")[0].split("#")[0].rstrip("/").rsplit("/", 1)[-1]


def _post_mcp(payload: dict) -> dict:
    """Un único POST JSON-RPC. Medido 2026-07-24: `tools/call` responde sin
    `initialize` previo y sin `Mcp-Session-Id`, así que no hace falta cliente MCP
    ni dependencia nueva. La respuesta puede venir como SSE (`event: …`), de ahí
    que se busque el primer `{`."""
    from curl_cffi import requests

    r = requests.post(
        MCP, json=payload, impersonate=IMPERSONATE, timeout=30,
        headers={"Accept": "application/json, text/event-stream",
                 "Content-Type": "application/json"},
    )
    r.raise_for_status()
    texto = r.text or ""
    return json.loads(texto[texto.index("{"):])


def _detalle_mcp(url: str, post) -> str:
    """Descripción vía el servidor MCP oficial del portal: ~4 KB y 0,2 s, contra
    846 KB y timeouts de hasta 45 s por la página SSR."""
    respuesta = (post or _post_mcp)({
        "jsonrpc": "2.0", "id": 1, "method": "tools/call",
        "params": {"name": "get_job_detail",
                   "arguments": {"jobSlug": slug_de_url(url)}},
    })
    job = ((respuesta.get("result") or {}).get("structuredContent") or {}).get("job") or {}
    return " ".join(str(job.get("description") or "").split())


def detalle(url: str, fetch=None, post=None) -> str:
    """MCP primero, HTML como respaldo. El MCP es infraestructura de un tercero:
    si cae o cambia, el extractor JSON-LD sigue respondiendo y la corrida no
    pierde la descripción."""
    try:
        descripcion = _detalle_mcp(url, post)
        if descripcion:
            return descripcion
    except Exception:
        pass
    return extraer_detalle((fetch or fetch_curl)(url))


def buscar(criterios: Criterios, fetch=None) -> ResultadoConector:
    # reintentos=1: latencia de cola errática medida en cualquier página
    # (docs/endpoints.md §Fiabilidad del listado de Magneto).
    return ejecutar(criterios, _url, fetch, _extraer, pausa=1.5, reintentos=1)
