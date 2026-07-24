import pytest

from jobwatch.modelos import Criterios, EstadoConector, ResultadoConector, Vacante
from jobwatch.nucleo import TopeExcedido, calcular_run_id, colapsar_lote, cosechar  # noqa: F401
from jobwatch.store import Store


def _v(idn, portal="indeed", empresa="ACME", titulo="Dev", ubic="Bogotá"):
    return Vacante(id_nativo=idn, portal=portal, empresa=empresa, titulo=titulo,
                   ubicacion=ubic, url=f"https://{portal}/{idn}")


def _ok(vacantes):
    return lambda c: ResultadoConector(estado=EstadoConector.OK, vacantes=vacantes)


def test_run_id_estable_y_sensible_a_fecha():
    vs = [_v("1"), _v("2")]
    a = calcular_run_id(vs, "2026-07-23")
    assert a == calcular_run_id(list(reversed(vs)), "2026-07-23")  # no depende del orden
    assert a != calcular_run_id(vs, "2026-07-24")                  # sí de la fecha


def test_cosechar_dedup_filtro_y_run_id(tmp_path):
    store = Store(str(tmp_path / "t.db"))
    conectores = {"indeed": _ok([_v("2", titulo="Otro Dev")])}
    cosecha = cosechar(Criterios(terminos="dev"), store, conectores, tope=50, fecha="2026-07-23")
    assert len(cosecha.candidatas) == 1
    assert cosecha.run_id == calcular_run_id(cosecha.candidatas, "2026-07-23")
    assert cosecha.tope == 50
    assert cosecha.estados["indeed"].estado is EstadoConector.OK
    store.cerrar()


def test_cosechar_es_solo_lectura(tmp_path):
    store = Store(str(tmp_path / "t.db"))
    v = _v("9")
    cosechar(Criterios(terminos="dev"), store, {"indeed": _ok([v])}, tope=50, fecha="2026-07-23")
    assert store.es_nueva(v) is True  # NADA persistido en harvest (D13)
    store.cerrar()


def test_cosechar_excluye_ya_vistas(tmp_path):
    store = Store(str(tmp_path / "t.db"))
    store.persistir([_v("1")])
    conectores = {"indeed": _ok([_v("1"), _v("2", titulo="Dev Nueva")])}
    cosecha = cosechar(Criterios(terminos="dev"), store, conectores, tope=50, fecha="2026-07-23")
    assert [v.id_nativo for v in cosecha.candidatas] == ["2"]
    store.cerrar()


def test_cosechar_tope_lanza_antes_de_puntuar(tmp_path):
    store = Store(str(tmp_path / "t.db"))
    muchas = [_v(str(i), titulo=f"Dev {i}") for i in range(5)]
    with pytest.raises(TopeExcedido):
        cosechar(Criterios(terminos="dev"), store, {"indeed": _ok(muchas)}, tope=3, fecha="2026-07-23")
    store.cerrar()


def test_cosechar_backstop_conector_que_lanza(tmp_path):
    store = Store(str(tmp_path / "t.db"))
    def malo(c):
        raise RuntimeError("timeout de red")
    conectores = {"malo": malo, "indeed": _ok([_v("1")])}
    cosecha = cosechar(Criterios(terminos="dev"), store, conectores, tope=50, fecha="2026-07-23")
    assert cosecha.estados["malo"].estado is EstadoConector.ERROR
    assert "timeout de red" in cosecha.estados["malo"].detalle
    assert len(cosecha.candidatas) == 1
    store.cerrar()


def _cosecha_de(vs, fecha="2026-07-23"):
    from jobwatch.modelos import Cosecha
    return Cosecha(run_id=calcular_run_id(vs, fecha), tope=50, estados={}, candidatas=vs)


def test_validar_scores_ok_incluye_sin_puntaje():
    from jobwatch.modelos import EstadoOferta, LotePuntajes, Puntaje
    from jobwatch.nucleo import validar_scores

    a, b = _v("1"), _v("2", titulo="Otro")
    cosecha = _cosecha_de([a, b])
    lote = LotePuntajes(run_id=cosecha.run_id, puntajes=[
        Puntaje(id_estable=a.id_estable, estado=EstadoOferta.PUNTUADA, puntaje=78, razon="encaja"),
        Puntaje(id_estable=b.id_estable, estado=EstadoOferta.SIN_PUNTAJE, puntaje=None, razon="no aplica"),
    ])
    ofertas = validar_scores(cosecha, lote)
    por_id = {o.vacante.id_estable: o for o in ofertas}
    assert por_id[a.id_estable].puntaje == 78
    assert por_id[b.id_estable].estado is EstadoOferta.SIN_PUNTAJE


