import json

from jobwatch.config import cargar_criterios
from jobwatch.modelos import Modalidad


def test_cargar_criterios_completo(tmp_path):
    ruta = tmp_path / "c.json"
    ruta.write_text(json.dumps({
        "terminos": "Gerente de Proyectos TI",
        "ubicacion": "Colombia",
        "modalidad": "remoto",
        "salario_min": 5000000,
        "excluir": ["ventas"],
    }), encoding="utf-8")
    c = cargar_criterios(str(ruta))
    assert c.terminos == "Gerente de Proyectos TI"
    assert c.modalidad is Modalidad.REMOTO
    assert c.excluir == ["ventas"]


def test_cargar_criterios_minimo(tmp_path):
    ruta = tmp_path / "c.json"
    ruta.write_text(json.dumps({"terminos": "dev"}), encoding="utf-8")
    c = cargar_criterios(str(ruta))
    assert c.terminos == "dev" and c.ubicacion is None


def test_config_carga_dias(tmp_path):
    p = tmp_path / "c.json"
    p.write_text(json.dumps({"terminos": "x", "dias": 2}), encoding="utf-8")
    assert cargar_criterios(str(p)).dias == 2
