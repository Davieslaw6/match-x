# MATCH X spec (living)
Source: master build prompt (sections 0-21). Module -> phase map:
| Module | Phase |
|---|---|
| Repo, settings, logging, health, compose, CI | 1 |
| Models, Alembic, owner auth, sessions, CSRF, rate limits | 2 |
| Provider interface, football-data.org, CSV importer, team resolution, sync | 3 |
| M0/M1 models, backtest, MODEL_REPORT.md | 4 |
| LLM provider, tools, grounding verifier, SSE chat | 5 |
| Analysis page, odds, de-vig, staleness | 6 |
| Tickets, previews, revisions, split, optimiser, export | 7 |
| Screenshot import | 8 |
| Booking codes | 9 |
| History, settings, retention, export/delete | 10 |
| Hardening, e2e, audits | 11 |
| Docs | 12 |
Hard rules: no billing/multi-user, no auto-betting, Decimal/NUMERIC money, UTC storage, never "safe/sure/guaranteed", no fabricated data, nothing marked passing unless executed.
## Design (Phase 1)
Concept: a tactics board. Chalk lines on slate. One memorable element: the ProbabilityBar drawn as a pitch strip (home | draw | away, halfway line at 50%). Everything else stays quiet.
Colors: slate-950 #12161C, slate-900 #1A2029, chalk #E7E4DA, line #3A4452, home-blue #6C9BFF, away-amber #F2B45A, draw-grey #8A94A3. Light theme swaps via tokens.
Type: Schibsted Grotesk (headings), Public Sans (body); system fallbacks until fonts are vendored. Sentence case, no all-caps labels.
