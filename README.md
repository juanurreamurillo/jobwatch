# jobwatch

**A console-first job aggregator.** Run one search across several job boards, deduplicate the results, score them against your own CV, and get a report of only what's *new* since the last run — without opening five tabs.

> Status: **design phase.** The architecture is specified in [`docs/design.md`](docs/design.md); connectors are built after a discovery phase (see below). Contributions welcome.

---

## Why

Job boards each have their own UI, their own search, and their own noise. `jobwatch` treats them as data sources behind a single contract, so you review one consolidated, ranked list on your terms — in the terminal or from a scheduled run.

It reads only what a normal public search already shows you, at a low, personal volume, with delays between requests. See [Responsible use](#responsible-use).

## How it works

```
[Connectors]              [Hybrid matcher]         [Store + Report]
 one per board     ──►     cheap local filter  ──►   SQLite + Markdown
 each emits                then LLM scoring          two-level dedup
 normalized Vacante        of survivors              new-only report
```

Every connector implements the same contract — `buscar(criterios) -> ResultadoConector` — so adding a board is a new file, not a rewrite. Full design and the trade-offs behind each decision are in [`docs/design.md`](docs/design.md).

### Design highlights

- **Single connector contract.** Boards are interchangeable behind one Pydantic `Vacante` model. Normalization (salary strings, city names, work mode) lives inside each connector.
- **Fail-loud.** A connector that returns zero results distinguishes *"empty search"* from *"broken / blocked"*, so a silently failing source never masquerades as "nothing new".
- **Two-level dedup.** Exact match on the board's native id, plus a content fingerprint that collapses the same posting seen across multiple boards or re-posted with a new id.
- **Hybrid matching.** A free, deterministic local filter discards ~80% of noise; only the survivors are scored by an LLM against your CV. Cover letters are drafted lazily, on demand — not for every listing.

## Roadmap

- [ ] **Phase 0 — endpoint discovery.** Map each board's real endpoints and response shape into `docs/endpoints.md` (a deliverable on its own). Toolkit: browser DevTools (HAR export), [`mitmproxy2swagger`](https://github.com/alufers/mitmproxy2swagger), [`jsluice`](https://github.com/BishopFox/jsluice), [`curlconverter`](https://github.com/curlconverter/curlconverter).
- [ ] Connectors: Computrabajo, elempleo, Magneto, Indeed (via [JobSpy](https://github.com/speedyapply/JobSpy)).
- [ ] Hybrid matcher + SQLite store + Markdown report.
- [ ] Scheduling recipe (cron / Task Scheduler).
- [ ] Optional session support for boards that require it (designed, built only when needed).

## Tech

Python · [`curl_cffi`](https://github.com/lexiforest/curl_cffi) · [`extruct`](https://github.com/scrapinghub/extruct) · [`pydantic`](https://github.com/pydantic/pydantic) · [`python-jobspy`](https://github.com/speedyapply/JobSpy)

## Responsible use

`jobwatch` is built for **personal, low-volume** use over **public** job listings:

- It reads only what a public search already returns — no logging in required for the core flow.
- It uses conservative delays between requests and avoids aggressive parallelism.
- Automated access may be restricted by a site's Terms of Service. You are responsible for how you use this tool. Respect each site's terms, `robots.txt`, and rate limits.

`curl_cffi` is used for browser-grade TLS/HTTP compatibility with sites that reject non-browser clients — not to defeat access controls or authentication.

## Contributing

Contributions are welcome — see [`CONTRIBUTING.md`](CONTRIBUTING.md). A great first contribution is a new connector for a board in your region.

## License

[MIT](LICENSE) © 2026 Juan Urrea & Claude (Anthropic)
