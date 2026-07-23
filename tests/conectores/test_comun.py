from bs4 import BeautifulSoup

from jobwatch.conectores._comun import (
    coincide_termino, ejecutar, id_de_url, slug, texto,
)
from jobwatch.modelos import Criterios, EstadoConector, Vacante


def test_slug():
    assert slug("Gerente de Proyectos") == "gerente-de-proyectos"


def test_id_de_url_toma_digitos_finales():
    assert id_de_url("https://x/co/empleos/gestor-en-sitio-1004184") == "1004184"
    assert id_de_url("https://x/co/ofertas-trabajo/gerente-1886730317") == "1886730317"
    assert id_de_url("https://x/sin-numero") == ""


def test_texto_colapsa_espacios_y_tolera_none():
    sopa = BeautifulSoup("<a>  Hola   mundo\n </a>", "lxml")
    assert texto(sopa.a) == "Hola mundo"
    assert texto(None) == ""


def test_coincide_termino():
    assert coincide_termino("Gerente de proyectos", "gerente de proyectos") is True
    assert coincide_termino("Gestor de servicio en sitio", "gerente de proyectos") is False
    # acentos y mayúsculas no importan; 'de' es stopword y se ignora
    assert coincide_termino("GESTIÓN de Proyéctos TI", "proyectos") is True


def test_ejecutar_envuelve_exito_y_detalle():
    def extraer(html, c):
        v = Vacante(id_nativo="1", portal="x", titulo="T", empresa="E",
                    ubicacion="Bogotá", url="https://x/1")
        return [v], 2
    r = ejecutar(Criterios(terminos="t"), lambda c: "https://x",
                 fetch=lambda u: "<html></html>", extraer=extraer)
    assert r.estado is EstadoConector.OK and len(r.vacantes) == 1
    assert "2 filas omitidas" in r.detalle


def test_ejecutar_fetch_falla_es_error():
    def boom(u):
        raise RuntimeError("403 bloqueado")
    r = ejecutar(Criterios(terminos="t"), lambda c: "u",
                 fetch=boom, extraer=lambda h, c: ([], 0))
    assert r.estado is EstadoConector.ERROR and "403 bloqueado" in r.detalle
