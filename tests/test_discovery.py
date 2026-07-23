import pytest

from discovery.probe import (
    _tiene_jobposting,
    construir_url,
    contar_indicios_ofertas,
    es_cloudflare,
    slugify,
)


def test_slugify():
    assert slugify("Gerente de Proyectos TI") == "gerente-de-proyectos-ti"
    assert slugify("  espacios   raros ") == "espacios-raros"


def test_construir_url_por_portal():
    assert construir_url("elempleo", "gerente de proyectos") == (
        "https://www.elempleo.com/co/ofertas-empleo/trabajo-gerente-de-proyectos"
    )
    assert construir_url("computrabajo", "dev").endswith("/trabajo-de-dev")
    assert "magneto365.com" in construir_url("magneto", "dev")


def test_construir_url_portal_desconocido():
    with pytest.raises(ValueError):
        construir_url("linkedin", "dev")


def test_es_cloudflare_por_status_y_marcadores():
    assert es_cloudflare(403, "") is True
    assert es_cloudflare(200, "<title>Just a moment...</title>") is True
    assert es_cloudflare(200, "<html>ofertas reales</html>") is False


def test_tiene_jobposting_detecta_tipo_lista_y_string():
    assert _tiene_jobposting([{"@type": "JobPosting"}]) is True
    assert _tiene_jobposting([{"@type": ["Thing", "JobPosting"]}]) is True
    assert _tiene_jobposting([{"@type": "Organization"}]) is False
    assert _tiene_jobposting([]) is False


def test_contar_indicios_no_falla_en_html_vacio():
    assert contar_indicios_ofertas("") == 0
    assert contar_indicios_ofertas("<article></article><article></article>") >= 2
