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
    assert "bloqueado" in r.detalle.lower()


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


def test_ejecutar_reporta_filas_omitidas_en_detalle():
    def url_fn(c, p):
        return f"p{p}" if p <= 2 else ""
    def extraer(html, c):
        if html == "":
            return ([], 0, 0)
        return ([_v(html)], 2, 5)   # 2 omitidas por página, 5 crudas
    r = ejecutar(Criterios(terminos="x"), url_fn, lambda u: u, extraer)
    assert r.estado is EstadoConector.OK
    assert "omitidas" in r.detalle.lower()


def test_ejecutar_extraer_lanza_en_pagina1_es_error():
    def extraer(html, c): raise ValueError("html corrupto")
    r = ejecutar(Criterios(terminos="x"), lambda c, p: f"p{p}", lambda u: u, extraer)
    assert r.estado is EstadoConector.ERROR


def test_ejecutar_fin_de_paginacion_no_es_cobertura_parcial():
    """Un portal que responde 404 al pedir una página inexistente está diciendo
    'no hay más', no 'me rompí'. Con un predicado es_fin por portal, eso es fin
    limpio y NO debe declarar cobertura parcial (hallazgo #4)."""
    def url_fn(c, p): return f"p{p}"
    def fetch(u):
        if u == "p3":
            raise RuntimeError("HTTP Error 404: ")
        return u
    def extraer(html, c): return ([_v(html)], 0, 20)
    r = ejecutar(
        Criterios(terminos="x"), url_fn, fetch, extraer,
        es_fin=lambda e: "404" in str(e),
    )
    assert r.estado is EstadoConector.OK
    assert [v.titulo for v in r.vacantes] == ["tp1", "tp2"]
    assert "parcial" not in r.detalle.lower()


def test_ejecutar_error_no_reconocido_sigue_siendo_parcial():
    """El predicado no debe tragarse errores reales: un 500 sigue siendo parcial."""
    def url_fn(c, p): return f"p{p}"
    def fetch(u):
        if u == "p2":
            raise RuntimeError("HTTP Error 500: ")
        return u
    def extraer(html, c): return ([_v(html)], 0, 20)
    r = ejecutar(
        Criterios(terminos="x"), url_fn, fetch, extraer,
        es_fin=lambda e: "404" in str(e),
    )
    assert "parcial" in r.detalle.lower()


def test_ejecutar_fin_de_paginacion_en_pagina1_sigue_siendo_error():
    """Un 404 en la página 1 no es 'fin', es que la búsqueda no existe."""
    def fetch(u): raise RuntimeError("HTTP Error 404: ")
    r = ejecutar(
        Criterios(terminos="x"), lambda c, p: f"p{p}", fetch,
        lambda h, c: ([], 0, 0), es_fin=lambda e: "404" in str(e),
    )
    assert r.estado is EstadoConector.ERROR


# --- Reintento ante latencia errática (medido en magneto 2026-07-24) ---

def test_ejecutar_reintenta_fallo_transitorio_en_pagina1():
    """Magneto tiene latencia de cola errática: la misma URL que da timeout
    responde en 0,8 s al reintentarla. Sin reintento, un fallo transitorio en la
    página 1 tumba el conector entero y se pierden vacantes reales."""
    intentos = {"n": 0}
    def fetch(u):
        if u == "p1":
            intentos["n"] += 1
            if intentos["n"] == 1:
                raise RuntimeError("timeout")
        return u
    def extraer(html, c):
        return ([], 0, 0) if html == "" else ([_v(html)], 0, 20)
    def url_fn(c, p): return f"p{p}" if p <= 2 else ""
    r = ejecutar(Criterios(terminos="x"), url_fn, fetch, extraer, reintentos=1)
    assert r.estado is EstadoConector.OK
    assert [v.titulo for v in r.vacantes] == ["tp1", "tp2"]


