from __future__ import annotations

from jobwatch.matcher import filtro_local, puntuar
from jobwatch.modelos import Criterios, EstadoConector, ResultadoConector, Vacante
from jobwatch.nucleo import Conector, TopeExcedido, calcular_run_id, colapsar_lote, cosechar  # noqa: F401
from jobwatch.reporte import render
from jobwatch.store import Store


def correr(
    criterios: Criterios,
    cv: str,
    store: Store,
    puntuador,
    conectores: dict[str, Conector],
    fecha: str,
    tope: int = 50,
) -> tuple[str, dict[str, ResultadoConector]]:
    resultados: dict[str, ResultadoConector] = {}
    cosechadas: list[Vacante] = []
    for nombre, conector in conectores.items():
        try:
            r = conector(criterios)
        except Exception as e:  # fail-loud sin abortar la corrida completa (D2)
            r = ResultadoConector(estado=EstadoConector.ERROR, detalle=str(e))
        resultados[nombre] = r
        cosechadas.extend(r.vacantes)

    nuevas = [
        v for v in colapsar_lote(cosechadas)
        if store.es_nueva(v) and filtro_local(v, criterios)
    ]

    ofertas = puntuar(nuevas, cv, puntuador, tope=tope)
    store.persistir(nuevas)
    store.registrar_corrida(resultados)
    return render(fecha, resultados, ofertas), resultados
