from __future__ import annotations

import json
import os
import re

from jobwatch.modelos import Vacante

_MODELO = "claude-sonnet-5"


def _cliente():
    from anthropic import Anthropic

    return Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])


def _extraer_texto(bloques) -> str:
    """Return the first text block's text from an Anthropic message content list."""
    return next((b.text for b in bloques if getattr(b, "type", None) == "text"), "")


def _extraer_json(texto: str) -> dict:
    """Extract the first {...} JSON object from model text, tolerating fences/prose."""
    m = re.search(r"\{.*\}", texto, re.DOTALL)
    if not m:
        raise ValueError(f"El modelo no devolvió JSON: {texto[:120]!r}")
    return json.loads(m.group(0))


def generar_texto(prompt: str) -> str:
    msg = _cliente().messages.create(
        model=_MODELO, max_tokens=1024,
        messages=[{"role": "user", "content": prompt}],
    )
    return _extraer_texto(msg.content)


def puntuador_real(v: Vacante, cv: str) -> dict:
    prompt = (
        "Evalúa qué tan bien encaja esta vacante con el CV. "
        'Responde SOLO un JSON {"puntaje": 0-100, "razon": "una frase"}.\n\n'
        f"Vacante: {v.titulo} en {v.empresa}. {v.descripcion_raw}\n\nCV:\n{cv}\n"
    )
    return _extraer_json(generar_texto(prompt))
