from jobwatch.modelos import (
    Vacante, Modalidad, EstadoConector, ResultadoConector,
    calcular_id_estable, calcular_fingerprint, Criterios,
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


def test_fingerprint_dc_insensible_a_mayusculas_y_acotado_a_ubicacion():
    # D.C. suffix collapses regardless of case
    assert calcular_fingerprint("X", "Y", "Bogotá D.C.") == calcular_fingerprint("X", "Y", "bogota d.c.") == calcular_fingerprint("X", "Y", "Bogotá")
    # 'D.C.' inside a company name is NOT stripped (scope is location-only)
    assert calcular_fingerprint("D.C. United", "Y", "Bogotá") != calcular_fingerprint("United", "Y", "Bogotá")


def test_cosecha_round_trip_json():
    from jobwatch.modelos import Cosecha, EstadoConector, ResultadoConector, Vacante

    v = Vacante(id_nativo="1", portal="computrabajo", titulo="Dev", empresa="ACME",
                ubicacion="Bogotá", url="https://x/1")
    c = Cosecha(
        run_id="abcd1234", tope=50,
        estados={"computrabajo": ResultadoConector(estado=EstadoConector.OK, detalle="")},
        candidatas=[v],
    )
    reconstruida = Cosecha.model_validate_json(c.model_dump_json())
    assert reconstruida.run_id == "abcd1234"
    assert reconstruida.tope == 50
    assert reconstruida.candidatas[0].id_estable == v.id_estable
    assert reconstruida.estados["computrabajo"].estado is EstadoConector.OK


def test_lote_puntajes_estado_enum():
    from jobwatch.modelos import EstadoOferta, LotePuntajes, Puntaje

    lote = LotePuntajes(run_id="x", puntajes=[
        Puntaje(id_estable="a", estado=EstadoOferta.PUNTUADA, puntaje=80, razon="ok"),
        Puntaje(id_estable="b", estado=EstadoOferta.SIN_PUNTAJE, puntaje=None, razon="no aplica"),
    ])
    assert lote.puntajes[0].puntaje == 80
    assert lote.puntajes[1].puntaje is None


def test_criterios_dias_default_none():
    assert Criterios(terminos="x").dias is None


def test_criterios_dias_se_asigna():
    assert Criterios(terminos="x", dias=2).dias == 2
