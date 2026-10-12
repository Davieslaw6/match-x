# Security audit and debug pass (spec item 21)
Method: read every route for auth/CSRF, wrote regression tests, ran bandit, ruff (F rules) and pip-audit. Results in docs/TEST_REPORT.md.
Found and fixed:
1. Unbounded Decimal odds (e.g. 1e999999) could crash ticket math with a 500. Odds are now bounded (1 < odds <= 10000, 9 digits). Tested.
2. Validation errors and unknown routes returned FastAPI's default body instead of the standard error envelope. Fixed and tested.
3. Tool calls with an unknown team id raised an error. Now handled. Tested.
4. SQLite did not enforce foreign keys, so cascades silently failed. PRAGMA foreign_keys=ON added.
5. Backtest crashed on a degenerate score grid. Now skipped and counted (earlier phase).
6. CSV rows with invalid odds kept their fixture. Rows are now atomic (earlier phase).
7. Odds lookup matched past fixtures. Now scheduled only (earlier phase).
8. No rate limiting existed. Added per-route-group limits. Tested.
Open risks: no CAPTCHA/lockout across IPs; in-memory rate limiter resets on restart and is per process; prediction immutability is not enforced against raw SQL (needs a Postgres trigger);
CORS and Secure-cookie production behaviour untested; no dependency pinning; frontend untested against the API; Postgres untested.
