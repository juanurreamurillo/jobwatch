import json

from jobwatch.cli import main
from jobwatch.modelos import EstadoConector, ResultadoConector, Vacante
from jobwatch.nucleo import calcular_run_id


def _preparar(tmp_path, run_id_scores=None):
    v = Vacante(id_nativo="1", portal="computrabajo", titulo="Gerente", empresa="ACME",
                ubicacion="Bogotá", url="https://x/1")
    run_id = calcular_run_id([v], "2026-07-23")
    candidatas = tmp_path / "cand.json"
    candidatas.write_text(json.dumps({
        "run_id": run_id, "tope": 50,
        "estados": {"computrabajo": {"estado": "ok", "detalle": ""}},
        "candidatas": [json.loads(v.model_dump_json())],
    }), encoding="utf-8")
    scores = tmp_path / "scores.json"
    scores.write_text(json.dumps({
        "run_id": run_id_scores or run_id,
        "puntajes": [{"id_estable": v.id_estable, "estado": "puntuada",
                      "puntaje": 88, "razon": "encaja"}],
    }), encoding="utf-8")
    return str(candidatas), str(scores), v


def test_report_valida_persiste_y_escribe(tmp_path, capsys, monkeypatch):
    monkeypatch.chdir(tmp_path)
    cand, scores, v = _preparar(tmp_path)
    db = str(tmp_path / "j.db")
    rc = main(["report", "--candidatas", cand, "--scores", scores,
               "--fecha", "2026-07-23", "--db", db])
    assert rc == 0
    reporte = tmp_path / "reportes" / "2026-07-23.md"
    assert reporte.exists() and "Gerente" in reporte.read_text(encoding="utf-8")
    from jobwatch.store import Store
    s = Store(db)
    assert s.es_nueva(v) is False  # persistida
    s.cerrar()


def test_report_run_id_desalineado_aborta(tmp_path, capsys):
    cand, scores, _ = _preparar(tmp_path, run_id_scores="viejo000")
    rc = main(["report", "--candidatas", cand, "--scores", scores,
               "--db", str(tmp_path / "j.db")])
    assert rc == 1
    assert "run_id" in capsys.readouterr().err


def test_run_con_config_y_conectores_inyectados(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    cfg = tmp_path / "c.json"
    cfg.write_text(json.dumps({"terminos": "gerente"}), encoding="utf-8")
    cv = tmp_path / "cv.txt"
    cv.write_text("Gerente de proyectos con 10 años.", encoding="utf-8")
    v = Vacante(id_nativo="1", portal="computrabajo", titulo="Gerente", empresa="ACME",
                ubicacion="Bogotá", url="https://x/1")
    conectores = {"computrabajo": lambda c: ResultadoConector(estado=EstadoConector.OK, vacantes=[v])}
    rc = main(
        ["run", "--config", str(cfg), "--cv", str(cv), "--db", str(tmp_path / "j.db")],
        _conectores=conectores, _puntuador=lambda vac, cv: {"puntaje": 91, "razon": "ok"},
    )
    assert rc == 0
    assert (tmp_path / "reportes").exists()
