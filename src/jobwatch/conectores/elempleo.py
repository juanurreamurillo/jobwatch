from __future__ import annotations

import json

from bs4 import BeautifulSoup

from jobwatch.conectores._comun import ejecutar, id_de_url, slug
from jobwatch.modelos import Criterios, ResultadoConector, Vacante
from jobwatch.normalizar import normalizar_ubicacion, parsear_salario

HOST = "https://www.elempleo.com"


def _url(criterios: Criterios) -> str:
    return f"{HOST}/co/ofertas-empleo/trabajo-{slug(criterios.terminos)}"


def _items_jsonld(sopa) -> list[dict]:
    """Items del ItemList: {id, url, name}. Tolera varios bloques JSON-LD."""
    items: list[dict] = []
    for script in sopa.select('script[type="application/ld+json"]'):
        try:
            datos = json.loads(script.string or "")
        except Exception:
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


def _extraer(html: str, criterios: Criterios) -> tuple[list[Vacante], int]:
    sopa = BeautifulSoup(html, "lxml")
    cards = _cards_por_id(sopa)
    vacantes: list[Vacante] = []
    omitidas = 0
    for it in _items_jsonld(sopa):
        card = cards.get(it["id"])
        if not it["id"] or card is None:
            omitidas += 1
            continue
        try:
            salario_raw = str(card.get("salary", "") or "")
            smin, smax = parsear_salario(salario_raw)
            vacantes.append(Vacante(
                id_nativo=it["id"],
                portal="elempleo",
                titulo=str(card.get("title") or it["name"]),
                empresa=str(card.get("company", "")),
                ubicacion=normalizar_ubicacion(str(card.get("location", ""))),
                salario_raw=salario_raw,
                salario_min=smin,
                salario_max=smax,
                url=it["url"],
            ))
        except Exception:
            omitidas += 1
    return vacantes, omitidas


def buscar(criterios: Criterios, fetch=None) -> ResultadoConector:
    return ejecutar(criterios, _url, fetch, _extraer)
