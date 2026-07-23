---
name: jobwatch
description: "Agrega ofertas de empleo de portales colombianos, deduplica, puntúa contra tu CV y reporta solo lo nuevo — desde Claude Code, sin API key. Trigger: /jobwatch"
---

# /jobwatch

Corre el agregador de empleos jobwatch desde tu sesión de Claude Code. El motor
determinista (conectores, dedup, store, reporte) es el paquete Python `jobwatch`;
tú (Claude) haces el único paso que necesita un LLM: **puntuar las candidatas
contra el CV del usuario**. Sin API key.

## Pre-vuelo

1. ¿Está instalado el CLI? Corre `jobwatch --help`. Si falla, instruye al usuario:
   `pipx install jobwatch` (o `pipx install git+https://github.com/juanurreamurillo/jobwatch`).
2. ¿Existe `jobwatch.config.json` en el directorio actual? Si no, copia la
   plantilla `jobwatch.config.example.json` de esta skill y pide al usuario que
   ajuste términos/ubicación/modalidad.
3. ¿Existe `data/cv.txt`? Si no, pide al usuario que guarde su CV en texto plano
   ahí (`data/` debe estar en su `.gitignore`).

## Flujo

1. **Cosecha (determinista, solo-lectura):**
   ```
   jobwatch harvest --config jobwatch.config.json --json > candidatas.json
   ```
   Si el comando devuelve `{"error": "tope excedido..."}`, dile al usuario que
   afine el filtro (términos/exclusiones) — hay demasiadas candidatas para puntuar.

2. **Puntúa en contexto.** Lee `data/cv.txt` y las `candidatas` de `candidatas.json`.
   Aplica `references/scoring-rubric.md` (para consistencia entre corridas). Para
   CADA candidata (una por `id_estable`, sin faltar ni inventar ninguna) produce un
   objeto `{id_estable, estado, puntaje, razon}` con `estado` ∈ `puntuada|sin_puntaje`.
   Escribe `scores.json` con la forma:
   ```json
   { "run_id": "<el run_id de candidatas.json>", "puntajes": [ ... ] }
   ```
   Respeta el `run_id` exacto de `candidatas.json` — `report` lo valida.

3. **Reporta (determinista):**
   ```
   jobwatch report --candidatas candidatas.json --scores scores.json
   ```
   Valida fail-loud (run_id, cobertura, rango 0–100), persiste y escribe
   `reportes/AAAA-MM-DD.md`. Si aborta, revisa que `scores.json` cubra todas las
   candidatas con el `run_id` correcto y vuelve a puntuar.

4. **Muestra** la ruta del reporte al usuario. Ofrece redactar una carta para las
   mejores: `jobwatch carta <id_estable> --cv data/cv.txt`.

## Programación (opcional)

Para correr esto en cron, el usuario puede usar `/schedule` de Claude Code sobre
`/jobwatch` (Claude-en-esa-sesión puntúa). Para automatización 100% headless sin
Claude, existe `jobwatch run --config ... --cv data/cv.txt` con `ANTHROPIC_API_KEY`.
