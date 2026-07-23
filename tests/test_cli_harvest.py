import json

from jobwatch.cli import main
from jobwatch.modelos import EstadoConector, ResultadoConector, Vacante


def _config(tmp_path):
    ruta = tmp_path / "c.json"
    ruta.write_text(json.dumps({"terminos": "dev"}), encoding="utf-8")
    return str(ruta)


def _conectores_falsos():
    v = Vacante(id_nativo="1", portal="computrabajo", titulo="Dev", empresa="ACME",
                ubicacion="Bogotá", url="https://x/1")
    return {"computrabajo": lambda c: ResultadoConector(estado=EstadoConector.OK, vacantes=[v])}


def test_harvest_emite_json_y_no_toca_bd(tmp_path, capsys):
    db = str(tmp_path / "j.db")
    rc = main([
        "harvest", "--config", _config(tmp_path), "--db", db, "--json",
    ], _conectores=_conectores_falsos())
    assert rc == 0
    salida = json.loads(capsys.readouterr().out)
    assert salida["tope"] == 50
    assert salida["estados"]["computrabajo"]["estado"] == "ok"
    assert len(salida["candidatas"]) == 1
    assert salida["candidatas"][0]["titulo"] == "Dev"
    # solo-lectura: reabrir el store lo ve como nuevo
    from jobwatch.store import Store
    s = Store(db)
    assert s.es_nueva(Vacante(**salida["candidatas"][0])) is True
    s.cerrar()


def test_harvest_tope_excedido_error_json(tmp_path, capsys):
    def muchos(c):
        vs = [Vacante(id_nativo=str(i), portal="computrabajo", titulo=f"Dev {i}",
                      empresa="ACME", ubicacion="Bogotá", url=f"https://x/{i}") for i in range(4)]
        return ResultadoConector(estado=EstadoConector.OK, vacantes=vs)
    rc = main([
        "harvest", "--config", _config(tmp_path), "--db", str(tmp_path / "j.db"),
        "--tope", "2", "--json",
    ], _conectores={"computrabajo": muchos})
    assert rc == 1
    assert "error" in json.loads(capsys.readouterr().out)


def test_harvest_sin_json_imprime_resumen_español(tmp_path, capsys):
    db = str(tmp_path / "j.db")
    rc = main([
        "harvest", "--config", _config(tmp_path), "--db", db,
    ], _conectores=_conectores_falsos())
    assert rc == 0
    salida = capsys.readouterr().out
    # debe NO ser JSON válido
    try:
        json.loads(salida)
        assert False, "Sin --json debe imprimir resumen, no JSON"
    except json.JSONDecodeError:
        pass  # esperado: no es JSON
    # debe contener marcadores en español
    assert "candidatas" in salida.lower()
    assert "computrabajo" in salida
    assert not salida.strip().startswith("{")
