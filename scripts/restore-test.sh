#!/usr/bin/env bash
# Exclusivamente para validar em ambiente isolado; não restaura a produção.
set -Eeuo pipefail
export TZ=America/Sao_Paulo
umask 077
root=$(cd "$(dirname "$0")/.." && pwd)
archive=$(realpath "${1:-$root/backups/weekly.tar.gz}")
[[ -f "$archive" ]] || { echo 'Backup não encontrado.'; exit 1; }
[[ ! -f "$archive.sha256" ]] || (cd "$(dirname "$archive")" && sha256sum -c "$(basename "$archive").sha256")
stage=$(mktemp -d /tmp/treinos-restore-XXXXXX)
project="treinos-restore-$(date +%s)-$$"
cleanup(){ if [[ -f "$stage/project/docker-compose.yml" ]]; then (cd "$stage/project" && docker compose -p "$project" down -v >/dev/null 2>&1) || true; fi; rm -rf "$stage"; }
trap cleanup EXIT
python3 - "$archive" "$stage" <<'PY'
import sys,tarfile
from pathlib import Path
archive,stage=sys.argv[1:];root=Path(stage)
# Ubuntu 26.04 possui o filtro data, que rejeita caminhos perigosos.
with tarfile.open(archive) as t:t.extractall(root,filter='data')
with tarfile.open(root/'application.tar.gz') as t:t.extractall(root/'project',filter='data')
PY
cd "$stage/project"
find frontend -type d -exec chmod 755 {} +
find frontend -type f -exec chmod 644 {} +
chmod 644 nginx.conf
# Nome explícito cria uma rede e volume diferentes dos de produção.
export HTTP_PORT=${RESTORE_TEST_PORT:-18088} COOKIE_SECURE=false
docker compose -p "$project" up -d --wait db
docker compose -p "$project" exec -T db sh -c 'MYSQL_PWD="$MYSQL_PASSWORD" exec mysql -u"$MYSQL_USER" "$MYSQL_DATABASE"' < "$stage/database.sql"
docker compose -p "$project" up -d --build --wait
curl --fail --silent "http://127.0.0.1:$HTTP_PORT/api/health"
docker compose -p "$project" exec -T app python - <<'PY'
import secrets
from app import app,DB,Exercise,Workout,Account,ph
from sqlalchemy import select,func
with DB() as d:
    count=d.scalar(select(func.count()).select_from(Exercise))
    assert count>=18
    a=d.get(Account,1)
    if a: assert a.password_hash.startswith('$argon2id$')
    print(f'\nRESTAURAÇÃO ISOLADA OK: {count} exercícios; '+str(d.scalar(select(func.count()).select_from(Workout)))+' sessões; hash validado se configurado.')
# Credencial temporária somente no banco restaurado, descartado ao terminar.
password=secrets.token_urlsafe(24)
with DB.begin() as d:
    a=d.get(Account,1)
    if not a:
        a=Account(id=1);d.add(a)
    a.password_hash=ph.hash(password);a.version=secrets.token_hex(32)
c=app.test_client()
csrf=c.get('/api/auth').json['csrf']
r=c.post('/api/login',json={'password':password},headers={'X-CSRF-Token':csrf})
assert r.status_code==200
assert c.get('/api/exercises').status_code==200
assert c.get('/api/routines').status_code==200
print('LOGIN no ambiente restaurado validado com senha temporária aleatória.')
PY
