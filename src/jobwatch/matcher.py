from __future__ import annotations

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
