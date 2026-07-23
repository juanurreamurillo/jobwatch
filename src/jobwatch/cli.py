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


def main(argv: list[str] | None = None, _conectores: dict | None = None) -> int:
    parser = argparse.ArgumentParser(prog="jobwatch", description="Agregador de empleos.")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_run = sub.add_parser("run", help="Corre la búsqueda y escribe el reporte.")
    p_run.add_argument("--terminos", required=True)
    p_run.add_argument("--ubicacion", default=None)
    p_run.add_argument("--cv", required=True, help="Ruta al archivo de CV (texto).")
    p_run.add_argument("--db", default="jobwatch.db")

    p_carta = sub.add_parser("carta", help="Redacta una carta para una oferta guardada.")
    p_carta.add_argument("id_estable")
    p_carta.add_argument("--db", default="jobwatch.db")
    p_carta.add_argument("--cv", default="data/cv.txt", help="Ruta al archivo de CV (texto).")

    p_harvest = sub.add_parser("harvest", help="Cosecha candidatas (solo-lectura) y emite JSON.")
    p_harvest.add_argument("--config", required=True)
    p_harvest.add_argument("--db", default="jobwatch.db")
    p_harvest.add_argument("--tope", type=int, default=50)
    p_harvest.add_argument("--json", action="store_true", help="Emite JSON a stdout.")

    args = parser.parse_args(argv)

    if args.cmd == "run":
        from jobwatch.conectores import computrabajo, elempleo, indeed, magneto
        from jobwatch.llm import puntuador_real
        from jobwatch.modelos import Criterios
        from jobwatch.orquestador import correr
        from jobwatch.store import Store

        cv = Path(args.cv).read_text(encoding="utf-8")
        criterios = Criterios(terminos=args.terminos, ubicacion=args.ubicacion)
        store = Store(args.db)
        conectores = {
            "computrabajo": computrabajo.buscar,
            "elempleo": elempleo.buscar,
            "magneto": magneto.buscar,
            "indeed": indeed.buscar,
        }
        fecha = _dt.date.today().isoformat()
        md, _ = correr(criterios, cv, store, puntuador_real, conectores, fecha)
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
            cosecha = cosechar(criterios, store, conectores, args.tope, fecha)
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
        print(_json.dumps(salida, ensure_ascii=False, indent=2))
        return 0

    return 1


if __name__ == "__main__":
    raise SystemExit(main())
