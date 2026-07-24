from __future__ import annotations

from urllib.parse import urljoin

from bs4 import BeautifulSoup

from jobwatch.conectores._comun import ejecutar, fetch_curl, slug, texto
from jobwatch.modelos import Criterios, Modalidad, ResultadoConector, Vacante
from jobwatch.normalizar import normalizar_ubicacion, parsear_salario

HOST = "https://co.computrabajo.com"

_PUBDATE = [1, 3, 7, 15]  # ventanas server discretas (descubrimiento)


def _pubdate_para(dias: int | None) -> int | None:
    if dias is None:
        return None
    for v in _PUBDATE:
        if v >= dias:
            return v
    return None


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


_ANCLA_DETALLE = "descripción de la oferta"


def extraer_detalle(html: str) -> str:
    """Descripción desde la página de la oferta. Ancla en el encabezado
    'Descripción de la oferta' y toma su contenedor, en vez de colgarse de clases
    utilitarias (`div.mb40.pb40.bb1`) que cambian con cualquier retoque de estilo.
    El bloque incluye salario, tipo de contrato y modalidad además del cuerpo."""
    sopa = BeautifulSoup(html, "lxml")
    for h in sopa.find_all(["h1", "h2", "h3"]):
        if h.get_text(strip=True).lower().startswith(_ANCLA_DETALLE):
            contenedor = h.find_parent(["div", "section"])
            if contenedor is not None:
                return texto(contenedor)
    return " ".join(texto(p) for p in sopa.select("p.mbB")).strip()


def detalle(url: str, fetch=None) -> str:
    return extraer_detalle((fetch or fetch_curl)(url))


def _a_vacante(art, criterios: Criterios) -> Vacante:
    a = art.select_one("h2 a.js-o-link")
    href = a.get("href", "").split("#")[0] if a else ""
    empresa = art.select_one("a[offer-grid-article-company-url]")
    ubic = art.select_one("p.fs16.fc_base.mt5:not(.dFlex) > span.mr10")
    salario_raw = ""
    if art.select_one("span.i_salary"):
        salario_raw = texto(art.select_one("div.fs13.mt15 span.dIB.mr10"))
    smin, smax = parsear_salario(salario_raw) if salario_raw else (None, None)
    fecha_el = art.select_one("p.fs13.fc_aux")
    fecha_raw = texto(fecha_el) or None  # texto relativo crudo; el core lo normaliza (D22)
    # La modalidad no se raspa de la tarjeta: el server ya filtra por -en-remoto
    # en la URL de búsqueda cuando criterios.modalidad es REMOTO, así que todas
    # las ofertas devueltas en esa ruta son remotas.
    es_remoto = criterios.modalidad is Modalidad.REMOTO
    modalidad = Modalidad.REMOTO if es_remoto else Modalidad.DESCONOCIDO
    return Vacante(
        id_nativo=art.get("data-id", ""),
        portal="computrabajo",
        titulo=texto(a),
        empresa=texto(empresa),
        ubicacion=normalizar_ubicacion(texto(ubic)),
        modalidad=modalidad,
        salario_raw=salario_raw,
        salario_min=smin,
        salario_max=smax,
        url=urljoin(HOST, href),
        fecha_publicacion=fecha_raw,
    )


def _extraer(html: str, criterios: Criterios) -> tuple[list[Vacante], int, int]:
    sopa = BeautifulSoup(html, "lxml")
    arts = sopa.select("article.box_offer")
    vacantes: list[Vacante] = []
    omitidas = 0
    for art in arts:
        try:
            v = _a_vacante(art, criterios)
            if not v.id_nativo or not v.titulo:
                omitidas += 1
                continue
            vacantes.append(v)
        except Exception:
            omitidas += 1
    return vacantes, omitidas, len(arts)  # n_crudo = tarjetas crudas


def buscar(criterios: Criterios, fetch=None) -> ResultadoConector:
    return ejecutar(criterios, _url, fetch, _extraer, pausa=1.0)
