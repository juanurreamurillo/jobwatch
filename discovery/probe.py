"""Probe a Colombian job board's search page to characterize it for Phase 0.

Run locally (the portals need browser-grade TLS, which `curl_cffi` provides):

    python -m discovery.probe elempleo "gerente de proyectos"

It fetches the search page, reports HTTP status, whether Cloudflare blocked it,
whether the HTML embeds schema.org JSON-LD, and a rough count of listing hints,
then saves the raw HTML to `discovery/captures/{portal}.html` for you to
inspect and lift selectors from. Network deps (`curl_cffi`, `extruct`) are
imported lazily so the pure helpers below stay unit-testable offline.
"""

from __future__ import annotations

import sys
from pathlib import Path
from urllib.parse import quote_plus

CAPTURAS = Path(__file__).parent / "captures"

# Perfil de Chrome reciente para curl_cffi (ver docs: usar uno actual, no chrome99).
IMPERSONATE = "chrome124"


def slugify(termino: str) -> str:
    """"Gerente de Proyectos" -> "gerente-de-proyectos" (para URLs con ruta)."""
    return "-".join(termino.lower().split())


def construir_url(portal: str, termino: str) -> str:
    """URL de resultados de búsqueda por portal. Los patrones provienen del
    reconocimiento en docs/endpoints.md; el de Magneto es provisional."""
    slug = slugify(termino)
    if portal == "computrabajo":
        return f"https://co.computrabajo.com/trabajo-de-{slug}"
    if portal == "elempleo":
        return f"https://www.elempleo.com/co/ofertas-empleo/trabajo-{slug}"
    if portal == "magneto":
        # Parámetro de búsqueda por confirmar en la captura local.
        return f"https://www.magneto365.com/co/trabajos/buscar?search={quote_plus(termino)}"
    raise ValueError(f"Portal desconocido: {portal!r} (usa computrabajo|elempleo|magneto)")


def es_cloudflare(status: int, html: str) -> bool:
    """Heurística: ¿la respuesta es un challenge/bloqueo de Cloudflare?"""
    if status in (403, 429, 503):
        return True
    marcadores = (
        "just a moment",
        "checking your browser",
        "cf-browser-verification",
        "challenge-platform",
        "attention required",
    )
    bajo = html.lower()
    return any(m in bajo for m in marcadores)


def contar_indicios_ofertas(html: str) -> int:
    """Conteo aproximado de tarjetas de oferta por señales comunes en el HTML.
    No es exacto — solo indica si el listado se renderiza server-side."""
    bajo = html.lower()
    return max(
        bajo.count("jobposting"),
        bajo.count('article'),
        bajo.count("/ofertas-trabajo/"),
        bajo.count("data-id"),
    )


def extraer_jsonld(html: str) -> list[dict]:
    """Bloques JSON-LD de la página (import perezoso de extruct)."""
    import extruct

    datos = extruct.extract(html, syntaxes=["json-ld"])
    return datos.get("json-ld", [])


def _tiene_jobposting(bloques: list[dict]) -> bool:
    for b in bloques:
        tipo = b.get("@type", "")
        tipos = tipo if isinstance(tipo, list) else [tipo]
        if any(str(t).endswith("JobPosting") for t in tipos):
            return True
    return False


def sondear(portal: str, termino: str) -> dict:
    """Descarga la página y devuelve un reporte de caracterización."""
    from curl_cffi import requests

    url = construir_url(portal, termino)
    r = requests.get(url, impersonate=IMPERSONATE, timeout=30)
    html = r.text or ""

    CAPTURAS.mkdir(exist_ok=True)
    destino = CAPTURAS / f"{portal}.html"
    destino.write_text(html, encoding="utf-8")

    bloques = extraer_jsonld(html) if html else []
    return {
        "portal": portal,
        "url": url,
        "status": r.status_code,
        "bloqueado_cloudflare": es_cloudflare(r.status_code, html),
        "bytes": len(html),
        "json_ld_bloques": len(bloques),
        "tiene_jobposting": _tiene_jobposting(bloques),
        "indicios_ofertas": contar_indicios_ofertas(html),
        "html_guardado_en": str(destino),
    }


def _imprimir(rep: dict) -> None:
    print(f"\n=== {rep['portal']} ===")
    print(f"URL:                {rep['url']}")
    print(f"HTTP status:        {rep['status']}")
    print(f"Cloudflare bloqueó: {'SÍ' if rep['bloqueado_cloudflare'] else 'no'}")
    print(f"Bytes de HTML:      {rep['bytes']}")
    print(f"Bloques JSON-LD:    {rep['json_ld_bloques']} "
          f"(JobPosting: {'sí' if rep['tiene_jobposting'] else 'no'})")
    print(f"Indicios de oferta: {rep['indicios_ofertas']}")
    print(f"HTML guardado:      {rep['html_guardado_en']}")


def main(argv: list[str] | None = None) -> int:
    args = sys.argv[1:] if argv is None else argv
    if len(args) < 2:
        print("uso: python -m discovery.probe <computrabajo|elempleo|magneto> <termino>",
              file=sys.stderr)
        return 2
    portal, termino = args[0], " ".join(args[1:])
    try:
        rep = sondear(portal, termino)
    except ValueError as e:
        print(f"error: {e}", file=sys.stderr)
        return 2
    _imprimir(rep)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
