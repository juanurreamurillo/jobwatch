from __future__ import annotations

from typing import Callable

from jobwatch.matcher import filtro_local, puntuar
from jobwatch.modelos import Criterios, EstadoConector, ResultadoConector
from jobwatch.reporte import render
from jobwatch.store import Store

Conector = Callable[[Criterios], ResultadoConector]


def correr(
    criterios: Criterios,
    cv: str,
    store: Store,
    puntuador,
    conectores: dict[str, Conector],
    fecha: str,
    tope: int = 50,
) -> tuple[str, dict[str, EstadoConector]]:
    estados: dict[str, EstadoConector] = {}
    nuevas = []
    for nombre, conector in conectores.items():
        r = conector(criterios)
        estados[nombre] = r.estado
        for v in r.vacantes:
            if store.es_nueva(v) and filtro_local(v, criterios):
                nuevas.append(v)

    ofertas = puntuar(nuevas, cv, puntuador, tope=tope)
    store.persistir(nuevas)
    store.registrar_corrida(estados)
    return render(fecha, estados, ofertas), estados
