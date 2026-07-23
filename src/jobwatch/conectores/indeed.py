from __future__ import annotations

from jobwatch.modelos import (
    Criterios, EstadoConector, Modalidad, ResultadoConector, Vacante,
)
from jobwatch.normalizar import normalizar_ubicacion, parsear_salario


def _id_nativo(fila: dict) -> str:
    return str(fila.get("id") or fila.get("job_url") or "")


def _a_vacante(fila: dict) -> Vacante:
    smin = fila.get("min_amount")
    smax = fila.get("max_amount")
    if smin is None and smax is None:
        smin, smax = parsear_salario(str(fila.get("salary", "") or ""))
    return Vacante(
        id_nativo=_id_nativo(fila),
        portal="indeed",
        titulo=str(fila.get("title", "")),
        empresa=str(fila.get("company", "")),
        ubicacion=normalizar_ubicacion(str(fila.get("location", ""))),
        modalidad=Modalidad.REMOTO if fila.get("is_remote") else Modalidad.DESCONOCIDO,
        salario_min=int(smin) if smin is not None else None,
        salario_max=int(smax) if smax is not None else None,
        url=str(fila.get("job_url", "")),
        fecha_publicacion=str(fila.get("date_posted")) if fila.get("date_posted") else None,
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
        )
        filas = df.to_dict("records")
    except Exception as e:  # fail-loud (D4): JobSpy is not under our control
        return ResultadoConector(estado=EstadoConector.ERROR, detalle=str(e))

    vacantes = [_a_vacante(f) for f in filas if _id_nativo(f)]
    return ResultadoConector(estado=EstadoConector.OK, vacantes=vacantes)
