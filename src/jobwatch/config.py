from __future__ import annotations

from pathlib import Path

from jobwatch.modelos import Criterios


def cargar_criterios(ruta: str) -> Criterios:
    """Deserializa un archivo JSON de configuración a Criterios (§4.6).
    Compartido por la skill (harvest) y la ruta cron (run)."""
    texto = Path(ruta).read_text(encoding="utf-8")
    return Criterios.model_validate_json(texto)
