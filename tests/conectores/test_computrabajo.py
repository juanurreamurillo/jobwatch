from pathlib import Path

from jobwatch.conectores.computrabajo import _extraer, _url, buscar
from jobwatch.modelos import Criterios, EstadoConector, Modalidad

FIXTURE = (Path(__file__).parent / "fixtures" / "computrabajo.html").read_text(encoding="utf-8")


def _fetch_ok(url):
    # página 1 trae el fixture (2 ofertas); página 2 en adelante "agotada" (0
    # tarjetas crudas) para que la paginación (D17/B1) no reintente indefinidamente.
    return "" if "p=2" in url else FIXTURE


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


def test_url_remoto_pubdate_paginado():
    c = Criterios(terminos="gerente de proyectos", modalidad=Modalidad.REMOTO, dias=2)
    u = _url(c, 2)
    assert "/trabajo-de-gerente-de-proyectos-en-remoto" in u
    assert "pubdate=3" in u          # menor de {1,3,7,15} >= 2
    assert "by=publicationtime" in u
    assert "&p=2" in u


def test_url_dias_excede_max_pubdate_no_filtra_server():
    c = Criterios(terminos="gerente", modalidad=Modalidad.REMOTO, dias=30)
    u = _url(c, 1)
    assert "/trabajo-de-gerente-de-proyectos-en-remoto" not in u  # slug diferente, pero cumple lógica
    assert "pubdate=" not in u  # dias>15 no manda pubdate
    assert "by=publicationtime" not in u
    # Sin params de pubdate, la URL base solo tiene /trabajo-de-gerente-en-remoto (sin ?p=1 porque es página 1)


def test_url_sin_modalidad_ni_dias():
    u = _url(Criterios(terminos="gerente"), 1)
    assert u.endswith("/trabajo-de-gerente")   # sin -en-remoto, sin params, p=1 implícito/omitido


def test_extraer_puebla_fecha_cruda_y_ncrudo():
    vacantes, omitidas, n_crudo = _extraer(FIXTURE, Criterios(terminos="gerente"))
    assert n_crudo >= 1
    assert len(vacantes) >= 1
    # al menos una con la fecha CRUDA poblada (texto relativo; el core la normaliza)
    assert any(v.fecha_publicacion for v in vacantes)


def test_extraer_modalidad_remoto_viene_de_criterios_no_de_la_tarjeta():
    criterios = Criterios(terminos="gerente", modalidad=Modalidad.REMOTO)
    vacantes, _, _ = _extraer(FIXTURE, criterios)
    assert len(vacantes) >= 1
    assert all(v.modalidad is Modalidad.REMOTO for v in vacantes)


def test_extraer_sin_modalidad_en_criterios_es_desconocida():
    vacantes, _, _ = _extraer(FIXTURE, Criterios(terminos="gerente"))
    assert len(vacantes) >= 1
    assert all(v.modalidad is Modalidad.DESCONOCIDO for v in vacantes)
