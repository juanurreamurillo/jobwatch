from __future__ import annotations

import hashlib
import re
import unicodedata
from enum import Enum

from pydantic import BaseModel, model_validator


class Modalidad(str, Enum):
    REMOTO = "remoto"
    HIBRIDO = "hibrido"
    PRESENCIAL = "presencial"
    DESCONOCIDO = "desconocido"


class EstadoConector(str, Enum):
    OK = "ok"
    ERROR = "error"
    SESION_EXPIRADA = "sesion_expirada"


class EstadoOferta(str, Enum):
    PUNTUADA = "puntuada"
    SIN_PUNTAJE = "sin_puntaje"
    ERROR = "error"


def _clave(texto: str) -> str:
    """Lowercase, strip accents and non-alphanumerics -> comparison key."""
    sin_acentos = "".join(
        c for c in unicodedata.normalize("NFKD", texto) if not unicodedata.combining(c)
    )
    sin_simbolos = "".join(c for c in sin_acentos.lower() if c.isalnum() or c == " ")
    return re.sub(r"\s+", " ", sin_simbolos).strip()


def _clave_ubicacion(texto: str) -> str:
    """Location-scoped comparison key: _clave() plus removal of a standalone
    'dc' token, the residue of the geographic modifier D.C. (Distrito Capital)."""
    clave = _clave(texto)
    sin_dc = re.sub(r"\bdc\b", "", clave)
    return re.sub(r"\s+", " ", sin_dc).strip()


def calcular_id_estable(portal: str, id_nativo: str) -> str:
    return hashlib.sha256(f"{portal}:{id_nativo}".encode()).hexdigest()[:16]


def calcular_fingerprint(empresa: str, titulo: str, ubicacion: str) -> str:
    crudo = "|".join((_clave(empresa), _clave(titulo), _clave_ubicacion(ubicacion)))
    return hashlib.sha256(crudo.encode()).hexdigest()[:16]


class Criterios(BaseModel):
    terminos: str
    ubicacion: str | None = None
    modalidad: Modalidad | None = None
    salario_min: int | None = None
    excluir: list[str] = []


class Vacante(BaseModel):
    id_nativo: str
    portal: str
    titulo: str
    empresa: str
    ubicacion: str
    modalidad: Modalidad = Modalidad.DESCONOCIDO
    salario_raw: str = ""
    salario_min: int | None = None
    salario_max: int | None = None
    url: str
    fecha_publicacion: str | None = None
    descripcion_raw: str = ""
    id_estable: str = ""
    fingerprint_contenido: str = ""

    @model_validator(mode="after")
    def _computar(self) -> "Vacante":
        object.__setattr__(self, "id_estable", calcular_id_estable(self.portal, self.id_nativo))
        object.__setattr__(
            self, "fingerprint_contenido",
            calcular_fingerprint(self.empresa, self.titulo, self.ubicacion),
        )
        return self


class OfertaPuntuada(BaseModel):
    vacante: Vacante
    estado: EstadoOferta
    puntaje: int | None = None
    razon: str = ""


class ResultadoConector(BaseModel):
    estado: EstadoConector
    vacantes: list[Vacante] = []
    detalle: str = ""
