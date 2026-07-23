from jobwatch.modelos import EstadoConector, Vacante
from jobwatch.store import Store


def _v(id_nativo="1", portal="indeed", empresa="ACME", titulo="Dev", ubicacion="Bogotá"):
    return Vacante(id_nativo=id_nativo, portal=portal, empresa=empresa, titulo=titulo,
                   ubicacion=ubicacion, url=f"https://x/{id_nativo}")


def test_es_nueva_true_para_store_vacio(tmp_path):
    s = Store(str(tmp_path / "t.db"))
    assert s.es_nueva(_v()) is True
    s.cerrar()


def test_persistir_hace_que_deje_de_ser_nueva(tmp_path):
    s = Store(str(tmp_path / "t.db"))
    v = _v()
    s.persistir([v])
    assert s.es_nueva(v) is False
    s.cerrar()


def test_dedup_secundaria_por_fingerprint(tmp_path):
    s = Store(str(tmp_path / "t.db"))
    s.persistir([_v(id_nativo="1", portal="computrabajo")])
    # misma oferta, otro portal + otro id nativo -> distinto id_estable, MISMO fingerprint
    otra = _v(id_nativo="2", portal="elempleo")
    assert s.es_nueva(otra) is False
    s.cerrar()


def test_registrar_corrida_devuelve_id_incremental(tmp_path):
    s = Store(str(tmp_path / "t.db"))
    id1 = s.registrar_corrida({"indeed": EstadoConector.OK})
    id2 = s.registrar_corrida({"indeed": EstadoConector.ERROR})
    assert id2 > id1
    s.cerrar()
