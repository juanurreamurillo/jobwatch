from pathlib import Path

from jobwatch.conectores.magneto import buscar
from jobwatch.modelos import Criterios, EstadoConector

FIXTURE = (Path(__file__).parent / "fixtures" / "magneto.html").read_text(encoding="utf-8")


def test_extrae_campos_cuando_el_termino_coincide():
    # el feed trae "Gestor de servicio en sitio"; con ese término el card pasa el filtro
    r = buscar(Criterios(terminos="gestor de servicio"), fetch=lambda url: FIXTURE)
    assert r.estado is EstadoConector.OK
    assert len(r.vacantes) == 1
    v = r.vacantes[0]
    assert v.portal == "magneto"
    assert v.id_nativo == "1004184"
    assert v.titulo == "Gestor de servicio en sitio"
    assert v.empresa == "Confidencial"
    assert v.ubicacion == "Bogotá"
    assert v.url.endswith("/co/empleos/gestor-de-servicio-en-sitio-1004184")
    assert v.salario_min == 500_000 and v.salario_max == 3_000_000


def test_filtra_client_side_cuando_search_no_filtra():
    # el portal ignora ?search=; ningún card del feed es "gerente de proyectos"
    r = buscar(Criterios(terminos="gerente de proyectos"), fetch=lambda url: FIXTURE)
    assert r.estado is EstadoConector.OK and r.vacantes == []


def test_fetch_falla_es_error():
    def explota(url):
        raise RuntimeError("503")
    r = buscar(Criterios(terminos="x"), fetch=explota)
    assert r.estado is EstadoConector.ERROR and "503" in r.detalle
