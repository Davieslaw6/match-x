# Progress (evidence in VERIFICATION_LOG.md and TEST_REPORT.md)
| Phase | Status |
|---|---|
| 0-1 Spec, foundation | done; compose and CI files written but not executed |
| 2 Data/auth | auth, sessions, CSRF, lockout, CLI done; Alembic and full per-spec table set partly done (no model_registry, api_quota_usage tables) |
| 3 Sports data | done+tested with mocks; live provider UNVERIFIED; scheduler not built |
| 4 Engine | M0/M1/backtest done; report on SYNTHETIC data; M2 not built |
| 5 Chat | done+tested on mock LLM; live LLM UNVERIFIED; chat UI not built |
| 6 Odds/analysis | done+tested (API only) |
| 7 Tickets | storage, two-step edits, revisions, split, optimiser, export, idempotency done+tested (API only) |
| 8 Screenshots | validation, re-encode, dedup, review flow done+tested with test double; real vision extractor and Tesseract not built |
| 9 Booking | integration interface, manual fallback, job flow done+tested with fake integration |
| 10 History/settings | evaluation job, history, calibration, settings, export, delete, retention done+tested; timezone setting not yet wired into explorer |
| 11 Hardening | rate limits, envelopes, headers, bandit/ruff/pip-audit run; Playwright, mypy, EXPLAIN checks NOT run |
| 12 Docs | architecture, api-setup, deployment, troubleshooting, backup scripts, TEST_REPORT done |
| 13 Audit | docs/AUDIT.md |
| Frontend | shell only; no pages for chat, explorer, analysis, tickets, history, settings, login |
