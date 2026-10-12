#!/usr/bin/env bash
# Usage: DATABASE_URL_PG=postgresql://user:pass@host/db ./scripts/backup.sh [outdir]   (UNVERIFIED: not executed in this build)
set -euo pipefail
out="${1:-backups}"; mkdir -p "$out"; f="$out/matchx-$(date -u +%Y%m%dT%H%M%SZ).dump"
pg_dump --format=custom --no-owner "$DATABASE_URL_PG" > "$f" && echo "wrote $f"
