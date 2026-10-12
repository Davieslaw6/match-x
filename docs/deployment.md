# Deployment
Local: `docker compose up -d db`, set DATABASE_URL to the postgresql+psycopg URL (pip install "psycopg[binary]"), `python -m app.cli create-owner <name>`, `uvicorn app.main:app`.
Private self-hosted: run behind HTTPS, set ENV=production (Secure cookies), bind the backend to 127.0.0.1 and let the frontend proxy /api/*, set CORS_ORIGIN only if a second origin is unavoidable.
Vercel frontend + separate backend: set BACKEND_URL in the Vercel project so next.config rewrites /api/* to it; the browser then talks to one origin. Host the database privately.
Tables are created with create_all; Alembic migrations are NOT written yet, so schema changes need a manual migration or a fresh database. All of this is UNVERIFIED on Postgres and Vercel.
Backup/restore: scripts/backup.sh and scripts/restore.sh (pg_dump/pg_restore, UNVERIFIED). Restore test: restore into an empty database and run `pytest` smoke checks against it.