def test_validar_scores_run_id_desalineado():
    from jobwatch.modelos import EstadoOferta, LotePuntajes, Puntaje
    from jobwatch.nucleo import ScoresInvalidos, validar_scores

    a = _v("1")
    cosecha = _cosecha_de([a])
    lote = LotePuntajes(run_id="viejo000", puntajes=[
        Puntaje(id_estable=a.id_estable, estado=EstadoOferta.PUNTUADA, puntaje=50)])
    with pytest.raises(ScoresInvalidos, match="run_id"):
        validar_scores(cosecha, lote)


def test_validar_scores_falta_una_candidata():
    from jobwatch.modelos import EstadoOferta, LotePuntajes, Puntaje
    from jobwatch.nucleo import ScoresInvalidos, validar_scores

    a, b = _v("1"), _v("2", titulo="Otro")
    cosecha = _cosecha_de([a, b])
    lote = LotePuntajes(run_id=cosecha.run_id, puntajes=[
        Puntaje(id_estable=a.id_estable, estado=EstadoOferta.PUNTUADA, puntaje=50)])
    with pytest.raises(ScoresInvalidos):
        validar_scores(cosecha, lote)


def test_validar_scores_id_inventado():
    from jobwatch.modelos import EstadoOferta, LotePuntajes, Puntaje
    from jobwatch.nucleo import ScoresInvalidos, validar_scores

    a = _v("1")
    cosecha = _cosecha_de([a])
    lote = LotePuntajes(run_id=cosecha.run_id, puntajes=[
        Puntaje(id_estable=a.id_estable, estado=EstadoOferta.PUNTUADA, puntaje=50),
        Puntaje(id_estable="fantasma", estado=EstadoOferta.PUNTUADA, puntaje=50)])
    with pytest.raises(ScoresInvalidos):
        validar_scores(cosecha, lote)


def test_validar_scores_puntaje_fuera_de_rango():
    from jobwatch.modelos import EstadoOferta, LotePuntajes, Puntaje
    from jobwatch.nucleo import ScoresInvalidos, validar_scores

    a = _v("1")
    cosecha = _cosecha_de([a])
    lote = LotePuntajes(run_id=cosecha.run_id, puntajes=[
        Puntaje(id_estable=a.id_estable, estado=EstadoOferta.PUNTUADA, puntaje=150)])
    with pytest.raises(ScoresInvalidos, match="0.*100|rango"):
        validar_scores(cosecha, lote)


def test_reportar_persiste_todas_y_renderiza(tmp_path):
    from jobwatch.modelos import EstadoOferta, LotePuntajes, Puntaje
    from jobwatch.nucleo import reportar, validar_scores
    from jobwatch.store import Store

    a, b = _v("1", titulo="Gerente"), _v("2", titulo="Analista")
    cosecha = _cosecha_de([a, b])
    lote = LotePuntajes(run_id=cosecha.run_id, puntajes=[
        Puntaje(id_estable=a.id_estable, estado=EstadoOferta.PUNTUADA, puntaje=90, razon="top"),
        Puntaje(id_estable=b.id_estable, estado=EstadoOferta.SIN_PUNTAJE, razon="fuera"),
    ])
    ofertas = validar_scores(cosecha, lote)
    store = Store(str(tmp_path / "t.db"))
    md = reportar(cosecha, ofertas, store, "2026-07-23")
    # ambas persistidas (incluida la sin_puntaje) -> ya no son nuevas
    assert store.es_nueva(a) is False and store.es_nueva(b) is False
    assert "2026-07-23" in md and "Gerente" in md and "Analista" in md
    store.cerrar()


