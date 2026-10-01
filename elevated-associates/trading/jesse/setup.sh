#!/usr/bin/env bash
# Jesse (open-source backtesting framework) for RESEARCH ONLY: backtests and paper results.
# Free tier only. Never installs the paid live-trade plugin and never reads or stores exchange keys.
#   ./setup.sh setup    install Jesse + project template, services and database (idempotent)
#   ./setup.sh start    start Postgres, Redis and the dashboard (http://localhost:9000)
#   ./setup.sh stop     stop the dashboard
#   ./setup.sh status   show what is running
# Needs python3 (3.10-3.12), git, postgresql and redis-server on this machine.
set -euo pipefail

HOME_DIR="${JESSE_HOME:-$HOME/jesse-bot}"
PROJECT="$HOME_DIR/bot"
VENV="$HOME_DIR/.venv"
DB_USER=jesse_user
DB_NAME=jesse_db

as_postgres() { if [ "$(id -u)" -eq 0 ]; then su postgres -c "$1"; else sudo -u postgres bash -c "$1"; fi; }

env_get() { sed -n "s/^$1=//p" "$PROJECT/.env" | head -1; }

start_services() {
  if command -v pg_lsclusters >/dev/null && ! pg_lsclusters | grep -q online; then
    pg_ctlcluster "$(pg_lsclusters -h | awk 'NR==1{print $1}')" main start 2>/dev/null || sudo service postgresql start
  fi
  redis-cli ping >/dev/null 2>&1 || redis-server --daemonize yes --save "" >/dev/null
}

case "${1:-status}" in
  setup)
    mkdir -p "$HOME_DIR"
    [ -d "$VENV" ] || python3 -m venv "$VENV"
    "$VENV/bin/pip" install -q --upgrade pip jesse
    [ -d "$PROJECT/.git" ] || git clone -q --depth 1 https://github.com/jesse-ai/project-template.git "$PROJECT"
    # Jesse writes AGENTS.md into the template clone; keep that clone's git status clean.
    grep -qx AGENTS.md "$PROJECT/.git/info/exclude" 2>/dev/null || echo AGENTS.md >> "$PROJECT/.git/info/exclude"
    if [ ! -f "$PROJECT/.env" ]; then
      pw="$("$VENV/bin/python" -c 'import secrets;print(secrets.token_urlsafe(16))')"
      dash="$("$VENV/bin/python" -c 'import secrets;print(secrets.token_urlsafe(12))')"
      sed -e "s/^PASSWORD=.*/PASSWORD=$dash/" -e 's/^POSTGRES_HOST=postgres/POSTGRES_HOST=localhost/' \
          -e "s/^POSTGRES_PASSWORD=.*/POSTGRES_PASSWORD=$pw/" -e 's/^REDIS_HOST=redis/REDIS_HOST=localhost/' \
          "$PROJECT/.env.example" > "$PROJECT/.env"
      chmod 600 "$PROJECT/.env"
    fi
    start_services
    pw="$(env_get POSTGRES_PASSWORD)"
    as_postgres "psql -tAc \"SELECT 1 FROM pg_roles WHERE rolname='$DB_USER'\"" | grep -q 1 \
      || as_postgres "psql -qc \"CREATE USER $DB_USER WITH PASSWORD '$pw';\""
    as_postgres "psql -tAc \"SELECT 1 FROM pg_database WHERE datname='$DB_NAME'\"" | grep -q 1 \
      || as_postgres "psql -qc \"CREATE DATABASE $DB_NAME OWNER $DB_USER;\""
    echo "Jesse set up in $HOME_DIR. Dashboard password: grep ^PASSWORD $PROJECT/.env" ;;
  start)
    start_services
    cd "$PROJECT"
    nohup "$VENV/bin/jesse" run --skip-lsp > "$HOME_DIR/jesse.log" 2>&1 &
    echo "Starting; log: $HOME_DIR/jesse.log, dashboard: http://localhost:$(env_get APP_PORT)" ;;
  stop)
    pkill -f "$VENV/bin/jesse run" && echo stopped || echo "not running" ;;
  status)
    curl -s -o /dev/null -w "dashboard http=%{http_code}\n" "http://localhost:$(env_get APP_PORT)/" || echo "dashboard down"
    redis-cli ping 2>&1 | head -1 ;;
  *) echo "usage: $0 setup|start|stop|status" >&2; exit 2 ;;
esac
