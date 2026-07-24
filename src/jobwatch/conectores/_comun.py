from __future__ import annotations

import re

from jobwatch.modelos import Criterios, EstadoConector, ResultadoConector, Vacante

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


def _clave_palabras(texto: str) -> str:
    """Como `_clave`, pero los símbolos se vuelven SEPARADOR en vez de desaparecer:
    'Ingeniero/a' -> 'ingeniero a', no 'ingenieroa'. Imprescindible al comparar con
    `\\b…\\b`: pegar palabras rompe el límite y descarta títulos correctos.
    No se corrige `_clave` porque alimenta `calcular_fingerprint`, y cambiarlo haría
    que toda vacante ya vista volviera a parecer nueva."""
    import unicodedata

    sin_acentos = "".join(
        c for c in unicodedata.normalize("NFKD", texto) if not unicodedata.combining(c)
    )
    con_espacios = "".join(c if c.isalnum() else " " for c in sin_acentos.lower())
    return re.sub(r"\s+", " ", con_espacios).strip()


def coincide_termino(titulo: str, terminos: str) -> bool:
    """¿El título comparte AL MENOS UN token distintivo con el término buscado?

    Exigir todos los tokens descartaba coincidencias legítimas: 'Ingeniero IA' para
    'ingeniero inteligencia artificial', o 'Project Manager IT' para 'project manager
    senior' — los portales abrevian y reordenan. Esto es un pre-filtro barato antes de
    la puntuación (README §Cómo funciona), así que prima el recall: una vacante perdida
    es irrecuperable, un falso positivo solo cuesta una puntuación. Medido sobre el
    ruido real del 2026-07-24, la regla de >=1 token sigue cortando el 88%."""
    t = _clave_palabras(titulo)
    toks = [
        w for w in _clave_palabras(terminos).split()
        if len(w) >= 3 and w not in _STOPWORDS
    ]
    if not toks:
        return True
    return any(re.search(rf"\b{re.escape(w)}\b", t) for w in toks)


def _traer_pagina(criterios, url_fn, fetch, extraer, pagina, reintentos, es_fin):
    """Trae y extrae una página, reintentando ante fallo transitorio. Deja escapar
    la última excepción para que `ejecutar` aplique su política fail-loud."""
    intento = 0
    while True:
        try:
            html = fetch(url_fn(criterios, pagina))
            vs, omitidas, n_crudo = extraer(html, criterios)
            return html, vs, omitidas, n_crudo
        except Exception as e:
            if es_fin and es_fin(e):  # respuesta correcta: no gastar reintentos
                raise
            if intento >= reintentos:
                raise
            intento += 1


def ejecutar(
    criterios: Criterios, url_fn, fetch, extraer, max_paginas: int = 50, pausa=None,
    es_fin=None, reintentos: int = 0,
) -> ResultadoConector:
    """Envoltorio fail-loud + paginación (D17). Recorre páginas por `url_fn(c, pagina)`
    (página 1-based) hasta: página con 0 tarjetas crudas (fin normal), error tras la
    pág. 1 (fin + cobertura parcial), o tope de páginas (cobertura parcial). Error en
    la pág. 1 = ERROR. `extraer(html, criterios) -> (vacantes, omitidas, n_crudo)`;
    la parada se decide por `n_crudo == 0` (B1), nunca por `len(vacantes) == 0`, ya
    que una página con tarjetas crudas pero 0 vacantes tras filtrar no implica fin.

    `reintentos` reintenta la MISMA página ante un fallo transitorio. Magneto tiene
    latencia de cola errática en cualquier página (medido 2026-07-24: la misma URL da
    timeout de 45 s y responde en 0,8 s al reintentarla), y sin esto un tropiezo en la
    página 1 tumba el conector entero. El fin de paginación (`es_fin`) NO se reintenta:
    es una respuesta correcta, no un fallo."""
    import time

    fetch = fetch or fetch_curl
    vacantes: list[Vacante] = []
    omitidas_total = 0
    for pagina in range(1, max_paginas + 1):
        try:
            html, vs, omitidas, n_crudo = _traer_pagina(
                criterios, url_fn, fetch, extraer, pagina, reintentos, es_fin
            )
        except Exception as e:  # fail-loud
            if pagina == 1:
                return ResultadoConector(estado=EstadoConector.ERROR, detalle=str(e))
            if es_fin and es_fin(e):  # el portal dice "no hay más", no "me rompí"
                det = (
                    f"{omitidas_total} filas omitidas por datos inválidos"
                    if omitidas_total
                    else ""
                )
                return ResultadoConector(
                    estado=EstadoConector.OK, vacantes=vacantes, detalle=det
                )
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