def test_ejecutar_reintenta_fallo_transitorio_en_pagina_intermedia():
    """No es 'reintentar la página 1': cualquier página puede fallar."""
    intentos = {"n": 0}
    def fetch(u):
        if u == "p2":
            intentos["n"] += 1
            if intentos["n"] == 1:
                raise RuntimeError("timeout")
        return u
    def extraer(html, c):
        return ([], 0, 0) if html == "" else ([_v(html)], 0, 20)
    r = ejecutar(Criterios(terminos="x"), lambda c, p: f"p{p}" if p <= 2 else "",
                 fetch, extraer, reintentos=1)
    assert [v.titulo for v in r.vacantes] == ["tp1", "tp2"]
    assert "parcial" not in r.detalle.lower()


def test_ejecutar_fallo_persistente_sigue_siendo_error_tras_agotar_reintentos():
    """El reintento no debe convertir una fuente rota en silencio."""
    def boom(u): raise RuntimeError("bloqueado")
    r = ejecutar(Criterios(terminos="x"), lambda c, p: f"p{p}", boom,
                 lambda h, c: ([], 0, 0), reintentos=2)
    assert r.estado is EstadoConector.ERROR
    assert "bloqueado" in r.detalle.lower()


def test_ejecutar_no_reintenta_el_fin_de_paginacion():
    """Un 404 de 'no hay más páginas' es una respuesta correcta: reintentarlo
    solo gasta peticiones contra el portal."""
    llamadas = []
    def fetch(u):
        llamadas.append(u)
        if u == "p3":
            raise RuntimeError("HTTP Error 404: ")
        return u
    r = ejecutar(Criterios(terminos="x"), lambda c, p: f"p{p}", fetch,
                 lambda h, c: ([_v(h)], 0, 20), reintentos=2,
                 es_fin=lambda e: "404" in str(e))
    assert r.estado is EstadoConector.OK
    assert llamadas.count("p3") == 1     # no se reintentó
    assert "parcial" not in r.detalle.lower()


def test_coincide_termino_no_pega_palabras_al_quitar_simbolos():
    """Regresión real (2026-07-24): `_clave` BORRA los símbolos en vez de
    sustituirlos por espacio, así que 'Ingeniero/a' queda 'ingenieroa' y el
    límite de palabra \\bingeniero\\b falla. Con el filtro cableado a producción
    eso descarta la vacante correcta: la búsqueda 'ingeniero inteligencia
    artificial' cortaba 'Ingeniero/a de inteligencia artificial (IA)'."""
    assert coincide_termino(
        "Ingeniero/a de inteligencia artificial (IA) 1626436242-64",
        "ingeniero inteligencia artificial",
    ) is True


def test_coincide_termino_separa_por_guion_y_parentesis():
    assert coincide_termino("Analista-Programador (Senior)", "analista programador") is True
    assert coincide_termino("Coordinador/Líder de Proyectos", "lider proyectos") is True


def test_coincide_termino_sigue_descartando_lo_ajeno():
    """El arreglo no debe aflojar el filtro: lo irrelevante se sigue cortando."""
    assert coincide_termino("Gestor comercial", "gerente de proyectos") is False
    assert coincide_termino("Auxiliar administrativo", "ingeniero inteligencia artificial") is False


def test_coincide_termino_acepta_coincidencia_parcial():
    """Caso real (computrabajo, 2026-07-24): 'Ingeniero IA' es exactamente lo que
    busca 'ingeniero inteligencia artificial', pero exigir TODOS los tokens la
    descartaba. El filtro local es un pre-filtro barato antes de la puntuación
    (README): perder una vacante es irrecuperable, un falso positivo solo cuesta
    una puntuación. Medido: con >=1 token se sigue cortando el 88% del ruido real."""
    assert coincide_termino("Ingeniero IA", "ingeniero inteligencia artificial") is True
    assert coincide_termino("Project Manager IT", "project manager senior") is True


def test_coincide_termino_corta_lo_que_no_comparte_ningun_token():
    """El aflojamiento no debe resucitar el ruido del hallazgo #2: los títulos sin
    NINGÚN token en común se siguen descartando."""
    for titulo in ["gestor comercial", "Auxiliar administrativo", "Arquitecto de datos",
                   "APRENDIZ SENA - IT", "Analista financiero"]:
        assert coincide_termino(titulo, "gerente de proyectos") is False, titulo
