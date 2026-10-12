#!/usr/bin/env bash
# Usage: DATABASE_URL_PG=... ./scripts/restore.sh backups/file.dump   Restores into an EMPTY database. (UNVERIFIED)
set -euo pipefail
pg_restore --no-owner --exit-on-error -d "$DATABASE_URL_PG" "$1" && echo restored
