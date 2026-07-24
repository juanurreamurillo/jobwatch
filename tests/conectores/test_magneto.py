from pathlib import Path

from jobwatch.conectores.magneto import _extraer, _rows_del_flight, _url, buscar
from jobwatch.modelos import Criterios, EstadoConector, Modalidad

FIXTURE = (Path(__file__).parent / "fixtures" / "magneto-flight.html").read_text(
    encoding="utf-8"
)


def test_url_ruta_termino_pagina():
    c = Criterios(terminos="gerente de proyectos", modalidad=Modalidad.REMOTO)
    assert _url(c, 1).endswith("/co/trabajos/buscar/gerente-de-proyectos")
    assert _url(c, 3).endswith("/co/trabajos/buscar/gerente-de-proyectos/pagina-3")


def test_rows_del_flight_extrae_vacantes():
    rows = _rows_del_flight(FIXTURE)
    assert len(rows) >= 1
    r0 = rows[0]
    assert "publishDate" in r0 and "id" in r0 and "title" in r0


def test_extraer_filtra_remoto_y_puebla_fecha_iso():
    c = Criterios(terminos="gerente de proyectos", modalidad=Modalidad.REMOTO)
    vacantes, omitidas, n_crudo = _extraer(FIXTURE, c)
    assert n_crudo >= 1  # tarjetas crudas del flight
    assert all(v.modalidad is Modalidad.REMOTO for v in vacantes)  # solo remotas
    assert all(v.fecha_publicacion and v.fecha_publicacion[:2] == "20" for v in vacantes)


def test_extraer_sin_filtro_remoto_incluye_todas():
    c = Criterios(terminos="gerente de proyectos")
    vacantes, omitidas, n_crudo = _extraer(FIXTURE, c)
    assert n_crudo == len(vacantes) + omitidas


def test_fetch_falla_es_error():
    def explota(url):
        raise RuntimeError("503")

    r = buscar(Criterios(terminos="x"), fetch=explota)
    assert r.estado is EstadoConector.ERROR and "503" in r.detalle
