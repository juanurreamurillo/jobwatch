from __future__ import annotations

import re

from jobwatch.modelos import Criterios, EstadoConector, ResultadoConector, Vacante, _clave

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


def ejecutar(
    criterios: Criterios, url_fn, fetch, extraer, max_paginas: int = 50, pausa=None
) -> ResultadoConector:
    """Envoltorio fail-loud + paginación (D17). Recorre páginas por `url_fn(c, pagina)`
    (página 1-based) hasta: página con 0 tarjetas crudas (fin normal), error tras la
    pág. 1 (fin + cobertura parcial), o tope de páginas (cobertura parcial). Error en
    la pág. 1 = ERROR. `extraer(html, criterios) -> (vacantes, omitidas, n_crudo)`;
    la parada se decide por `n_crudo == 0` (B1), nunca por `len(vacantes) == 0`, ya
    que una página con tarjetas crudas pero 0 vacantes tras filtrar no implica fin."""
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
                estado=EstadoConector.OK,
                vacantes=vacantes,
                detalle=f"cobertura parcial: fin en página {pagina} por error: {e}",
            )
        if n_crudo == 0:  # página sin tarjetas crudas = agotado real (B1)
            det = (
                f"{omitidas_total} filas omitidas por datos inválidos"
                if omitidas_total
                else ""
            )
            return ResultadoConector(estado=EstadoConector.OK, vacantes=vacantes, detalle=det)
        vacantes.extend(vs)
        omitidas_total += omitidas
        if pausa:
            time.sleep(pausa)
    return ResultadoConector(
        estado=EstadoConector.OK,
        vacantes=vacantes,
        detalle=f"cobertura parcial: tope de {max_paginas} páginas alcanzado",
    )
