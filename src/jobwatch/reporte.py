from __future__ import annotations

from jobwatch.modelos import EstadoConector, EstadoOferta, OfertaPuntuada


def _orden(o: OfertaPuntuada) -> int:
    # scored offers first (higher score first), unscored/error last
    return -(o.puntaje if o.estado is EstadoOferta.PUNTUADA and o.puntaje is not None else -1)


def render(
    fecha: str,
    estados: dict[str, EstadoConector],
    ofertas: list[OfertaPuntuada],
) -> str:
    lineas = [f"# Vacantes nuevas — {fecha}", ""]

    lineas.append("## Estado de conectores")
    for portal, estado in estados.items():
        marca = "⚠️ ERROR" if estado is EstadoConector.ERROR else estado.value.upper()
        lineas.append(f"- **{portal}**: {marca}")
    lineas.append("")

    lineas.append(f"## Ofertas ({len(ofertas)})")
    if not ofertas:
        lineas.append("_Sin ofertas nuevas en esta corrida._")
    for o in sorted(ofertas, key=_orden):
        v = o.vacante
        puntaje = o.puntaje if o.estado is EstadoOferta.PUNTUADA else "—"
        lineas.append(
            f"### [{v.titulo}]({v.url}) · {puntaje}\n"
            f"- Empresa: {v.empresa}\n"
            f"- Ubicación: {v.ubicacion}\n"
            f"- Motivo: {o.razon}\n"
        )
    return "\n".join(lineas)
