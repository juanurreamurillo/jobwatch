from jobwatch.modelos import (
    Vacante, Modalidad, EstadoConector, ResultadoConector,
    calcular_id_estable, calcular_fingerprint,
)


def _vacante(**over):
    base = dict(
        id_nativo="123", portal="indeed", titulo="Gerente de Proyectos TI",
        empresa="ACME S.A.S.", ubicacion="Bogotá D.C.", url="https://x/123",
    )
    base.update(over)
    return Vacante(**base)


def test_id_estable_es_estable_y_depende_de_portal_e_id():
    v = _vacante()
    assert v.id_estable == calcular_id_estable("indeed", "123")
    # mismo id nativo, distinto portal -> distinto id_estable
    assert _vacante(portal="magneto").id_estable != v.id_estable
    # mismo portal+id, distinta URL -> MISMO id_estable (D3)
    assert _vacante(url="https://x/123?utm=abc").id_estable == v.id_estable


def test_fingerprint_ignora_variaciones_menores():
    a = _vacante(empresa="ACME S.A.S.", titulo="Gerente de Proyectos TI", ubicacion="Bogotá D.C.")
    b = _vacante(id_nativo="999", empresa="acme sas", titulo="gerente de proyectos ti", ubicacion="bogota")
    assert a.fingerprint_contenido == b.fingerprint_contenido == calcular_fingerprint(
        "ACME S.A.S.", "Gerente de Proyectos TI", "Bogotá D.C."
    )


def test_resultado_conector_por_defecto_ok_vacio():
    r = ResultadoConector(estado=EstadoConector.OK)
    assert r.vacantes == [] and r.detalle == ""


def test_modalidad_default_desconocido():
    assert _vacante().modalidad == Modalidad.DESCONOCIDO
