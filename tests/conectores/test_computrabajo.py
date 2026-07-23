from pathlib import Path

from jobwatch.conectores.computrabajo import buscar
from jobwatch.modelos import Criterios, EstadoConector

FIXTURE = (Path(__file__).parent / "fixtures" / "computrabajo.html").read_text(encoding="utf-8")


def _fetch_ok(url):
    return FIXTURE


def test_parsea_dos_ofertas_del_fixture():
    r = buscar(Criterios(terminos="gerente de proyectos"), fetch=_fetch_ok)
    assert r.estado is EstadoConector.OK
    assert len(r.vacantes) == 2
    v0, v1 = r.vacantes
    assert v0.portal == "computrabajo"
    assert v0.id_nativo == "067CFDC9FD215E0B61373E686DCF3405"
    assert v0.titulo == "Director de Proyectos Fotovoltaico"
    assert v0.empresa == "GLOBALEM S.A.S"
    assert v0.ubicacion == "Bogotá"
    assert v0.url.startswith("https://co.computrabajo.com/ofertas-de-trabajo/")
    assert "#" not in v0.url          # el fragmento #lc= se quitó
    assert v0.salario_max is None     # oferta 1 no trae salario


def test_extrae_salario_cuando_existe():
    r = buscar(Criterios(terminos="x"), fetch=_fetch_ok)
    v1 = r.vacantes[1]
    assert v1.empresa == "Proservis"
    assert v1.ubicacion == "Cali"
    assert v1.salario_max == 8_529_999


def test_fetch_falla_es_error_fail_loud():
    def explota(url):
        raise RuntimeError("403 bloqueado")
    r = buscar(Criterios(terminos="x"), fetch=explota)
    assert r.estado is EstadoConector.ERROR and "403 bloqueado" in r.detalle
