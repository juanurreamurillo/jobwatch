from __future__ import annotations

from jobwatch.modelos import EstadoConector, EstadoOferta, OfertaPuntuada, ResultadoConector


def _orden(o: OfertaPuntuada) -> int:
    # scored offers first (higher score first), unscored/error last
    return -(o.puntaje if o.estado is EstadoOferta.PUNTUADA and o.puntaje is not None else -1)


def render(
    fecha: str,
    resultados: dict[str, ResultadoConector],
    ofertas: list[OfertaPuntuada],
) -> str:
    lineas = [f"# Vacantes nuevas — {fecha}", ""]

    lineas.append("## Estado de conectores")
    for portal, r in resultados.items():
        marca = "⚠️ ERROR" if r.estado is EstadoConector.ERROR else r.estado.value.upper()
        extra = f" — {r.detalle}" if r.detalle else ""
        lineas.append(f"- **{portal}**: {marca}{extra}")
    lineas.append("")

    lineas.append(f"## Ofertas ({len(ofertas)})")
    if not ofertas:
        lineas.append("_Sin ofertas nuevas en esta corrida._")
    for o in sorted(ofertas, key=_orden):
        v = o.vacante
        puntaje = o.puntaje if o.estado is EstadoOferta.PUNTUADA else "—"
        multi = ""
        if len(v.portales) > 1:
            multi = f"\n- Vista en {len(v.portales)} portales: {', '.join(v.portales)}"
        lineas.append(
            f"### [{v.titulo}]({v.url}) · {puntaje}\n"
            f"- Empresa: {v.empresa}\n"
            f"- Ubicación: {v.ubicacion}\n"
            f"- Motivo: {o.razon}{multi}\n"
        )
    return "\n".join(lineas)
