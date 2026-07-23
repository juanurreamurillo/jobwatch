from __future__ import annotations

from urllib.parse import urljoin

from bs4 import BeautifulSoup

from jobwatch.conectores._comun import ejecutar, slug, texto
from jobwatch.modelos import Criterios, ResultadoConector, Vacante
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


def _extraer(html: str, criterios: Criterios) -> tuple[list[Vacante], int]:
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
    return vacantes, omitidas


def buscar(criterios: Criterios, fetch=None) -> ResultadoConector:
    return ejecutar(criterios, _url, fetch, _extraer)
