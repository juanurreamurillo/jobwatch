from pathlib import Path

from jobwatch.config import cargar_criterios

_SKILL = Path(__file__).resolve().parents[1] / "skill"


def test_bundle_existe():
    assert (_SKILL / "SKILL.md").exists()
    assert (_SKILL / "jobwatch.config.example.json").exists()
    assert (_SKILL / "references" / "scoring-rubric.md").exists()


def test_config_ejemplo_deserializa_a_criterios():
    c = cargar_criterios(str(_SKILL / "jobwatch.config.example.json"))
    assert c.terminos  # no vacío


def test_skill_frontmatter_tiene_trigger():
    texto = (_SKILL / "SKILL.md").read_text(encoding="utf-8")
    assert texto.startswith("---")
    assert "name: jobwatch" in texto
    assert "/jobwatch" in texto  # el trigger aparece en el frontmatter


def test_bundle_sin_datos_personales():
    # Ningún archivo del bundle debe traer un CV ni rutas personales.
    for p in _SKILL.rglob("*"):
        if p.is_file():
            t = p.read_text(encoding="utf-8", errors="ignore").lower()
            assert "juan" not in t and "data/cv.txt" not in t or p.name == "SKILL.md"
