from __future__ import annotations

import json
from typing import Callable

from jobwatch.modelos import Vacante


def redactar(v: Vacante, cv: str, generar: Callable[[str], str]) -> str:
    prompt = (
        "Redacta una carta de presentación breve y profesional en español "
        f"para la vacante «{v.titulo}» en {v.empresa} ({v.ubicacion}).\n\n"
        f"Descripción de la vacante:\n{v.descripcion_raw}\n\n"
        f"Perfil del candidato (CV):\n{cv}\n"
    )
    return generar(prompt)


def redactar_desde_store(id_estable: str, db: str) -> str:
    import sqlite3

    from jobwatch.llm import generar_texto

    con = sqlite3.connect(db)
    try:
        fila = con.execute(
            "SELECT datos FROM vacantes WHERE id_estable = ?", (id_estable,)
        ).fetchone()
    finally:
        con.close()
    if fila is None:
        raise ValueError(f"No existe una oferta con id_estable={id_estable}")
    v = Vacante(**json.loads(fila[0]))
    cv = _leer_cv_por_defecto()
    return redactar(v, cv, generar_texto)


def _leer_cv_por_defecto() -> str:
    from pathlib import Path

    ruta = Path("data/cv.txt")
    return ruta.read_text(encoding="utf-8") if ruta.exists() else ""
