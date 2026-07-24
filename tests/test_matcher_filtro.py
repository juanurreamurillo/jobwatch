from datetime import date

from jobwatch.modelos import Criterios, Modalidad, Vacante
from jobwatch.matcher import filtro_local, filtro_recencia


def _v(**over):
    base = dict(id_nativo="1", portal="indeed", titulo="Gerente de Proyectos TI",
                empresa="ACME", ubicacion="Bogotá", url="https://x/1")
    base.update(over)
    return Vacante(**base)


def test_sobrevive_por_defecto():
    assert filtro_local(_v(), Criterios(terminos="gerente")) is True


def test_rechaza_por_keyword_excluida():
    v = _v(titulo="Gerente de Ventas puerta a puerta")
    assert filtro_local(v, Criterios(terminos="gerente", excluir=["ventas"])) is False


def test_rechaza_por_salario_bajo_solo_si_hay_dato():
    caro = _v(salario_max=5_000_000)
    barato = _v(salario_max=1_000_000)
    sin_dato = _v()
    c = Criterios(terminos="x", salario_min=3_000_000)
    assert filtro_local(caro, c) is True
    assert filtro_local(barato, c) is False
    assert filtro_local(sin_dato, c) is True  # sin dato no se descarta


def test_rechaza_por_modalidad_solo_si_conocida():
    c = Criterios(terminos="x", modalidad=Modalidad.REMOTO)
    assert filtro_local(_v(modalidad=Modalidad.PRESENCIAL), c) is False
    assert filtro_local(_v(modalidad=Modalidad.REMOTO), c) is True
    assert filtro_local(_v(modalidad=Modalidad.DESCONOCIDO), c) is True


HOY = date(2026, 7, 23)


def _vf(fecha):
    return Vacante(id_nativo="1", portal="x", titulo="t", empresa="e",
                   ubicacion="u", url="http://x", fecha_publicacion=fecha)


def test_recencia_none_no_filtra():
    assert filtro_recencia(_vf("2020-01-01"), None, HOY) is True


def test_recencia_dias2_es_hoy_y_ayer():
    assert filtro_recencia(_vf("2026-07-23"), 2, HOY) is True   # hoy
    assert filtro_recencia(_vf("2026-07-22"), 2, HOY) is True   # ayer
    assert filtro_recencia(_vf("2026-07-21"), 2, HOY) is False  # anteayer FUERA


def test_recencia_no_fechable_se_incluye():
    assert filtro_recencia(_vf(None), 2, HOY) is True