def test_puntuar_en_proceso_error_por_oferta_no_aborta():
    from jobwatch.modelos import EstadoOferta
    from jobwatch.nucleo import puntuar_en_proceso

    a, b, c = _v("1"), _v("2", titulo="B"), _v("3", titulo="C")
    cosecha = _cosecha_de([a, b, c])
    def flaky(v, cv):
        if v.id_nativo == "2":
            raise RuntimeError("timeout")
        return {"puntaje": 60, "razon": "ok"}
    lote = puntuar_en_proceso(cosecha, "cv", flaky)
    assert lote.run_id == cosecha.run_id
    por_id = {p.id_estable: p for p in lote.puntajes}
    assert por_id[a.id_estable].estado is EstadoOferta.PUNTUADA
    assert por_id[b.id_estable].estado is EstadoOferta.SIN_PUNTAJE  # el fallo cae a sin_puntaje


# --- Enriquecimiento con el detalle de la oferta (hallazgo #1) ---

def test_cosechar_enriquece_descripcion_vacia(tmp_path):
    """Computrabajo y elempleo emiten la tarjeta sin descripción; sin ella no se
    puede juzgar si la vacante exige inglés."""
    store = Store(str(tmp_path / "t.db"))
    v = _v("1", portal="computrabajo", titulo="Dev")
    cosecha = cosechar(
        Criterios(terminos="dev"), store, {"c": _ok([v])}, tope=50, fecha="2026-07-23",
        detalles={"computrabajo": lambda url: "Se requiere inglés B2 para este cargo."},
    )
    assert "inglés" in cosecha.candidatas[0].descripcion_raw
    store.cerrar()


def test_cosechar_no_refetchea_si_ya_hay_descripcion(tmp_path):
    """Indeed ya trae descripción: gastar una petición más sería puro desperdicio."""
    store = Store(str(tmp_path / "t.db"))
    v = _v("1", portal="indeed", titulo="Dev")
    v.descripcion_raw = "ya venía completa"
    llamadas = []
    cosechar(
        Criterios(terminos="dev"), store, {"i": _ok([v])}, tope=50, fecha="2026-07-23",
        detalles={"indeed": lambda url: llamadas.append(url) or "otra cosa"},
    )
    assert llamadas == []
    store.cerrar()


def test_cosechar_detalle_que_falla_no_tumba_la_corrida(tmp_path):
    """Fail-soft por vacante: una oferta cuyo detalle no carga sigue siendo
    candidata, solo que sin descripción."""
    store = Store(str(tmp_path / "t.db"))
    def explota(url):
        raise RuntimeError("timeout")
    cosecha = cosechar(
        Criterios(terminos="dev"), store,
        {"c": _ok([_v("1", portal="computrabajo", titulo="Dev")])},
        tope=50, fecha="2026-07-23", detalles={"computrabajo": explota},
    )
    assert len(cosecha.candidatas) == 1
    assert cosecha.candidatas[0].descripcion_raw == ""
    store.cerrar()


def test_cosechar_aplica_excluir_sobre_la_descripcion_traida(tmp_path):
    """El filtro `excluir` mira título+descripción. Si la descripción llega
    después del filtro, `excluir` nunca la ve: hay que re-filtrar tras enriquecer."""
    store = Store(str(tmp_path / "t.db"))
    cosecha = cosechar(
        Criterios(terminos="dev", excluir=["call center"]), store,
        {"c": _ok([_v("1", portal="computrabajo", titulo="Dev")])},
        tope=50, fecha="2026-07-23",
        detalles={"computrabajo": lambda url: "Operación de call center en turnos."},
    )
    assert cosecha.candidatas == []
    store.cerrar()


def test_cosechar_resuelve_modalidad_desconocida_desde_el_detalle(tmp_path):
    """Indeed deja vacantes en modalidad desconocida; si el detalle dice
    'presencial', el filtro de remoto debe poder descartarlas."""
    from jobwatch.modelos import Modalidad

    store = Store(str(tmp_path / "t.db"))
    cosecha = cosechar(
        Criterios(terminos="dev", modalidad=Modalidad.REMOTO), store,
        {"c": _ok([_v("1", portal="computrabajo", titulo="Dev")])},
        tope=50, fecha="2026-07-23",
        detalles={"computrabajo": lambda url: "Modalidad: presencial en Bogotá."},
    )
    assert cosecha.candidatas == []
    store.cerrar()
