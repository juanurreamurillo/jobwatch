from __future__ import annotations

import json
import os

from jobwatch.modelos import Vacante

_MODELO = "claude-sonnet-5"


def _cliente():
    from anthropic import Anthropic

    return Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])


def generar_texto(prompt: str) -> str:
    msg = _cliente().messages.create(
        model=_MODELO, max_tokens=1024,
        messages=[{"role": "user", "content": prompt}],
    )
    return msg.content[0].text


def puntuador_real(v: Vacante, cv: str) -> dict:
    prompt = (
        "Evalúa qué tan bien encaja esta vacante con el CV. "
        'Responde SOLO un JSON {"puntaje": 0-100, "razon": "una frase"}.\n\n'
        f"Vacante: {v.titulo} en {v.empresa}. {v.descripcion_raw}\n\nCV:\n{cv}\n"
    )
    return json.loads(generar_texto(prompt))
