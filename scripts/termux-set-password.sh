#!/data/data/com.termux/files/usr/bin/sh
set -eu
cd "$HOME/ritmo-termux"
set -a
. ./.env
set +a
export COOKIE_SECURE=false
exec .venv/bin/python backend/manage.py
