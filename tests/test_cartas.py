from jobwatch.modelos import Vacante
from jobwatch.cartas import redactar


def test_redactar_usa_generador_inyectado():
    v = Vacante(id_nativo="1", portal="indeed", titulo="Gerente de Proyectos TI",
                empresa="ACME", ubicacion="Bogotá", url="https://x/1")
    capturado = {}
    def fake_generar(prompt: str) -> str:
        capturado["prompt"] = prompt
        return "Estimados de ACME, ..."
    carta = redactar(v, "PM con 10 años de experiencia en entrega de software…", fake_generar)
    assert carta.startswith("Estimados de ACME")
    # el prompt debe incorporar el cargo y la empresa
    assert "Gerente de Proyectos TI" in capturado["prompt"]
    assert "ACME" in capturado["prompt"]
