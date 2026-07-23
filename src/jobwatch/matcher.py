from __future__ import annotations

from typing import Callable

from jobwatch.modelos import Criterios, EstadoOferta, Modalidad, OfertaPuntuada, Vacante


def filtro_local(v: Vacante, c: Criterios) -> bool:
    texto = f"{v.titulo} {v.descripcion_raw}".lower()
    if any(kw.lower() in texto for kw in c.excluir):
        return False
    if c.salario_min is not None and v.salario_max is not None:
        if v.salario_max < c.salario_min:
            return False
    if c.modalidad is not None and v.modalidad is not Modalidad.DESCONOCIDO:
        if v.modalidad is not c.modalidad:
            return False
    return True


PuntuadorLLM = Callable[[Vacante, str], dict]


class TopeExcedido(Exception):
    pass


def puntuar(
    vacantes: list[Vacante],
    cv: str,
    puntuador: PuntuadorLLM,
    tope: int = 50,
) -> list[OfertaPuntuada]:
    if len(vacantes) > tope:
        raise TopeExcedido(
            f"{len(vacantes)} ofertas superan el tope de {tope}; "
            f"revisa el filtro local antes de gastar en el LLM."
        )
    resultado: list[OfertaPuntuada] = []
    for v in vacantes:
        try:
            r = puntuador(v, cv)
            resultado.append(
                OfertaPuntuada(
                    vacante=v, estado=EstadoOferta.PUNTUADA,
                    puntaje=int(r["puntaje"]), razon=str(r.get("razon", "")),
                )
            )
        except Exception as e:  # fail-loud per offer, no aborta el lote
            resultado.append(
                OfertaPuntuada(vacante=v, estado=EstadoOferta.ERROR, razon=str(e))
            )
    return resultado
