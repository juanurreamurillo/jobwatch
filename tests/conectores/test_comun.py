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


def _v(i):
    return Vacante(id_nativo=str(i), portal="x", titulo=f"t{i}", empresa="e",
                   ubicacion="u", url=f"http://x/{i}")


def test_ejecutar_pagina_hasta_pagina_vacia():
    paginas = {1: "p1", 2: "p2", 3: ""}  # p3 vacía = fin
    urls = []
    def url_fn(c, p):
        urls.append(p)
        return paginas.get(p, "")
    def extraer(html, c):
        if not html:
            return ([], 0, 0)           # n_crudo=0 -> parada
        n = 1 if html == "p1" else 1
        return ([_v(html)], 0, n)       # 1 tarjeta cruda
    r = ejecutar(Criterios(terminos="x"), url_fn, lambda u: u, extraer)
    assert r.estado is EstadoConector.OK
    assert [v.titulo for v in r.vacantes] == ["tp1", "tp2"]
    assert urls == [1, 2, 3]            # visitó hasta la vacía y paró


def test_ejecutar_para_por_crudo_no_por_filtrado():
    # página intermedia con tarjetas crudas pero 0 vacantes filtradas NO para
    def url_fn(c, p): return f"p{p}" if p <= 3 else ""
    def extraer(html, c):
        if html == "":
            return ([], 0, 0)
        if html == "p2":
            return ([], 0, 20)   # 20 crudas, 0 tras filtrar
        return ([_v(html)], 0, 20)
    r = ejecutar(Criterios(terminos="x"), url_fn, lambda u: u, extraer)
    assert [v.titulo for v in r.vacantes] == ["tp1", "tp3"]  # p2 no cortó


def test_ejecutar_tope_paginas_declara_parcial():
    def url_fn(c, p): return f"p{p}"        # nunca vacía
    def extraer(html, c): return ([_v(html)], 0, 20)
    r = ejecutar(Criterios(terminos="x"), url_fn, lambda u: u, extraer, max_paginas=3)
    assert r.estado is EstadoConector.OK
    assert "tope" in r.detalle.lower()      # cobertura parcial declarada (B2)


def test_ejecutar_error_en_pagina1_es_error():
    def url_fn(c, p): return f"p{p}"
    def boom(u): raise RuntimeError("bloqueado")
    r = ejecutar(Criterios(terminos="x"), url_fn, boom, lambda h, c: ([], 0, 0))
    assert r.estado is EstadoConector.ERROR


def test_ejecutar_error_tras_pagina1_es_parcial():
    def url_fn(c, p): return f"p{p}"
    def fetch(u):
        if u == "p2":
            raise RuntimeError("500")
        return u
    def extraer(html, c): return ([_v(html)], 0, 20)
    r = ejecutar(Criterios(terminos="x"), url_fn, fetch, extraer)
    assert r.estado is EstadoConector.OK
    assert [v.titulo for v in r.vacantes] == ["tp1"]
    assert "página 2" in r.detalle.lower() or "pagina 2" in r.detalle.lower()
