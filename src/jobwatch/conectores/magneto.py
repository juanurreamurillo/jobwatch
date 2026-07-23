from __future__ import annotations

from bs4 import BeautifulSoup

from jobwatch.conectores._comun import (
    coincide_termino, ejecutar, id_de_url, texto,
)
from jobwatch.modelos import Criterios, ResultadoConector, Vacante
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


def _extraer(html: str, criterios: Criterios) -> tuple[list[Vacante], int]:
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
    return vacantes, omitidas


def buscar(criterios: Criterios, fetch=None) -> ResultadoConector:
    return ejecutar(criterios, _url, fetch, _extraer)
