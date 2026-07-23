from jobwatch.modelos import Criterios, EstadoConector
from jobwatch.conectores.indeed import buscar


class _FakeDF:
    """Minimal stand-in for the pandas DataFrame JobSpy returns."""
    def __init__(self, filas):
        self._filas = filas
    def to_dict(self, orient):
        assert orient == "records"
        return self._filas


def test_mapea_filas_a_vacantes():
    filas = [{
        "id": "abc123", "title": "Gerente de Proyectos TI", "company": "ACME",
        "location": "Bogotá D.C.", "job_url": "https://indeed/abc123",
        "is_remote": True, "min_amount": 4_000_000, "max_amount": 6_000_000,
        "description": "…", "date_posted": "2026-07-20",
    }]
    r = buscar(Criterios(terminos="gerente"), scrape=lambda **kw: _FakeDF(filas))
    assert r.estado == EstadoConector.OK
    assert len(r.vacantes) == 1
    v = r.vacantes[0]
    assert v.portal == "indeed" and v.id_nativo == "abc123"
    assert v.ubicacion == "Bogotá" and v.salario_max == 6_000_000


def test_resultado_vacio_es_ok_no_error():
    r = buscar(Criterios(terminos="x"), scrape=lambda **kw: _FakeDF([]))
    assert r.estado == EstadoConector.OK and r.vacantes == []


def test_excepcion_de_jobspy_es_error_fail_loud():
    def explota(**kw):
        raise RuntimeError("bloqueado")
    r = buscar(Criterios(terminos="x"), scrape=explota)
    assert r.estado == EstadoConector.ERROR and "bloqueado" in r.detalle
