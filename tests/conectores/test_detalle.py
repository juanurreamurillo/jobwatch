"""Sub-fetch del detalle de la oferta (hallazgo #1).

Los conectores de computrabajo y elempleo paran en la tarjeta del listado, que no
trae descripción. Sin descripción no se puede decidir si una vacante exige inglés
—la pregunta central de este buscador— así que 12 de 22 candidatas de la corrida
del 2026-07-24 llegaron incontestables.
"""
from pathlib import Path

import pytest

from jobwatch.conectores import computrabajo, elempleo, magneto

FX = Path(__file__).parent / "fixtures"


@pytest.mark.parametrize("modulo,fixture,esperado", [
    (computrabajo, "computrabajo-detalle.html", "multinacional en expansión"),
    (elempleo, "elempleo-detalle.html", "construcción de paz"),
])
def test_extraer_detalle_devuelve_la_descripcion(modulo, fixture, esperado):
    html = (FX / fixture).read_text(encoding="utf-8")
    texto = modulo.extraer_detalle(html)
    assert esperado in texto.lower()
    assert len(texto) > 300


def test_computrabajo_detalle_incluye_la_modalidad():
    """El bloque de computrabajo trae 'Remoto' junto al contrato: es lo que
    permite resolver la modalidad de las que llegan como desconocidas."""
    html = (FX / "computrabajo-detalle.html").read_text(encoding="utf-8")
    assert "remoto" in computrabajo.extraer_detalle(html).lower()


@pytest.mark.parametrize("modulo", [computrabajo, elempleo])
def test_extraer_detalle_sin_bloque_devuelve_vacio(modulo):
    """Una página sin el bloque esperado no debe reventar: devuelve cadena vacía
    y el núcleo decide qué hacer."""
    assert modulo.extraer_detalle("<html><body><p>nada</p></body></html>") == ""


@pytest.mark.parametrize("modulo", [computrabajo, elempleo])
def test_detalle_usa_el_fetch_inyectado(modulo):
    """`detalle` compone fetch + parseo, con fetch inyectable para test offline."""
    fixture = f"{modulo.__name__.rsplit('.', 1)[-1]}-detalle.html"
    html = (FX / fixture).read_text(encoding="utf-8")
    llamadas = []

    def fetch(url):
        llamadas.append(url)
        return html

    texto = modulo.detalle("https://portal/oferta/1", fetch=fetch)
    assert llamadas == ["https://portal/oferta/1"]
    assert len(texto) > 300


# --- Magneto: JSON-LD JobPosting (descubrimiento del 2026-07-24) ---

def test_magneto_extraer_detalle_usa_el_jobposting_jsonld():
    """El detalle de magneto es SSR y trae schema.org/JobPosting en un
    <script type="application/ld+json">. Es fuente estructurada y estándar: más
    estable que cualquier selector de DOM."""
    html = (FX / "magneto-detalle.html").read_text(encoding="utf-8")
    texto = magneto.extraer_detalle(html)
    assert "inteligencia artificial" in texto.lower()
    assert len(texto) > 1000


def test_magneto_detalle_ignora_otros_bloques_jsonld():
    """La página trae además BreadcrumbList y LocalBusiness; solo vale JobPosting."""
    html = (FX / "magneto-detalle.html").read_text(encoding="utf-8")
    assert "breadcrumb" not in magneto.extraer_detalle(html).lower()


def test_magneto_extraer_detalle_sin_jobposting_devuelve_vacio():
    assert magneto.extraer_detalle("<html><body><p>nada</p></body></html>") == ""


def test_magneto_detalle_tolera_jsonld_corrupto():
    """Un bloque ld+json que no parsea no debe tumbar el extractor."""
    html = '<html><head><script type="application/ld+json">{roto</script></head></html>'
    assert magneto.extraer_detalle(html) == ""


# --- Magneto vía su servidor MCP oficial (medido: 0,2 s / 4,3 KB vs 846 KB) ---

def test_magneto_slug_de_url():
    """El MCP identifica la oferta por slug; hay que sacarlo de la URL, ignorando
    la query string (el propio MCP devuelve urls con ?utm_source=…)."""
    assert magneto.slug_de_url(
        "https://www.magneto365.com/co/empleos/ingeniero-ia-1003909?utm_source=openai"
    ) == "ingeniero-ia-1003909"


def test_magneto_detalle_prefiere_mcp():
    """Si el MCP responde, no se descarga el HTML de 846 KB."""
    llamadas = {"mcp": 0, "html": 0}
    def post(payload):
        llamadas["mcp"] += 1
        return {"result": {"structuredContent": {"job": {
            "description": "Agentes de IA con LangChain y MCP.", "modality": "Remoto"}}}}
    def fetch(url):
        llamadas["html"] += 1
        return ""
    texto = magneto.detalle("https://www.magneto365.com/co/empleos/x-1", fetch=fetch, post=post)
    assert "LangChain" in texto
    assert llamadas == {"mcp": 1, "html": 0}


def test_magneto_detalle_cae_al_html_si_el_mcp_falla():
    """El MCP es de un tercero: si cae, el extractor JSON-LD sigue respondiendo."""
    html = (FX / "magneto-detalle.html").read_text(encoding="utf-8")
    def post(payload): raise RuntimeError("503")
    texto = magneto.detalle("https://www.magneto365.com/co/empleos/x-1",
                            fetch=lambda u: html, post=post)
    assert "inteligencia artificial" in texto.lower()


def test_magneto_detalle_cae_al_html_si_el_mcp_responde_vacio():
    """Una respuesta 200 sin descripción también debe caer al respaldo."""
    html = (FX / "magneto-detalle.html").read_text(encoding="utf-8")
    def post(payload): return {"result": {"structuredContent": {"job": {"description": ""}}}}
    assert "inteligencia artificial" in magneto.detalle(
        "https://www.magneto365.com/co/empleos/x-1", fetch=lambda u: html, post=post).lower()


def test_magneto_payload_mcp_es_un_solo_tools_call():
    """Medido: `tools/call` responde sin `initialize` previo ni Mcp-Session-Id,
    así que el cliente es un único POST JSON-RPC (sin dependencia nueva)."""
    capturado = {}
    def post(payload):
        capturado.update(payload)
        return {"result": {"structuredContent": {"job": {"description": "x"*400}}}}
    magneto.detalle("https://www.magneto365.com/co/empleos/mi-slug-9", fetch=None, post=post)
    assert capturado["method"] == "tools/call"
    assert capturado["params"]["name"] == "get_job_detail"
    assert capturado["params"]["arguments"] == {"jobSlug": "mi-slug-9"}
