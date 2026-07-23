import pytest

from jobwatch.modelos import EstadoOferta, Vacante
from jobwatch.matcher import puntuar, TopeExcedido


def _v(id_nativo):
    return Vacante(id_nativo=id_nativo, portal="indeed", titulo="Dev", empresa="ACME",
                   ubicacion="Bogotá", url=f"https://x/{id_nativo}")


def test_puntua_cada_oferta():
    def fake(v, cv):
        return {"puntaje": 80, "razon": "encaja"}
    res = puntuar([_v("1"), _v("2")], "mi cv", fake)
    assert [o.estado for o in res] == [EstadoOferta.PUNTUADA, EstadoOferta.PUNTUADA]
    assert res[0].puntaje == 80 and res[0].razon == "encaja"


def test_fallo_de_una_no_aborta_el_lote():
    def flaky(v, cv):
        if v.id_nativo == "2":
            raise RuntimeError("timeout")
        return {"puntaje": 50, "razon": "ok"}
    res = puntuar([_v("1"), _v("2"), _v("3")], "cv", flaky)
    assert [o.estado for o in res] == [
        EstadoOferta.PUNTUADA, EstadoOferta.ERROR, EstadoOferta.PUNTUADA,
    ]


def test_tope_excedido_no_llama_al_llm():
    llamadas = []
    def espia(v, cv):
        llamadas.append(v)
        return {"puntaje": 1, "razon": ""}
    with pytest.raises(TopeExcedido):
        puntuar([_v(str(i)) for i in range(5)], "cv", espia, tope=3)
    assert llamadas == []
