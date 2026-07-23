from __future__ import annotations

import json
import sqlite3

from jobwatch.modelos import EstadoConector, Vacante


class Store:
    def __init__(self, ruta: str = "jobwatch.db") -> None:
        self.con = sqlite3.connect(ruta)
        self._init_schema()

    def _init_schema(self) -> None:
        self.con.executescript(
            """
            CREATE TABLE IF NOT EXISTS vacantes (
                id_estable TEXT PRIMARY KEY,
                fingerprint_contenido TEXT NOT NULL,
                portal TEXT NOT NULL,
                titulo TEXT NOT NULL,
                empresa TEXT NOT NULL,
                url TEXT NOT NULL,
                datos TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_fingerprint
                ON vacantes(fingerprint_contenido);
            CREATE TABLE IF NOT EXISTS corridas (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                estados TEXT NOT NULL
            );
            """
        )
        self.con.commit()

    def es_nueva(self, v: Vacante) -> bool:
        cur = self.con.execute(
            "SELECT 1 FROM vacantes WHERE id_estable = ? OR fingerprint_contenido = ? LIMIT 1",
            (v.id_estable, v.fingerprint_contenido),
        )
        return cur.fetchone() is None

    def persistir(self, vacantes: list[Vacante]) -> None:
        self.con.executemany(
            """
            INSERT INTO vacantes
                (id_estable, fingerprint_contenido, portal, titulo, empresa, url, datos)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(id_estable) DO NOTHING
            """,
            [
                (v.id_estable, v.fingerprint_contenido, v.portal, v.titulo,
                 v.empresa, v.url, v.model_dump_json())
                for v in vacantes
            ],
        )
        self.con.commit()

    def registrar_corrida(self, estados: dict[str, EstadoConector]) -> int:
        serializable = {k: e.value for k, e in estados.items()}
        cur = self.con.execute(
            "INSERT INTO corridas (estados) VALUES (?)", (json.dumps(serializable),)
        )
        self.con.commit()
        return int(cur.lastrowid)

    def cerrar(self) -> None:
        self.con.close()
