# Test report (real results from this build, SQLite only)
| Command | Result |
|---|---|
| `pytest -q` (backend) | 102 passed in 16.45s |
| `pytest --cov=app.engine --cov=app.tickets --cov=app.odds --cov=app.predictions` | TOTAL 336 6 98% (engine, tickets, odds and predictions packages; target 90% met) |
| `ruff check app --select E9,F --ignore F403,F405` | 10 unused-import findings, auto-fixed; re-run clean (star-import warnings F403/F405 ignored) |
| `bandit -r app -ll` | no medium or high findings |
| `pip-audit -r requirements.txt` | No known vulnerabilities found |
Frontend: vitest 3 tests passed in an earlier phase (not re-run this phase). Not run: Playwright, mypy, alembic, npm audit, gitleaks, Postgres, docker compose, CI.
Backtest report is on synthetic data only.
