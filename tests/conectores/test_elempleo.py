from pathlib import Path

from jobwatch.conectores.elempleo import _extraer, _url, buscar
from jobwatch.modelos import Criterios, EstadoConector, Modalidad

FIXTURE = (Path(__file__).parent / "fixtures" / "elempleo.html").read_text(encoding="utf-8")


def _fetch_ok(url):
    # página 1 trae el fixture (2 ofertas); página 2 en adelante "agotada" (0
    # tarjetas crudas) para que la paginación (D17/B1) no reintente indefinidamente.
    return "" if url.split("?")[0].rstrip("/").endswith(("/2", "/3")) else FIXTURE


def test_parsea_itemlist_y_cards():
    r = buscar(Criterios(terminos="gerente de proyectos"), fetch=_fetch_ok)
    assert r.estado is EstadoConector.OK
    assert len(r.vacantes) == 2
    porid = {v.id_nativo: v for v in r.vacantes}
    v = porid["1886730317"]
    assert v.portal == "elempleo"
    assert v.titulo == "Gerente de proyectos"
    assert v.empresa == "ENTELGY COLOMBIA S.A.S"
    assert v.ubicacion == "Bogotá"
    assert v.url == "https://www.elempleo.com/co/ofertas-trabajo/gerente-de-proyectos-1886730317"
    assert v.salario_min is None            # "Salario confidencial" -> sin números
    assert porid["1886741235"].empresa == "JAHV MC GREGOR S.A.S"


def test_fetch_falla_es_error():
    def explota(url):
        raise RuntimeError("timeout")
    r = buscar(Criterios(terminos="x"), fetch=explota)
    assert r.estado is EstadoConector.ERROR and "timeout" in r.detalle


def test_ignora_bloque_jsonld_de_array_raiz():
    """Un bloque JSON-LD raíz-array (común en sitios reales) no debe tumbar
    el conector; los ítems del ItemList válido se siguen extrayendo."""
    html = """
    <html><body>
    <script type="application/ld+json">[{"@context": "https://schema.org", "@type": "BreadcrumbList"}]</script>
    <script type="application/ld+json">
    {"@type": "ItemList", "itemListElement": [
        {"item": {"@id": "https://www.elempleo.com/co/ofertas-trabajo/dev-123", "name": "Dev"}}
    ]}
    </script>
    <div data-ga4-offerdata='{"id": "123", "title": "Dev", "company": "ACME",
        "location": "Bogotá", "salary": "Salario confidencial"}'></div>
    </body></html>
    """

    def fetch(url):
        return "" if url.split("?")[0].rstrip("/").endswith(("/2", "/3")) else html

    r = buscar(Criterios(terminos="dev"), fetch=fetch)
    assert r.estado is EstadoConector.OK
    assert len(r.vacantes) == 1
    assert r.vacantes[0].id_nativo == "123"


def test_url_modalidad_remoto_publishdate_y_pagina():
    c = Criterios(terminos="gerente de proyectos", modalidad=Modalidad.REMOTO, dias=2)
    assert _url(c, 1).endswith("trabajo-gerente-de-proyectos-modalidad-remoto?PublishDate=hoy")
    assert _url(c, 3).endswith("trabajo-gerente-de-proyectos-modalidad-remoto/3?PublishDate=hoy")


def test_url_sin_modalidad_ni_dias():
    assert _url(Criterios(terminos="gerente"), 1).endswith("/co/ofertas-empleo/trabajo-gerente")


def test_extraer_puebla_fecha_cruda_y_ncrudo():
    vacantes, omitidas, n_crudo = _extraer(FIXTURE, Criterios(terminos="gerente de proyectos"))
    assert n_crudo == 2
    assert omitidas == 0
    assert len(vacantes) == 2
    porid = {v.id_nativo: v for v in vacantes}
    # fecha CRUDA (texto relativo tal cual aparece en el DOM); el core la normaliza (D22)
    assert porid["1886730317"].fecha_publicacion == "Hace 1 mes"
    assert porid["1886741235"].fecha_publicacion == "Hace 6 días"


def test_extraer_modalidad_remoto_viene_de_criterios_no_de_la_tarjeta():
    criterios = Criterios(terminos="gerente de proyectos", modalidad=Modalidad.REMOTO)
    vacantes, _, _ = _extraer(FIXTURE, criterios)
    assert len(vacantes) == 2
    assert all(v.modalidad is Modalidad.REMOTO for v in vacantes)


def test_extraer_sin_modalidad_en_criterios_es_desconocida():
    vacantes, _, _ = _extraer(FIXTURE, Criterios(terminos="gerente de proyectos"))
    assert len(vacantes) == 2
    assert all(v.modalidad is Modalidad.DESCONOCIDO for v in vacantes)
