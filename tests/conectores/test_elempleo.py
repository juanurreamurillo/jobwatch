from pathlib import Path

from jobwatch.conectores.elempleo import buscar
from jobwatch.modelos import Criterios, EstadoConector

FIXTURE = (Path(__file__).parent / "fixtures" / "elempleo.html").read_text(encoding="utf-8")


def test_parsea_itemlist_y_cards():
    r = buscar(Criterios(terminos="gerente de proyectos"), fetch=lambda url: FIXTURE)
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
    r = buscar(Criterios(terminos="dev"), fetch=lambda url: html)
    assert r.estado is EstadoConector.OK
    assert len(r.vacantes) == 1
    assert r.vacantes[0].id_nativo == "123"
