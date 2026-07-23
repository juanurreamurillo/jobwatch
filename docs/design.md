# jobwatch — Design

**Status:** Approved design, pending implementation plan.

## 1. Purpose

A console tool that aggregates job postings from several boards, deduplicates
them, scores each against the user's CV, and reports **only what is new** since
the last run. Runs on a schedule (cron / Task Scheduler). Personal, low-volume
use. Not a multi-tenant product.

**Goal:** aggregation with CV matching + continuous monitoring with deduplication.

**Non-goals (MVP):**
- Does not write to boards (no applying, no favoriting). Read-only over what a
  public search already shows.
- No authentication/session (see §4 and §5d, decision D1).
- No bulk cover-letter generation (see §5d, D6).

## 2. Board scope

| Board | Type | Mechanism | Session |
|---|---|---|---|
| Computrabajo | SSR behind Cloudflare | `curl_cffi` (browser-grade TLS) + `extruct` over JSON-LD `JobPosting` | No (public) |
| elempleo | SPA, internal JSON API | `curl_cffi` against internal endpoint (mapped in Phase 0) | No (public) |
| Magneto | SPA, internal JSON API | `curl_cffi` against internal endpoint (mapped in Phase 0) | No (public) |
| Indeed | Third-party library | Wraps `JobSpy`; treated as its own category (see §5d, D4) | No (public) |

LinkedIn is **out of scope** for the MVP: mandatory session and aggressive
automation detection make the account-ban risk disproportionate to the value.

## 3. Architecture

Four-stage pipeline. Normalization lives **inside** each connector (there is no
separate "normalizer" stage — see §5d, D7).

```
[Connectors]           [Hybrid matcher]         [Store + Report]
 4 sources       ──►    local filter → LLM  ──►   SQLite + .md
 each emits            (scores only, does         two-level dedup
 list[Vacante]         not draft letters)         new-only report
 pre-normalized
```

**One run (`jobwatch run`):**
1. For each connector: `buscar(criterios) -> ResultadoConector`.
2. Consolidate all `Vacante` records.
3. Dedup against the store (two levels, §6).
4. Match **only the new ones**: cheap local filter → LLM scores survivors.
5. Persist to SQLite.
6. Write `reportes/YYYY-MM-DD.md` with new scored postings + per-connector status.

### 3.1 Connector contract

```python
def buscar(criterios: Criterios) -> ResultadoConector: ...
```

- `Criterios`: search terms, location, work mode, etc. (mapped to each board's
  vocabulary inside the connector).
- `ResultadoConector`: `{ estado: OK | ERROR | SESION_EXPIRADA,
  vacantes: list[Vacante], detalle: str }`. The `estado` field is what makes
  fail-loud possible (§5d, D2): telling "0 results from an empty search" apart
  from "connector broken/blocked".

### 3.2 `Vacante` model (Pydantic)

```
id_estable            # hash(board + native id) — see §6 and §5d, D3
id_nativo             # the board's internal id for the posting
portal                # computrabajo | elempleo | magneto | indeed
titulo
empresa
ubicacion
modalidad             # remote | hybrid | on-site | unknown
salario_raw           # original text
salario_min           # normalized, optional
salario_max           # normalized, optional
url
fecha_publicacion
descripcion_raw
fingerprint_contenido # normalize(company)+normalize(title)+location — see §6
```

## 4. Modules

- `conectores/computrabajo.py`, `elempleo.py`, `magneto.py` — `curl_cffi` +
  own parsing, emit normalized `Vacante`.
- `conectores/indeed.py` — wraps `JobSpy`; its own category with dedicated
  failure detection (§5d, D4).
- `matcher.py` — local filter + LLM scoring.
- `cartas.py` — cover-letter generation, **on demand** (not in `run`).
- `store.py` — SQLite, two-level dedup, persistence.
- `reporte.py` — Markdown render.
- `sesion.py` — **designed but NOT built in the MVP** (§5d, D1). Owns a
  persistent browser profile + cookie export. Activated only if a board starts
  requiring a session.
- `cli.py` — `run`, `carta <id>`, (future) `login <board>`.

Any future credential/profile lives under `secrets/` (git-ignored), never in
the repo.

## 5. Phase 0 — endpoint discovery (before building connectors)

Before writing each connector, map its real endpoint and response shape.
Deliverable: `docs/endpoints.md` with endpoint, parameters, and response shape
per board. Useful on its own even if nothing else is built.

