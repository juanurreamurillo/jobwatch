from __future__ import annotations

import hashlib
from typing import Callable

from jobwatch.matcher import filtro_local
from jobwatch.modelos import (
    Cosecha,
    Criterios,
    EstadoConector,
    PRIORIDAD_PORTAL,
    ResultadoConector,
    Vacante,
)

Conector = Callable[[Criterios], ResultadoConector]


class TopeExcedido(Exception):
    pass


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


def calcular_run_id(candidatas: list[Vacante], fecha: str) -> str:
    """Hash determinista del conjunto ordenado de id_estable + fecha (§4.1).
    Liga una cosecha a sus puntajes; independiente del orden de las candidatas."""
    ids = "|".join(sorted(v.id_estable for v in candidatas))
    return hashlib.sha256(f"{fecha}|{ids}".encode()).hexdigest()[:8]


def cosechar(
    criterios: Criterios,
    store,
    conectores: dict[str, Conector],
    tope: int,
    fecha: str,
) -> Cosecha:
    """Fase 1, determinista y SOLO-LECTURA (D13): corre conectores, deduplica
    (en-lote + cross-run), filtra localmente, hace cumplir el tope (D15). No persiste."""
    estados: dict[str, ResultadoConector] = {}
    cosechadas: list[Vacante] = []
    for nombre, conector in conectores.items():
        try:
            r = conector(criterios)
        except Exception as e:  # fail-loud sin abortar la corrida (D2)
            r = ResultadoConector(estado=EstadoConector.ERROR, detalle=str(e))
        estados[nombre] = r
        cosechadas.extend(r.vacantes)

    nuevas = [
        v for v in colapsar_lote(cosechadas)
        if store.es_nueva(v) and filtro_local(v, criterios)
    ]
    if len(nuevas) > tope:
        raise TopeExcedido(
            f"tope excedido: {len(nuevas)} > {tope}; revisa el filtro local "
            f"antes de involucrar al LLM."
        )
    return Cosecha(
        run_id=calcular_run_id(nuevas, fecha),
        tope=tope,
        estados=estados,
        candidatas=nuevas,
    )
