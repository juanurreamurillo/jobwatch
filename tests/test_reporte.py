# tests/test_reporte.py
from jobwatch.modelos import (
    EstadoConector, EstadoOferta, OfertaPuntuada, ResultadoConector, Vacante,
)
from jobwatch.reporte import render


def _op(id_nativo, puntaje, estado=EstadoOferta.PUNTUADA):
    v = Vacante(id_nativo=id_nativo, portal="indeed", titulo=f"Cargo {id_nativo}",
                empresa="ACME", ubicacion="Bogotá", url=f"https://x/{id_nativo}")
    return OfertaPuntuada(vacante=v, estado=estado, puntaje=puntaje, razon="motivo")


def test_render_incluye_fecha_y_estado_de_conector():
    resultados = {"indeed": ResultadoConector(estado=EstadoConector.ERROR)}
    md = render("2026-07-23", resultados, [])
    assert "2026-07-23" in md
    assert "indeed" in md and "ERROR" in md


def test_ofertas_ordenadas_por_puntaje_desc():
    ofertas = [_op("1", 40), _op("2", 90), _op("3", 65)]
    resultados = {"indeed": ResultadoConector(estado=EstadoConector.OK)}
    md = render("2026-07-23", resultados, ofertas)
    assert md.index("Cargo 2") < md.index("Cargo 3") < md.index("Cargo 1")


def test_sin_puntaje_va_al_final():
    ofertas = [_op("1", None, EstadoOferta.ERROR), _op("2", 50)]
    resultados = {"indeed": ResultadoConector(estado=EstadoConector.OK)}
    md = render("2026-07-23", resultados, ofertas)
    assert md.index("Cargo 2") < md.index("Cargo 1")


def test_render_muestra_detalle_y_multiportal():
    v = Vacante(id_nativo="1", portal="computrabajo", titulo="Gerente", empresa="ACME",
                ubicacion="Bogotá", url="https://x/1", portales=["computrabajo", "magneto"])
    ofertas = [OfertaPuntuada(vacante=v, estado=EstadoOferta.PUNTUADA, puntaje=80, razon="ok")]
    resultados = {
        "computrabajo": ResultadoConector(estado=EstadoConector.OK, detalle="1 filas omitidas"),
        "indeed": ResultadoConector(estado=EstadoConector.ERROR, detalle="bloqueado: 403"),
    }
    md = render("2026-07-23", resultados, ofertas)
    assert "1 filas omitidas" in md
    assert "bloqueado: 403" in md
    assert "computrabajo, magneto" in md          # nota "vista en N portales"
