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
    md, estados = correr(Criterios(terminos="dev"), "cv", store, fake, conectores, "2026-07-23")
    assert puntuadas == ["2"]           # solo la nueva se puntúa
    assert "2026-07-23" in md
    assert estados["indeed"] == EstadoConector.OK
    store.cerrar()


def test_estado_error_se_propaga_al_reporte(tmp_path):
    store = Store(str(tmp_path / "t.db"))
    conectores = {
        "indeed": lambda c: ResultadoConector(estado=EstadoConector.ERROR, detalle="bloqueado"),
    }
    md, estados = correr(Criterios(terminos="x"), "cv", store, lambda v, cv: {}, conectores, "2026-07-23")
    assert estados["indeed"] == EstadoConector.ERROR
    assert "ERROR" in md
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
