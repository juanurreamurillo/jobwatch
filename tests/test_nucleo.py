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
    conectores = {"indeed": _ok([_v("1"), _v("2", titulo="Nueva")])}
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
