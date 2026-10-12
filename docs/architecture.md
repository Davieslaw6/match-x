# Architecture
Browser -> Next.js (rewrites /api/* to backend) -> FastAPI -> SQLAlchemy -> SQLite (dev) or PostgreSQL 16.
Backend packages: `app/engine` (M0, Dixon-Coles, markets, metrics, backtest; pure functions), `app/odds`, `app/tickets` (pure ticket logic),
`app/providers` (adapter interface, football-data.org, CSV importer, resilience, team resolution), `app/ai` (tools, LLM abstraction, orchestrator, grounding verifier),
API routers: auth/main, explorer, tickets_api, imports_api, booking_api, chat_api, ops_api. `app/jobs.py` runs jobs from the CLI or the owner-only API.
Rules enforced in code: UTC storage; Decimal money; immutable predictions (CHECK + ORM guard); append-only odds; two-step ticket edits with revisions.
Not built: APScheduler worker process, Alembic migrations, most frontend pages.
