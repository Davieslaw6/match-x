# Troubleshooting
- 401 on every call: sign in via POST /api/v1/auth/login with the x-csrf-token header copied from GET /api/v1/auth/session.
- 403 csrf: send the mx_csrf cookie value in the x-csrf-token header on every POST/PUT.
- 503 on /chat: set LLM_PROVIDER. 503 on screenshot import: no vision extractor is configured.
- 429: rate limit per minute (auth 20, chat 30, jobs 10, other 300).
- Old matchx.db errors about missing columns: delete it; migrations are not written yet.
- Predictions return insufficient data: a team needs at least 8 finished matches in the competition.
