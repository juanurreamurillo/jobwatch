from __future__ import annotations

from typing import Callable

from jobwatch.matcher import filtro_local, puntuar
from jobwatch.modelos import Criterios, EstadoConector, PRIORIDAD_PORTAL, ResultadoConector, Vacante
from jobwatch.reporte import render
from jobwatch.store import Store

Conector = Callable[[Criterios], ResultadoConector]


def _prioridad(portal: str) -> int:
    return PRIORIDAD_PORTAL.index(portal) if portal in PRIORIDAD_PORTAL else len(PRIORIDAD_PORTAL)


def colapsar_lote(vacantes: list[Vacante]) -> list[Vacante]:
    """Colapsa por fingerprint_contenido dentro del lote (D11): elige la fila
    canónica por PRIORIDAD_PORTAL y fija portales = unión ordenada por prioridad."""
    grupos: dict[str, list[Vacante]] = {}
    for v in vacantes:
        grupos.setdefault(v.fingerprint_contenido, []).append(v)

    salida: list[Vacante] = []
    for grupo in grupos.values():
        canon = min(grupo, key=lambda v: (_prioridad(v.portal), v.portal, v.id_nativo))
        portales = sorted({v.portal for v in grupo}, key=lambda p: (_prioridad(p), p))
        canon.portales = portales
        salida.append(canon)
    return salida


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
