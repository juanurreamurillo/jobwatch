# tests/test_normalizar.py
from jobwatch.modelos import Modalidad
from jobwatch.normalizar import (
    normalizar_texto, normalizar_ubicacion, normalizar_modalidad, parsear_salario,
)


def test_normalizar_texto_colapsa_espacios():
    assert normalizar_texto("  Gerente   de\tProyectos ") == "Gerente de Proyectos"


def test_normalizar_ubicacion_canoniza_bogota():
    assert normalizar_ubicacion("Bogotá D.C.") == "Bogotá"
    assert normalizar_ubicacion("Bogota, Colombia") == "Bogotá"
    assert normalizar_ubicacion("Medellín") == "Medellín"


def test_normalizar_modalidad_mapea_sinonimos():
    assert normalizar_modalidad("Trabajo remoto") == Modalidad.REMOTO
    assert normalizar_modalidad("Híbrido") == Modalidad.HIBRIDO
    assert normalizar_modalidad("Presencial") == Modalidad.PRESENCIAL
    assert normalizar_modalidad("cualquier cosa") == Modalidad.DESCONOCIDO


def test_parsear_salario_rango_y_unico():
    assert parsear_salario("$2.000.000 a $3.000.000 COP") == (2_000_000, 3_000_000)
    assert parsear_salario("$4.500.000") == (4_500_000, 4_500_000)
    assert parsear_salario("A convenir") == (None, None)
