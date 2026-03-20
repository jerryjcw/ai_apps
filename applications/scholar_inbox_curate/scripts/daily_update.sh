#!/usr/bin/env bash
# daily_update.sh — run a single daily pass: ingest, poll citations, prune/promote.
# Place a cron entry like:
#   0 9 * * * /path/to/applications/scholar_inbox_curate/scripts/daily_update.sh >> /tmp/scholar_curate.log 2>&1

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
APP_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"  # applications/scholar_inbox_curate/

cd "$APP_ROOT"

CURATE="$APP_ROOT/.venv/bin/scholar-curate"
CONFIG="$APP_ROOT/config.toml"

log() { echo "[$(date '+%Y-%m-%d %H:%M:%S')] $*"; }

log "=== Daily update starting ==="

log "Step 1/4: Backfilling missed dates (last 30 days)..."
"$CURATE" --config "$CONFIG" backfill --lookback 30

log "Step 2/4: Ingesting today's recommendations..."
"$CURATE" --config "$CONFIG" ingest

log "Step 3/4: Polling citation counts..."
"$CURATE" --config "$CONFIG" poll-citations

log "Step 4/4: Applying prune/promote rules..."
"$CURATE" --config "$CONFIG" prune

log "--- Stats ---"
"$CURATE" --config "$CONFIG" stats

log "=== Daily update complete ==="
