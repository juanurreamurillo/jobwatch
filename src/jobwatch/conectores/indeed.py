from __future__ import annotations

import math

from jobwatch.modelos import (
    Criterios, EstadoConector, Modalidad, ResultadoConector, Vacante,
)
from jobwatch.normalizar import normalizar_ubicacion, parsear_salario


def _sin_nan(x):
    """Coerce pandas NaN (a float) to None; pass everything else through."""
    if x is None or (isinstance(x, float) and math.isnan(x)):
        return None
    return x


def _id_nativo(fila: dict) -> str:
    return str(_sin_nan(fila.get("id")) or _sin_nan(fila.get("job_url")) or "")


def _modalidad(fila: dict) -> Modalidad:
    """JobSpy emite `is_remote` como bool real. `False` es información —el portal
    afirma que NO es remoto—, no ausencia; colapsarla en DESCONOCIDO la cuela por
    filtro_local, que deja pasar lo desconocido a propósito."""
    v = _sin_nan(fila.get("is_remote"))
    if v is None:
        return Modalidad.DESCONOCIDO
    return Modalidad.REMOTO if v else Modalidad.PRESENCIAL


def _a_vacante(fila: dict) -> Vacante:
    smin = _sin_nan(fila.get("min_amount"))
    smax = _sin_nan(fila.get("max_amount"))
    if smin is None and smax is None:
        smin, smax = parsear_salario(str(fila.get("salary", "") or ""))
    return Vacante(
        id_nativo=_id_nativo(fila),
        portal="indeed",
        titulo=str(fila.get("title", "")),
        empresa=str(fila.get("company", "")),
        ubicacion=normalizar_ubicacion(str(fila.get("location", ""))),
        modalidad=_modalidad(fila),
        salario_min=int(smin) if smin is not None else None,
        salario_max=int(smax) if smax is not None else None,
        url=str(fila.get("job_url", "")),
        fecha_publicacion=(
            str(_sin_nan(fila.get("date_posted")))[:10]
            if _sin_nan(fila.get("date_posted")) else None
        ),
        descripcion_raw=str(fila.get("description", "") or ""),
    )


def buscar(criterios: Criterios, scrape=None) -> ResultadoConector:
    if scrape is None:
        from jobspy import scrape_jobs as scrape  # imported lazily to keep tests offline

    try:
        df = scrape(
            site_name=["indeed"],
            search_term=criterios.terminos,
            location=criterios.ubicacion or "Colombia",
            country_indeed="colombia",
            is_remote=criterios.modalidad is Modalidad.REMOTO,
            hours_old=24 * criterios.dias if criterios.dias else None,
        )
        filas = df.to_dict("records")
    except Exception as e:  # fail-loud (D4): JobSpy is not under our control
        return ResultadoConector(estado=EstadoConector.ERROR, detalle=str(e))

    vacantes = []
    omitidas = 0
    for f in filas:
        if not _id_nativo(f):
            omitidas += 1
            continue
        try:
            vacantes.append(_a_vacante(f))
        except Exception:
            omitidas += 1

    if omitidas:
        return ResultadoConector(
            estado=EstadoConector.OK,
            vacantes=vacantes,
            detalle=f"{omitidas} filas omitidas por datos inválidos",
        )
    return ResultadoConector(estado=EstadoConector.OK, vacantes=vacantes)
