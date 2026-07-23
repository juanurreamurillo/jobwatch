from __future__ import annotations

from jobwatch.modelos import Criterios, ResultadoConector
from jobwatch.nucleo import (  # noqa: F401  (re-export para compat)
    Conector,
    PuntuadorLLM,
    TopeExcedido,
    calcular_run_id,
    colapsar_lote,
    cosechar,
    puntuar_en_proceso,
    reportar,
    validar_scores,
)


def correr(
    criterios: Criterios,
    cv: str,
    store,
    puntuador,
    conectores: dict[str, "Conector"],
    fecha: str,
    tope: int = 50,
) -> tuple[str, dict[str, ResultadoConector]]:
    """Ruta API-key sobre el core: un solo pipeline, dos puntos de entrada (§4.4)."""
    cosecha = cosechar(criterios, store, conectores, tope, fecha)
    lote = puntuar_en_proceso(cosecha, cv, puntuador)
    ofertas = validar_scores(cosecha, lote)
    md = reportar(cosecha, ofertas, store, fecha)
    return md, cosecha.estados
