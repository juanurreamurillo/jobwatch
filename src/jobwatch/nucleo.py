from __future__ import annotations

import hashlib
from datetime import date
from typing import Callable

from jobwatch.matcher import filtro_local, filtro_recencia
from jobwatch.modelos import (
    Cosecha,
    Criterios,
    EstadoConector,
    EstadoOferta,
    LotePuntajes,
    OfertaPuntuada,
    PRIORIDAD_PORTAL,
    Puntaje,
    ResultadoConector,
    Vacante,
)
from jobwatch.normalizar import normalizar_fecha_publicacion
from jobwatch.reporte import render

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

    hoy = date.fromisoformat(fecha)
    for v in cosechadas:
        v.fecha_publicacion = normalizar_fecha_publicacion(v.fecha_publicacion, hoy)

    nuevas = [
        v for v in colapsar_lote(cosechadas)
        if store.es_nueva(v)
        and filtro_local(v, criterios)
        and filtro_recencia(v, criterios.dias, hoy)
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


class ScoresInvalidos(Exception):
    pass


def validar_scores(cosecha: Cosecha, lote: LotePuntajes) -> list[OfertaPuntuada]:
    """Fail-loud (D14): exige run_id igual, cobertura TOTAL de id_estable (ni
    faltantes ni inventadas) y puntaje ∈ 0–100 en las puntuadas. Aborta si no."""
    if lote.run_id != cosecha.run_id:
        raise ScoresInvalidos(
            f"run_id desalineado: scores={lote.run_id!r} != candidatas={cosecha.run_id!r}"
        )

    ids_candidatas = {v.id_estable for v in cosecha.candidatas}
    ids_scores = {p.id_estable for p in lote.puntajes}
    if ids_scores != ids_candidatas:
        faltan = ids_candidatas - ids_scores
        sobran = ids_scores - ids_candidatas
        raise ScoresInvalidos(f"cobertura incompleta: faltan={faltan} inventadas={sobran}")

    por_id = {p.id_estable: p for p in lote.puntajes}
    for p in lote.puntajes:
        if p.estado is EstadoOferta.PUNTUADA:
            if p.puntaje is None or not (0 <= p.puntaje <= 100):
                raise ScoresInvalidos(
                    f"puntaje fuera de rango 0–100 para {p.id_estable}: {p.puntaje}"
                )

    ofertas: list[OfertaPuntuada] = []
    for v in cosecha.candidatas:
        p = por_id[v.id_estable]
        ofertas.append(OfertaPuntuada(
            vacante=v, estado=p.estado, puntaje=p.puntaje, razon=p.razon,
        ))
    return ofertas


def reportar(cosecha: Cosecha, ofertas: list[OfertaPuntuada], store, fecha: str) -> str:
    """Fase 3, determinista: persiste TODAS las candidatas (puntuadas + sin_puntaje,
    D13) con el hecho multi-portal, registra la corrida con detalle, y renderiza."""
    store.persistir(cosecha.candidatas)
    store.registrar_corrida(cosecha.estados)
    return render(fecha, cosecha.estados, ofertas)


PuntuadorLLM = Callable[[Vacante, str], dict]


def puntuar_en_proceso(cosecha: Cosecha, cv: str, puntuador: PuntuadorLLM) -> LotePuntajes:
    """Ruta API-key (§4.4): puntúa cada candidata con el callable del SDK y arma
    el LotePuntajes que luego valida validar_scores. Fail-loud por oferta."""
    puntajes: list[Puntaje] = []
    for v in cosecha.candidatas:
        try:
            r = puntuador(v, cv)
            puntajes.append(Puntaje(
                id_estable=v.id_estable, estado=EstadoOferta.PUNTUADA,
                puntaje=int(r["puntaje"]), razon=str(r.get("razon", "")),
            ))
        except Exception as e:  # no aborta el lote
            puntajes.append(Puntaje(
                id_estable=v.id_estable, estado=EstadoOferta.SIN_PUNTAJE, razon=str(e),
            ))
    return LotePuntajes(run_id=cosecha.run_id, puntajes=puntajes)
