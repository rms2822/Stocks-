#!/usr/bin/env bash
# run_pipeline.sh -- full DSE data refresh in one command.
#
# Produces the analysis CSV (full_analysis.csv/.json + cleaned variants), the
# intraday data CSV (dse_latest_prices_<date>.csv) and the dashboard, then
# commits them. Designed to run unattended in a fresh cloud session (the daily
# scheduled task invokes this).
#
# Steps: deps -> DB -> API server -> load prices -> fundamentals (amarstock) ->
# enrich fundamentals (DSE company pages) -> 1y history -> eps_trend -> scan ->
# live prices -> clean -> dashboard -> commit+push.
#
# Usage: bash backend/run_pipeline.sh [--no-commit]
set -uo pipefail
cd "$(dirname "$0")"

PY=python3.13
command -v "$PY" >/dev/null 2>&1 || PY=python3
COMMIT=1
[ "${1:-}" = "--no-commit" ] && COMMIT=0
log(){ echo "[pipeline $(date -u +%H:%M:%S)] $*"; }

log "installing dependencies"
pip install -q -r requirements.txt 2>&1 | tail -1 || true

log "initialising database"
rm -f dse.db
"$PY" init_db.py

log "starting API server"
"$PY" -m uvicorn app.main:app --host 127.0.0.1 --port 8000 > /tmp/pipe_uvicorn.log 2>&1 &
SERVER=$!
trap 'kill $SERVER 2>/dev/null || true' EXIT
for i in $(seq 1 40); do curl -sf http://127.0.0.1:8000/ >/dev/null 2>&1 && break; sleep 1.5; done
curl -sf http://127.0.0.1:8000/ >/dev/null 2>&1 || { log "API did not start"; cat /tmp/pipe_uvicorn.log | tail -20; exit 1; }

log "loading latest prices (DSE day-end API)"
curl -sS -m 300  -X POST "http://127.0.0.1:8000/load-dse"            | tail -c 200; echo
log "loading fundamentals (amarstock EPS/PE)"
curl -sS -m 600  -X POST "http://127.0.0.1:8000/load-fundamentals"  | tail -c 200; echo
log "enriching fundamentals from DSE company pages (NAV/debt/EPS-hist/dividend)"
"$PY" load_company_fundamentals.py 8
log "loading 365d price history (this is the slow step, ~20 min)"
curl -sS -m 2000 -X POST "http://127.0.0.1:8000/load-history?days=365" | tail -c 200; echo
log "recomputing EPS trend"
"$PY" recompute_trend.py

log "running full scan"
"$PY" full_scan.py | tail -6

log "fetching intraday live prices + rebuilding dashboard"
"$PY" fetch_live_prices.py || true
"$PY" clean_analysis.py | tail -2
"$PY" build_dashboard.py

kill $SERVER 2>/dev/null || true; trap - EXIT

if [ "$COMMIT" = "1" ]; then
  log "committing refreshed data"
  git add full_analysis.csv full_analysis.json full_analysis_clean.csv \
          full_analysis_clean.json analysis_dashboard.html dse_latest_prices_*.csv 2>/dev/null || true
  if git diff --cached --quiet; then
    log "no changes to commit"
  else
    git -c user.name="github-actions[bot]" \
        -c user.email="41898282+github-actions[bot]@users.noreply.github.com" \
        commit -q -m "chore: daily DSE data refresh ($(date -u +%F))"
    for attempt in 1 2 3 4; do git push origin HEAD && break; sleep $((attempt*5)); done
    log "pushed"
  fi
fi
log "done"
