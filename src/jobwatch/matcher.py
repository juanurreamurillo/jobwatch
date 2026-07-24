from __future__ import annotations

from datetime import date

from jobwatch.modelos import Criterios, Modalidad, Vacante


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


def filtro_recencia(v: Vacante, dias: int | None, hoy: date) -> bool:
    """Recorte de recencia central (D22). Conserva no-fechables (D19). `dias=None`
    = sin filtro. Predicado exacto (D16): datable pasa si (hoy - fecha).days < dias.
    Asume fecha_publicacion ya normalizada a ISO por cosechar."""
    if dias is None:
        return True
    if not v.fecha_publicacion:
        return True  # no fechable -> incluir marcada (D19)
    try:
        f = date.fromisoformat(v.fecha_publicacion[:10])
    except ValueError:
        return True
    return (hoy - f).days < dias