**Toolkit:** browser DevTools (Copy as cURL / HAR export), `mitmproxy2swagger`
(HAR → OpenAPI), `jsluice` (AST extraction of endpoints from SPA JS bundles),
`curlconverter` / `har2requests` (capture → Python client), `extruct`
(validate Computrabajo's `JobPosting` JSON-LD).

**Per-board route rule (§5d, D5):** if a board requires a JS challenge
(Turnstile) that `curl_cffi` cannot pass, that connector is declared a
**first-class browser connector** (nodriver/Camoufox), with its own explicit
route — never a hidden mode of the HTTP connector.

### 5d. Architectural altitude

For each non-trivial decision: (a) the low-effort option, (b) the correct
option, (c) the one chosen + why, (d) debt / what breaks at 10× or in
production. Validated by a fresh-agent adversarial review.

**D1 — Session/authentication.**
(a) Tempting-easy: persistent browser + cookie export from day one.
(b) Correct for the MVP: no session; hit public listings with `curl_cffi`.
(c) **Chosen: no session.** Search listings are public on all four boards;
nothing session-gated (recommendations, applications, contact details) appears
in the pipeline output. Building the most fragile subsystem (browser + login +
cookie export + fingerprint matching) for features that are never delivered is
gold-plating.
(d) Deliberate debt: `sesion.py` stays **designed** (§4) but unbuilt. Trigger:
a board returns 401/403 on the listing endpoint we use → add session **to that
board only**. At 10×: no change; session risk was decoupled from value.

**D2 — Behavior on zero results.**
(a) Easy: fail-silent, "0 is 0".
(b) Correct: fail-loud, tell empty search apart from broken connector.
(c) **Chosen: fail-loud** via `ResultadoConector.estado`. The report marks
`ERROR` per connector.
(d) Without fail-loud, an anti-bot tightening would return 0 and the user would
believe "nothing new" for weeks. Silent-truncation trap avoided.

**D3 — Posting identity (primary dedup).**
(a) Easy: hash of the URL.
(b) Correct: hash of board + native id.
(c) **Chosen: board + native id.** A URL with a different `?utm=` would make
the same posting look new every run.
(d) Requires Phase 0 to identify each board's native id. If a board does not
expose a stable one (a real risk for Computrabajo via JSON-LD and Indeed via
JobSpy), the fallback is documented in `docs/endpoints.md` — not accidental.

**D4 — Indeed via JobSpy.**
(a) Easy: let JobSpy's DataFrame flow semi-raw (a "fake connector").
(b) Correct: full adapter to the `Vacante` model, treated as its own category.
(c) **Chosen: full adapter, own category.** JobSpy is not under our control: it
swallows errors and returns an empty DataFrame → it must be wrapped with
dedicated failure detection (exception/empty → explicit `ERROR`) so fail-loud
is not broken precisely in the connector we don't control. Verify a stable
`job_id` exists before trusting dedup; otherwise, a documented fallback (D3).
(d) At 10×: JobSpy's own rate-limiting; isolated in its module without
contaminating the other three.

**D5 — HTTP vs browser route per board.**
(a) Easy: "transparent fallback" to a headless browser inside the same connector.
(b) Correct: ONE explicit route per board; a first-class browser connector if needed.
(c) **Chosen: explicit route.** A "transparent fallback" contradicted
"the browser does not scrape" and silently doubled the per-board implementation
(two paths to maintain), with JS challenges nobody solves in a 3am cron run.
(d) If a board requires a browser, it is a browser connector with its own line
in the report and its own challenge handling. A visible decision, not a hidden mode.

**D6 — Cover-letter generation.**
(a) Easy-greedy: generate a letter for every listing that passes the filter, inside `run`.
(b) Correct: score in `run` (cheap, with a spend cap); draft letters lazily, on demand.
(c) **Chosen: lazy.** Generating letters for the ~90% of postings never applied
to spends tokens at the wrong boundary.
(d) `run` only scores, with a **per-run LLM call cap** that aborts fail-loud if
the local filter lets through more than expected. Per-posting state
`PUNTUADA | SIN_PUNTAJE | ERROR` (the LLM step is fail-loud too, not just
connectors). `jobwatch carta <id>` drafts on demand, choosing among the user's
existing base letters.

**D7 — Normalization boundary.**
(a) Easy-confused: a separate "normalizer" stage + connectors emitting raw (a lying contract).
(b) Correct: normalization inside the connector; the connector emits clean `Vacante`.
(c) **Chosen: inside the connector.** The `buscar()->list[Vacante]` contract
forces the messy normalization (salary "$2.000.000 a $3.000.000 COP",
"Bogotá D.C." vs "Bogota", work mode) to have a clear owner: each connector.
(d) Minor duplication of normalization logic across connectors → extract to a
shared `normalizar.py` helper if it grows, without changing the boundary.

## 6. Two-level deduplication

1. **Primary — exact:** `id_estable = hash(board + native id)`. Catches exact
   re-posts within one board.
2. **Secondary — content:** `fingerprint_contenido = normalize(company) +
   normalize(title) + location`. Catches the same posting across boards or
   re-posted with a new id. Collapsed into one row marked "seen on N boards".

A posting is **new** if neither its `id_estable` nor its `fingerprint_contenido`
exists in the store.

## 7. Hybrid matcher

1. **Local filter** (free, deterministic): exclusion keywords, minimum salary,
   work mode, junk signals. Discards ~80%.
2. **LLM scoring** (survivors only): input = `Vacante` + the user's CV;
   output = `{ score 0-100, reason }`. With a per-run call cap and per-posting
   state (D6). Each posting is scored once (only the new ones).

The CV is a user-provided file, configured locally and git-ignored — never
committed.

## 8. Store and monitoring

- **SQLite** (`jobwatch.db`): `vacantes` table (key `id_estable`, index on
  `fingerprint_contenido`), `corridas` table (timestamp, per-connector status).
- **Scheduler:** system cron / Task Scheduler running `jobwatch run`.
- **Report** (`reportes/YYYY-MM-DD.md`): new scored postings, ranked, with
  links; header with per-connector status (OK/ERROR); a note on which were seen
  on multiple boards.

## 9. Dependencies

`curl_cffi`, `extruct`, `python-jobspy`, `pydantic`, an LLM SDK
(matcher/letters). Phase 0 (dev): `mitmproxy2swagger`, `jsluice`,
`curlconverter`/`har2requests`. Future (session): `nodriver` or `camoufox`.

## 10. Responsible use / ToS

Automated access may be restricted by a board's Terms of Service. At personal,
low volume (reading public listings that are already shown, with delays between
requests) the practical risk is a temporary IP block, not legal exposure.
Mitigation: reasonable delays between requests, no aggressive parallelism,
respecting the low personal volume, and honoring each site's terms and
`robots.txt`. `curl_cffi` provides browser-grade TLS compatibility for sites
that reject non-browser clients — it is not used to defeat authentication or
access controls.
