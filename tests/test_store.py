import json
import sqlite3

from jobwatch.modelos import EstadoConector, ResultadoConector, Vacante
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
    id1 = s.registrar_corrida({"indeed": ResultadoConector(estado=EstadoConector.OK)})
    id2 = s.registrar_corrida({"indeed": ResultadoConector(estado=EstadoConector.ERROR)})
    assert id2 > id1
    s.cerrar()


def test_registrar_corrida_guarda_estado_y_detalle(tmp_path):
    import json
    from jobwatch.modelos import EstadoConector, ResultadoConector
    store = Store(str(tmp_path / "j.db"))
    store.registrar_corrida({"indeed": ResultadoConector(estado=EstadoConector.ERROR, detalle="x")})
    fila = store.con.execute("SELECT estados FROM corridas").fetchone()
    datos = json.loads(fila[0])
    assert datos["indeed"] == {"estado": "error", "detalle": "x"}
    store.cerrar()


def test_persistir_guarda_portales(tmp_path):
    ruta = str(tmp_path / "j.db")
    store = Store(ruta)
    from jobwatch.modelos import Vacante

    v = Vacante(id_nativo="1", portal="computrabajo", titulo="X", empresa="ACME",
                ubicacion="Bogotá", url="https://x/1", portales=["computrabajo", "magneto"])
    store.persistir([v])
    store.cerrar()
    con = sqlite3.connect(ruta)
    fila = con.execute("SELECT portales FROM vacantes WHERE id_estable = ?", (v.id_estable,)).fetchone()
    assert json.loads(fila[0]) == ["computrabajo", "magneto"]


def test_migra_base_v0_existente(tmp_path):
    ruta = str(tmp_path / "viejo.db")
    # base v0: tabla vacantes SIN columna portales, user_version 0
    con = sqlite3.connect(ruta)
    con.executescript(
        """
        CREATE TABLE vacantes (
            id_estable TEXT PRIMARY KEY, fingerprint_contenido TEXT NOT NULL,
            portal TEXT NOT NULL, titulo TEXT NOT NULL, empresa TEXT NOT NULL,
            url TEXT NOT NULL, datos TEXT NOT NULL);
        CREATE TABLE corridas (id INTEGER PRIMARY KEY AUTOINCREMENT, estados TEXT NOT NULL);
        """
    )
    con.commit()
    con.close()
    # abrir con Store debe migrar sin perder la fila y añadir la columna
    store = Store(ruta)
    assert store.con.execute("PRAGMA user_version").fetchone()[0] == 1
    cols = [r[1] for r in store.con.execute("PRAGMA table_info(vacantes)")]
    assert "portales" in cols
    store.cerrar()
