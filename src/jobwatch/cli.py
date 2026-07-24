from __future__ import annotations

import argparse
import datetime as _dt
import sys
from pathlib import Path


def _conectores_reales() -> dict:
    from jobwatch.conectores import computrabajo, elempleo, indeed, magneto
    return {
        "computrabajo": computrabajo.buscar,
        "elempleo": elempleo.buscar,
        "magneto": magneto.buscar,
        "indeed": indeed.buscar,
    }


def _detalles_reales() -> dict:
    """Portal -> extractor de la descripción desde la página de la oferta. Solo
    los que emiten la tarjeta sin descripción; indeed ya la trae vía JobSpy."""
    from jobwatch.conectores import computrabajo, elempleo, magneto
    return {
        "computrabajo": computrabajo.detalle,
        "elempleo": elempleo.detalle,
        "magneto": magneto.detalle,
    }


def main(
    argv: list[str] | None = None,
    _conectores: dict | None = None,
    _puntuador=None,
    _detalles: dict | None = None,
) -> int:
    parser = argparse.ArgumentParser(prog="jobwatch", description="Agregador de empleos.")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_run = sub.add_parser("run", help="Corre la búsqueda y escribe el reporte.")
    p_run.add_argument("--terminos", default=None)
    p_run.add_argument("--config", default=None)
    p_run.add_argument("--ubicacion", default=None)
    p_run.add_argument("--cv", required=True, help="Ruta al archivo de CV (texto).")
    p_run.add_argument("--db", default="jobwatch.db")
    p_run.add_argument("--tope", type=int, default=50)

    p_carta = sub.add_parser("carta", help="Redacta una carta para una oferta guardada.")
    p_carta.add_argument("id_estable")
    p_carta.add_argument("--db", default="jobwatch.db")
    p_carta.add_argument("--cv", default="data/cv.txt", help="Ruta al archivo de CV (texto).")

    p_harvest = sub.add_parser("harvest", help="Cosecha candidatas (solo-lectura) y emite JSON.")
    p_harvest.add_argument("--config", required=True)
    p_harvest.add_argument("--db", default="jobwatch.db")
    p_harvest.add_argument("--tope", type=int, default=50)
    p_harvest.add_argument("--json", action="store_true", help="Emite JSON a stdout.")

    p_report = sub.add_parser("report", help="Valida puntajes y escribe el reporte.")
    p_report.add_argument("--candidatas", required=True)
    p_report.add_argument("--scores", required=True)
    p_report.add_argument("--fecha", default=None)
    p_report.add_argument("--db", default="jobwatch.db")

    args = parser.parse_args(argv)

    if args.cmd == "run":
        from jobwatch.config import cargar_criterios
        from jobwatch.llm import puntuador_real
        from jobwatch.modelos import Criterios
        from jobwatch.orquestador import correr
        from jobwatch.store import Store

        if args.config:
            criterios = cargar_criterios(args.config)
        elif args.terminos:
            criterios = Criterios(terminos=args.terminos, ubicacion=args.ubicacion)
        else:
            print("Error: pasa --config o --terminos.", file=sys.stderr)
            return 1

        cv = Path(args.cv).read_text(encoding="utf-8")
        store = Store(args.db)
        conectores = _conectores if _conectores is not None else _conectores_reales()
        puntuador = _puntuador if _puntuador is not None else puntuador_real
        fecha = _dt.date.today().isoformat()
        md, _ = correr(
            criterios, cv, store, puntuador, conectores, fecha, args.tope,
            detalles=_detalles if _detalles is not None else _detalles_reales(),
        )
        store.cerrar()

        destino = Path("reportes") / f"{fecha}.md"
        destino.parent.mkdir(exist_ok=True)
        destino.write_text(md, encoding="utf-8")
        print(f"Reporte escrito en {destino}")
        return 0

    if args.cmd == "carta":
        from jobwatch.cartas import redactar_desde_store

        ruta_cv = Path(args.cv)
        cv = ruta_cv.read_text(encoding="utf-8") if ruta_cv.exists() else ""
        if not cv.strip():
            print(f"Error: el CV en {ruta_cv} no existe o está vacío.", file=sys.stderr)
            return 1
        print(redactar_desde_store(args.id_estable, args.db, cv))
        return 0

    if args.cmd == "harvest":
        import json as _json

        from jobwatch.config import cargar_criterios
        from jobwatch.nucleo import TopeExcedido, cosechar
        from jobwatch.store import Store

        criterios = cargar_criterios(args.config)
        conectores = _conectores if _conectores is not None else _conectores_reales()
        store = Store(args.db)
        fecha = _dt.date.today().isoformat()
        try:
            cosecha = cosechar(
                criterios, store, conectores, args.tope, fecha,
                detalles=_detalles if _detalles is not None else _detalles_reales(),
            )
        except TopeExcedido as e:
            store.cerrar()
            print(_json.dumps({"error": str(e)}, ensure_ascii=False))
            return 1
        store.cerrar()

        salida = {
            "run_id": cosecha.run_id,
            "tope": cosecha.tope,
            "estados": {
                p: {"estado": r.estado.value, "detalle": r.detalle}
                for p, r in cosecha.estados.items()
            },
            "candidatas": [_json.loads(v.model_dump_json()) for v in cosecha.candidatas],
        }

        if args.json:
            print(_json.dumps(salida, ensure_ascii=False, indent=2))
        else:
            # Resumen en español
            print(f"{len(cosecha.candidatas)} candidatas nuevas (tope {cosecha.tope}, run_id {cosecha.run_id}).")
            for portal, r in cosecha.estados.items():
                detalle_str = f" — {r.detalle}" if r.detalle else ""
                print(f"  {portal}: {r.estado.value}{detalle_str}")
        return 0

    if args.cmd == "report":
        import json as _json

        from jobwatch.modelos import (
            Cosecha, EstadoConector, LotePuntajes, ResultadoConector, Vacante,
        )
        from jobwatch.nucleo import ScoresInvalidos, reportar, validar_scores
        from jobwatch.store import Store

        cand = _json.loads(Path(args.candidatas).read_text(encoding="utf-8"))
        estados = {
            p: ResultadoConector(estado=EstadoConector(e["estado"]), detalle=e.get("detalle", ""))
            for p, e in cand["estados"].items()
        }
        cosecha = Cosecha(
            run_id=cand["run_id"], tope=cand["tope"], estados=estados,
            candidatas=[Vacante(**v) for v in cand["candidatas"]],
        )
        lote = LotePuntajes.model_validate_json(Path(args.scores).read_text(encoding="utf-8"))

        store = Store(args.db)
        try:
            ofertas = validar_scores(cosecha, lote)
        except ScoresInvalidos as e:
            store.cerrar()
            print(f"Error de validación (scores inválidos): {e}", file=sys.stderr)
            return 1

        fecha = args.fecha or _dt.date.today().isoformat()
        md = reportar(cosecha, ofertas, store, fecha)
        store.cerrar()

        destino = Path("reportes") / f"{fecha}.md"
        destino.parent.mkdir(exist_ok=True)
        destino.write_text(md, encoding="utf-8")
        print(f"Reporte escrito en {destino}")
        return 0

    return 1


if __name__ == "__main__":
    raise SystemExit(main())
