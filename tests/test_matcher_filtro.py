from jobwatch.modelos import Criterios, Modalidad, Vacante
from jobwatch.matcher import filtro_local


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
