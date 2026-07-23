from jobwatch.modelos import Criterios, EstadoConector, ResultadoConector, Vacante
from jobwatch.orquestador import colapsar_lote, correr
from jobwatch.store import Store


def _v(id_nativo, empresa="ACME", titulo="Dev"):
    return Vacante(id_nativo=id_nativo, portal="indeed", empresa=empresa, titulo=titulo,
                   ubicacion="Bogotá", url=f"https://x/{id_nativo}")


def _conector_ok(vacantes):
    return lambda c: ResultadoConector(estado=EstadoConector.OK, vacantes=vacantes)


def test_solo_puntua_las_nuevas(tmp_path):
    store = Store(str(tmp_path / "t.db"))
    store.persistir([_v("1")])  # ya vista
    conectores = {"indeed": _conector_ok([_v("1"), _v("2", titulo="Otro Dev")])}
    puntuadas = []
    def fake(v, cv):
        puntuadas.append(v.id_nativo)
        return {"puntaje": 70, "razon": "ok"}
    md, resultados = correr(Criterios(terminos="dev"), "cv", store, fake, conectores, "2026-07-23")
    assert puntuadas == ["2"]           # solo la nueva se puntúa
    assert "2026-07-23" in md
    assert resultados["indeed"].estado is EstadoConector.OK
    store.cerrar()


def test_estado_error_se_propaga_al_reporte(tmp_path):
    store = Store(str(tmp_path / "t.db"))
    conectores = {
        "indeed": lambda c: ResultadoConector(estado=EstadoConector.ERROR, detalle="bloqueado"),
    }
    md, resultados = correr(Criterios(terminos="x"), "cv", store, lambda v, cv: {}, conectores, "2026-07-23")
    assert resultados["indeed"].estado is EstadoConector.ERROR
    assert "ERROR" in md
    store.cerrar()


def test_correr_backstop_conector_que_lanza_excepcion(tmp_path):
    store = Store(str(tmp_path / "t.db"))

    def _malo(c):
        raise RuntimeError("timeout de red")

    v = _v("1")
    conectores = {
        "portal_malo": _malo,
        "indeed": _conector_ok([v]),
    }
    md, resultados = correr(
        Criterios(terminos="dev"), "cv", store, lambda v, cv: {"puntaje": 70, "razon": "ok"},
        conectores, "2026-07-23",
    )
    assert isinstance(md, str)
    assert resultados["portal_malo"].estado is EstadoConector.ERROR
    assert "timeout de red" in resultados["portal_malo"].detalle
    assert resultados["indeed"].estado is EstadoConector.OK
    assert store.es_nueva(v) is False  # la oferta buena sí quedó persistida
    store.cerrar()


def _vp(portal, empresa="ACME", titulo="Gerente de Proyectos", ubic="Bogotá", idn="1"):
    return Vacante(id_nativo=idn, portal=portal, titulo=titulo, empresa=empresa,
                   ubicacion=ubic, url=f"https://{portal}/{idn}")


def test_portales_por_defecto_es_el_propio_portal():
    assert _vp("magneto").portales == ["magneto"]


def test_colapsa_misma_oferta_en_dos_portales_por_prioridad():
    # misma empresa+titulo+ubicacion -> mismo fingerprint; distinto portal
    vs = [_vp("magneto", idn="9"), _vp("computrabajo", idn="1")]
    out = colapsar_lote(vs)
    assert len(out) == 1
    canon = out[0]
    assert canon.portal == "computrabajo"                 # gana por PRIORIDAD_PORTAL
    assert canon.portales == ["computrabajo", "magneto"]  # unión ordenada por prioridad


def test_no_colapsa_ofertas_distintas():
    vs = [_vp("computrabajo", empresa="A"), _vp("elempleo", empresa="B")]
    assert len(colapsar_lote(vs)) == 2


def test_desempate_deterministico_mismo_portal_distinto_id_nativo():
    # Mismo portal duplicado dentro de un mismo lote (misma prioridad):
    # el ganador debe ser el mismo id_nativo sin importar el orden de entrada.
    a = _vp("indeed", idn="1")
    b = _vp("indeed", idn="2")
    out_ab = colapsar_lote([a, b])
    out_ba = colapsar_lote([b, a])
    assert len(out_ab) == 1 and len(out_ba) == 1
    assert out_ab[0].id_nativo == out_ba[0].id_nativo


def test_desempate_deterministico_portales_no_listados():
    # Dos portales fuera de PRIORIDAD_PORTAL (misma prioridad por defecto):
    # el ganador debe ser el mismo portal sin importar el orden de entrada.
    a = _vp("linkedin", idn="1")
    b = _vp("glassdoor", idn="2")
    out_ab = colapsar_lote([a, b])
    out_ba = colapsar_lote([b, a])
    assert len(out_ab) == 1 and len(out_ba) == 1
    assert out_ab[0].portal == out_ba[0].portal
    assert out_ab[0].portales == out_ba[0].portales == ["glassdoor", "linkedin"]


def test_correr_colapsa_entre_conectores(tmp_path):
    from jobwatch.modelos import Criterios, EstadoConector, ResultadoConector, Vacante
    from jobwatch.orquestador import correr
    from jobwatch.store import Store

    def _mk(portal):
        v = Vacante(id_nativo="1", portal=portal, titulo="Gerente de Proyectos",
                    empresa="ACME", ubicacion="Bogotá", url=f"https://{portal}/1")
        return lambda c: ResultadoConector(estado=EstadoConector.OK, vacantes=[v])

    store = Store(str(tmp_path / "j.db"))
    conectores = {"computrabajo": _mk("computrabajo"), "magneto": _mk("magneto")}
    md, resultados = correr(
        Criterios(terminos="gerente de proyectos"), "cv", store,
        lambda v, cv: {"puntaje": 70, "razon": "ok"}, conectores, "2026-07-23",
    )
    store.cerrar()
    # una sola oferta persistida (colapsada), y el reporte la marca multi-portal
    assert md.count("### [Gerente de Proyectos]") == 1
    assert "Vista en 2 portales: computrabajo, magneto" in md
