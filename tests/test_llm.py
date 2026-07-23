from jobwatch.llm import _extraer_texto, _extraer_json


class _B:
    def __init__(self, type, text=None):
        self.type = type
        self.text = text


def test_extraer_texto_salta_bloque_thinking():
    bloques = [_B("thinking"), _B("text", "hola")]
    assert _extraer_texto(bloques) == "hola"


def test_extraer_texto_sin_texto_devuelve_vacio():
    assert _extraer_texto([_B("thinking")]) == ""


def test_extraer_json_tolera_fences_y_prosa():
    assert _extraer_json('Claro:\n```json\n{"puntaje": 80, "razon": "ok"}\n```') == {"puntaje": 80, "razon": "ok"}
