#!/usr/bin/env bash
# Run ON the EC2 as ubuntu. Creates .env from crypto's (rewrites DB name), venv, systemd.
set -euo pipefail
REPO=/home/ubuntu/nse-engine
CRYPTO=/home/ubuntu/crypto-signal-engine
cd "$REPO"

python3.12 -m venv .venv
.venv/bin/pip install -U pip -q
.venv/bin/pip install -r requirements.txt -q

# Build .env: only infra secrets — API keys go in Postgres via /keys
CRYPTO_ENV="$CRYPTO/.env"
DB_URL=$(grep -E '^DATABASE_URL=' "$CRYPTO_ENV" | head -1 | cut -d= -f2- | tr -d '"'\''\r')
# rewrite db name to nse_engine
NSE_DB_URL=$(DB_URL="$DB_URL" .venv/bin/python - <<'PY'
import os
from urllib.parse import urlparse, urlunparse
u = urlparse(os.environ["DB_URL"].replace("postgresql+asyncpg://","postgresql://").replace("postgres://","postgresql://"))
print(urlunparse((u.scheme, u.netloc, "/nse_engine", "", "", "")))
PY
)
MASTER=$(grep -E '^SECRETS_MASTER_KEY=' "$CRYPTO_ENV" | head -1 | cut -d= -f2- | tr -d '"'\''\r')
ADMIN=$(grep -E '^ADMIN_PASSWORD=' "$CRYPTO_ENV" | head -1 | cut -d= -f2- | tr -d '"'\''\r')

umask 077
cat > .env <<EOF
PORT=8090
WEB_HOST=0.0.0.0
WEB_PORT=8090
PYTHONUNBUFFERED=1
DATABASE_URL=${NSE_DB_URL}
SECRETS_MASTER_KEY=${MASTER}
ADMIN_PASSWORD=${ADMIN}
MODE=paper
LIVE_ORDERS=false
DATA_DIR=/home/ubuntu/nse-engine/var
TZ=Asia/Kolkata
EOF
chmod 600 .env

mkdir -p var/lake var/news var/llm_calls /home/ubuntu/shared
# ensure Python package `data/` was synced (not the runtime dir)
test -f data/calendar.py
set -a
# shellcheck disable=SC1091
source .env
set +a
# init schema
.venv/bin/python - <<'PY'
import os
from pathlib import Path
from dotenv import load_dotenv
load_dotenv(Path("/home/ubuntu/nse-engine/.env"))
assert os.environ.get("DATABASE_URL"), "DATABASE_URL missing"
from storage.pg import init_postgres
init_postgres()
print("schema ok", os.environ["DATABASE_URL"].split("@")[-1][:40])
PY

sudo cp deploy/nse-engine.service /etc/systemd/system/nse-engine.service
echo "ubuntu ALL=(ALL) NOPASSWD: /bin/systemctl restart nse-engine, /usr/bin/systemctl restart nse-engine, /bin/systemctl status nse-engine, /usr/bin/systemctl status nse-engine, /bin/systemctl stop nse-engine, /usr/bin/systemctl stop nse-engine, /bin/systemctl start nse-engine, /usr/bin/systemctl start nse-engine" | sudo tee /etc/sudoers.d/nse-engine >/dev/null
sudo chmod 0440 /etc/sudoers.d/nse-engine
sudo systemctl daemon-reload
sudo systemctl enable nse-engine
sudo systemctl restart nse-engine
sleep 3
sudo systemctl --no-pager --full status nse-engine || true
curl -fsS http://127.0.0.1:8090/api/health || true
echo
echo "NSE portal: http://$(curl -s --connect-timeout 2 https://checkip.amazonaws.com || echo 52.62.37.4):8090/"
echo "Keys page:  http://...:8090/keys  (same ADMIN_PASSWORD as crypto)"
