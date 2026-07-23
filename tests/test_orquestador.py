from jobwatch.modelos import Criterios, EstadoConector, ResultadoConector, Vacante
from jobwatch.orquestador import correr
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
