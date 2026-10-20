#!/usr/bin/env bash
set -Eeuo pipefail
cd "$(dirname "$(realpath "$0")")/.."
# Interrompe a atualização se algum destino de backup falhar.
./scripts/backup.sh pre-update
docker compose build --pull
docker compose up -d --wait
