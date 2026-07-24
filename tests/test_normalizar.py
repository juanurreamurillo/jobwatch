# tests/test_normalizar.py
from datetime import date
from jobwatch.modelos import Modalidad
from jobwatch.normalizar import (
    normalizar_texto, normalizar_ubicacion, normalizar_modalidad, parsear_salario,
    parsear_fecha_relativa,
)


def test_normalizar_texto_colapsa_espacios():
    assert normalizar_texto("  Gerente   de\tProyectos ") == "Gerente de Proyectos"


def test_normalizar_ubicacion_canoniza_bogota():
    assert normalizar_ubicacion("Bogotá D.C.") == "Bogotá"
    assert normalizar_ubicacion("Bogota, Colombia") == "Bogotá"
    assert normalizar_ubicacion("Medellín") == "Medellín"


def test_normalizar_ubicacion_no_devora_ciudades_con_c():
    # una "D" suelta antes de una ciudad con C no debe mutilarla
    assert normalizar_ubicacion("D Cali") != "ali"
    assert "Cali" in normalizar_ubicacion("D Cali")


def test_normalizar_ubicacion_dc_sin_punto_final():
    assert normalizar_ubicacion("Bogotá D.C") == "Bogotá"


def test_normalizar_modalidad_mapea_sinonimos():
    assert normalizar_modalidad("Trabajo remoto") == Modalidad.REMOTO
    assert normalizar_modalidad("Híbrido") == Modalidad.HIBRIDO
    assert normalizar_modalidad("Presencial") == Modalidad.PRESENCIAL
    assert normalizar_modalidad("cualquier cosa") == Modalidad.DESCONOCIDO


def test_parsear_salario_rango_y_unico():
    assert parsear_salario("$2.000.000 a $3.000.000 COP") == (2_000_000, 3_000_000)
    assert parsear_salario("$4.500.000") == (4_500_000, 4_500_000)
    assert parsear_salario("A convenir") == (None, None)


HOY = date(2026, 7, 23)


def test_fecha_relativa_hoy_y_ayer():
    assert parsear_fecha_relativa("Hoy", HOY) == HOY
    assert parsear_fecha_relativa("Ayer", HOY) == date(2026, 7, 22)


def test_fecha_relativa_horas_es_hoy():
    assert parsear_fecha_relativa("Hace 3 horas", HOY) == HOY
    assert parsear_fecha_relativa("Hace  2  minutos", HOY) == HOY


def test_fecha_relativa_dias_semanas_meses():
    assert parsear_fecha_relativa("Hace 2 días", HOY) == date(2026, 7, 21)
    assert parsear_fecha_relativa("Hace 1 semana", HOY) == date(2026, 7, 16)
    assert parsear_fecha_relativa("Hace 3 semanas", HOY) == date(2026, 7, 2)
    assert parsear_fecha_relativa("Hace 1 mes", HOY) == date(2026, 6, 23)


def test_fecha_relativa_no_fechable_es_none():
    assert parsear_fecha_relativa("", HOY) is None
    assert parsear_fecha_relativa("Publicación reciente", HOY) is None
