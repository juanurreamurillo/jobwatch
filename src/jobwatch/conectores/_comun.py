from __future__ import annotations

import re

from jobwatch.modelos import Criterios, EstadoConector, ResultadoConector, _clave

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


def ejecutar(criterios: Criterios, url_fn, fetch, extraer) -> ResultadoConector:
    """Envoltorio fail-loud compartido (D2): fetch → try/except → ERROR, o
    extraer(html, criterios) -> (vacantes, omitidas) → OK con detalle."""
    fetch = fetch or fetch_curl
    try:
        html = fetch(url_fn(criterios))
    except Exception as e:  # fail-loud
        return ResultadoConector(estado=EstadoConector.ERROR, detalle=str(e))
    vacantes, omitidas = extraer(html, criterios)
    detalle = f"{omitidas} filas omitidas por datos inválidos" if omitidas else ""
    return ResultadoConector(estado=EstadoConector.OK, vacantes=vacantes, detalle=detalle)
