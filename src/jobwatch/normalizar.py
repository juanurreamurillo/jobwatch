# src/jobwatch/normalizar.py
from __future__ import annotations

import re

from jobwatch.modelos import Modalidad

_CIUDADES = {
    "bogota": "Bogotá", "bogotá": "Bogotá",
    "medellin": "Medellín", "medellín": "Medellín",
    "cali": "Cali", "barranquilla": "Barranquilla", "cartagena": "Cartagena",
}


def normalizar_texto(s: str) -> str:
    return re.sub(r"\s+", " ", s).strip()


def normalizar_ubicacion(s: str) -> str:
    s = normalizar_texto(s)
    # take the first segment before a comma, drop "D.C." and similar suffixes
    primero = s.split(",")[0]
    primero = re.sub(r"\bd\.?\s*c\b\.?", "", primero, flags=re.IGNORECASE).strip()
    return _CIUDADES.get(primero.lower(), primero)


def normalizar_modalidad(s: str) -> Modalidad:
    t = s.lower()
    if "remoto" in t or "teletrabajo" in t:
        return Modalidad.REMOTO
    if "híbrido" in t or "hibrido" in t:
        return Modalidad.HIBRIDO
    if "presencial" in t:
        return Modalidad.PRESENCIAL
    return Modalidad.DESCONOCIDO


def parsear_salario(s: str) -> tuple[int | None, int | None]:
    numeros = re.findall(r"\d[\d.]*", s)
    valores = [int(n.replace(".", "")) for n in numeros if len(n.replace(".", "")) >= 5]
    if not valores:
        return (None, None)
    if len(valores) == 1:
        return (valores[0], valores[0])
    return (min(valores), max(valores))
