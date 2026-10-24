#!/usr/bin/env bash
# Local stack: sync env, news, strategies, bhav + prereg while Angel keys optional.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
PY="${ROOT}/.venv/bin/python"
mkdir -p var/reports var/news

echo "== sync env from crypto =="
"$PY" -m scripts.sync_local_env "$@"

# Angel: config/angel.env (preferred) merged by sync_local_env; legacy var/local/angel.env still works
if [[ -f "${ROOT}/var/local/angel.env" ]] && [[ ! -f "${ROOT}/config/angel.env" ]]; then
  "$PY" -m scripts.sync_local_env --angel "${ROOT}/var/local/angel.env"
fi

echo "== news + strategy smoke =="
"$PY" -m scripts.refresh_news_scores --llm || "$PY" -m scripts.refresh_news_scores
"$PY" -m scripts.run_strategy_tests --prereg --lake var/lake || true
"$PY" -m scripts.fy_history_depth --lake var/lake || true

if ! pgrep -f "scripts.download_bhav" >/dev/null 2>&1; then
  echo "== start bhav download (background) =="
  nohup "$PY" -m scripts.download_bhav --from 2012-01-01 --to "$(date +%Y-%m-%d)" \
    --out var/bhav --sleep 2.0 >> var/reports/download_bhav.log 2>&1 &
fi

if "$PY" -m scripts.login_check >/dev/null 2>&1; then
  echo "== Angel OK — starting FY 1m backfill (background) =="
  nohup "$PY" -m scripts.run_fy_angel_backfill >> var/reports/fy_angel_backfill.log 2>&1 &
else
  echo "== Angel skipped: fill config/angel.env (see config/angel.env.example) =="
fi

echo "== done; logs under var/reports/ =="
