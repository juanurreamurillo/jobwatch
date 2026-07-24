from __future__ import annotations

import json

from bs4 import BeautifulSoup

from jobwatch.conectores._comun import ejecutar, fetch_curl, id_de_url, slug
from jobwatch.modelos import Criterios, Modalidad, ResultadoConector, Vacante
from jobwatch.normalizar import normalizar_ubicacion, parsear_salario

HOST = "https://www.elempleo.com"


def _url(criterios: Criterios, pagina: int = 1) -> str:
    ruta = f"/co/ofertas-empleo/trabajo-{slug(criterios.terminos)}"
    if criterios.modalidad is Modalidad.REMOTO:
        ruta += "-modalidad-remoto"
    if pagina > 1:
        ruta += f"/{pagina}"
    qs = "?PublishDate=hoy" if (criterios.dias is not None and criterios.dias <= 2) else ""
    return f"{HOST}{ruta}{qs}"


def _items_jsonld(sopa) -> list[dict]:
    """Items del ItemList: {id, url, name}. Tolera varios bloques JSON-LD."""
    items: list[dict] = []
    for script in sopa.select('script[type="application/ld+json"]'):
        try:
            datos = json.loads(script.string or "")
        except Exception:
            continue
        if not isinstance(datos, dict):
            continue
        if datos.get("@type") != "ItemList":
            continue
        for el in datos.get("itemListElement", []):
            item = el.get("item", {})
            url = item.get("@id", "")
            items.append({"id": id_de_url(url), "url": url, "name": item.get("name", "")})
    return items


def _cards_por_id(sopa) -> dict[str, dict]:
    """Índice id -> JSON de data-ga4-offerdata (title, company, location, salary)."""
    porid: dict[str, dict] = {}
    for div in sopa.select("[data-ga4-offerdata]"):
        try:
            datos = json.loads(div["data-ga4-offerdata"])
            porid[str(datos["id"])] = datos
        except Exception:
            continue
    return porid


def _fechas_por_id(sopa) -> dict[str, str]:
    """id -> texto de fecha relativa (span.info-publish-date, descendiente del
    card [data-ga4-offerdata]; posición verificada contra la fixture real)."""
    porid: dict[str, str] = {}
    for card in sopa.select("[data-ga4-offerdata]"):
        try:
            oid = str(json.loads(card["data-ga4-offerdata"])["id"])
        except Exception:
            continue
        span = card.select_one(".info-publish-date")
        if span:
            porid[oid] = " ".join(span.get_text().split())
    return porid


def _extraer(html: str, criterios: Criterios) -> tuple[list[Vacante], int, int]:
    sopa = BeautifulSoup(html, "lxml")
    cards = _cards_por_id(sopa)
    fechas = _fechas_por_id(sopa)
    items = _items_jsonld(sopa)
    # La modalidad no se raspa de la tarjeta (patrón computrabajo Task 5): viene
    # de criterios, ya que la URL de búsqueda filtra por -modalidad-remoto.
    es_remoto = criterios.modalidad is Modalidad.REMOTO
    modalidad = Modalidad.REMOTO if es_remoto else Modalidad.DESCONOCIDO
    vacantes: list[Vacante] = []
    omitidas = 0
    for it in items:
        card = cards.get(it["id"])
        if not it["id"] or card is None:
            omitidas += 1
            continue
        try:
            salario_raw = str(card.get("salary", "") or "")
            smin, smax = parsear_salario(salario_raw)
            fecha_raw = fechas.get(it["id"]) or None  # texto relativo crudo; core normaliza (D22)
            vacantes.append(Vacante(
                id_nativo=it["id"],
                portal="elempleo",
                titulo=str(card.get("title") or it["name"]),
                empresa=str(card.get("company", "")),
                ubicacion=normalizar_ubicacion(str(card.get("location", ""))),
                modalidad=modalidad,
                salario_raw=salario_raw,
                salario_min=smin,
                salario_max=smax,
                url=it["url"],
                fecha_publicacion=fecha_raw,
            ))
        except Exception:
            omitidas += 1
    return vacantes, omitidas, len(items)  # n_crudo = items del ItemList


def extraer_detalle(html: str) -> str:
    """Descripción desde la página de la oferta. elempleo la encierra en un solo
    contenedor semántico, así que no hace falta anclar por encabezado."""
    bloque = BeautifulSoup(html, "lxml").select_one("div.description-block")
    return " ".join(bloque.get_text(" ").split()) if bloque else ""


def detalle(url: str, fetch=None) -> str:
    return extraer_detalle((fetch or fetch_curl)(url))


def _es_fin_paginacion(e: Exception) -> bool:
    """elempleo responde 404 a una página que no existe: es el final del listado,
    no una fuente rota. Prefiere el status_code real y cae al texto si no lo hay."""
    respuesta = getattr(e, "response", None)
    codigo = getattr(respuesta, "status_code", None)
    if codigo is not None:
        return codigo == 404
    return "404" in str(e)


def buscar(criterios: Criterios, fetch=None) -> ResultadoConector:
    return ejecutar(criterios, _url, fetch, _extraer, pausa=1.0, es_fin=_es_fin_paginacion)
