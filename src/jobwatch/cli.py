from __future__ import annotations

import argparse
import datetime as _dt
from pathlib import Path


def main(argv: list[str] | None = None) -> int:
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

    args = parser.parse_args(argv)

    if args.cmd == "run":
        from jobwatch.conectores import indeed
        from jobwatch.llm import puntuador_real
        from jobwatch.modelos import Criterios
        from jobwatch.orquestador import correr
        from jobwatch.store import Store

        cv = Path(args.cv).read_text(encoding="utf-8")
        criterios = Criterios(terminos=args.terminos, ubicacion=args.ubicacion)
        store = Store(args.db)
        conectores = {"indeed": indeed.buscar}
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
        print(redactar_desde_store(args.id_estable, args.db))
        return 0

    return 1


if __name__ == "__main__":
    raise SystemExit(main())
