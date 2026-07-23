# Contributing to jobwatch

Thanks for your interest — contributions are genuinely welcome.

## Ground rules

- **Never commit personal data or secrets.** No CVs, cover letters, cookies, session tokens, `.env` files, HAR captures, or generated reports. The `.gitignore` blocks the usual suspects; please keep it that way.
- **Public, low-volume, respectful.** This project targets public job listings at personal volume. Please don't add features whose primary purpose is to defeat access controls, solve CAPTCHAs at scale, or evade bans. Respect each site's Terms of Service, `robots.txt`, and rate limits.

## Adding a connector

The most useful contribution is a connector for a board in your region. Every connector implements the same contract:

```python
def buscar(criterios: Criterios) -> ResultadoConector: ...
```

- Emit the shared `Vacante` model — do the messy normalization (salary, location, work mode) **inside** your connector.
- Be **fail-loud**: return an explicit `ERROR` state on failure instead of an empty list, so a broken source is never mistaken for an empty search.
- Provide a stable native id for deduplication; if the board doesn't expose one, document your fallback.

See [`docs/design.md`](docs/design.md) for the full architecture and the reasoning behind each decision.

## Workflow

1. Fork and branch from `main`.
2. Keep changes focused; match the surrounding style.
3. Open a PR describing what you changed and why. Mention any new dependency.

## Discussion

Not sure about an approach? Open an issue first — happy to talk it through before you write code.
