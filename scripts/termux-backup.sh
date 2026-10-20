#!/data/data/com.termux/files/usr/bin/bash
# Backup do Ritmo (Termux/SQLite) -> cópia local + Google Drive (pasta Ritmo), em texto simples.
# Uso: termux-backup.sh [daily|manual]
#   daily  : entra na retenção automática (30 dias; 1 mensal por mês, 400 dias).
#   manual : nunca é apagado pela retenção (ex.: antes de uma atualização).
# Não inclui .env (SECRET_KEY, GEMINI_API_KEY) nem certs/ (chave privada TLS): recrie .env com scripts/setup-termux.py e reinstale certs/ da CA local ao restaurar.
set -Eeuo pipefail
umask 077

MODE="${1:-daily}"
[[ "$MODE" == daily || "$MODE" == manual ]] || { echo "Modo inválido: $MODE" >&2; exit 64; }

ROOT="$HOME/ritmo-termux"
DATA="$HOME/.local/share/ritmo"
DB="$DATA/ritmo.sqlite3"
OUT="$HOME/ritmo-backups"
REMOTE_NAME="${RITMO_RCLONE_REMOTE:-gdrive}"
REMOTE="$REMOTE_NAME:${RITMO_DRIVE_DIR:-Ritmo}"
KEEP_LOCAL=7
KEEP_DAILY_DAYS=30
KEEP_MONTHLY_DAYS=400
STATE="$DATA/backup-last-success"
LOG="$DATA/backup.log"

mkdir -p "$OUT" "$DATA"
log() { printf '%s %s\n' "$(date '+%Y-%m-%dT%H:%M:%S%z')" "$*" | tee -a "$LOG"; }

# Trava simples por diretório (flock pode não existir no Termux); ignora trava de processo morto.
LOCK="$OUT/.lock.d"
if ! mkdir "$LOCK" 2>/dev/null; then
    if [[ -f "$LOCK/pid" ]] && kill -0 "$(cat "$LOCK/pid")" 2>/dev/null; then
        log 'Outro backup está em execução.'; exit 75
    fi
    rm -rf "$LOCK"; mkdir "$LOCK"
fi
echo $$ > "$LOCK/pid"
stage="$(mktemp -d "$OUT/.stage-XXXXXX")"
cleanup() { rm -rf "$stage" "$LOCK"; }
trap cleanup EXIT
trap 'log "FALHA: backup interrompido na linha $LINENO."' ERR

[[ -s "$DB" ]] || { log "FALHA: banco não encontrado em $DB."; exit 66; }
log "INÍCIO ($MODE): exportando banco e aplicação."

# 1) Cópia consistente (API de backup do SQLite, banco aberto só para leitura) + dump SQL em texto.
"$ROOT/.venv/bin/python" - "$DB" "$stage" <<'PY'
import sqlite3, sys
src_path, stage = sys.argv[1], sys.argv[2]
src = sqlite3.connect(f'file:{src_path}?mode=ro', uri=True)
dst = sqlite3.connect(f'{stage}/ritmo.sqlite3')
src.backup(dst)
src.close()
status = dst.execute('PRAGMA integrity_check').fetchone()[0]
if status != 'ok':
    sys.exit(f'integrity_check falhou: {status}')
tables = [r[0] for r in dst.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")]
with open(f'{stage}/ritmo.sql', 'w', encoding='utf-8') as f:
    for line in dst.iterdump():
        f.write(line + '\n')
with open(f'{stage}/MANIFEST.txt', 'w', encoding='utf-8') as f:
    f.write('Backup do Ritmo (texto simples)\n')
    for t in tables:
        f.write(f'{t}: {dst.execute(f"SELECT count(*) FROM {t}").fetchone()[0]} linhas\n')
dst.close()
PY
[[ -s "$stage/ritmo.sqlite3" && -s "$stage/ritmo.sql" ]]

# 2) Aplicação (sem .venv, .env, caches, logs e pastas de backup antigas).
tar -C "$ROOT" --exclude=./.venv --exclude=./.env --exclude=./certs --exclude='__pycache__' \
    --exclude='./.pwa-backup-*' --exclude='*.log' -czf "$stage/application.tar.gz" .
{
    echo "modo: $MODE"
    echo "data: $(date '+%Y-%m-%dT%H:%M:%S%z')"
    echo "rodape_versao: $(grep -o 'v[0-9]\+\.[0-9]\+\.[0-9]\+' "$ROOT/frontend/index.html" | head -n1 || true)"
    echo "restauracao: extrair; ritmo.sqlite3 -> ~/.local/share/ritmo/; application.tar.gz -> ~/ritmo-termux; recriar .env com scripts/setup-termux.py"
} >> "$stage/MANIFEST.txt"

# 3) Pacote final + verificação.
name="ritmo-$MODE-$(date +%Y%m%d-%H%M%S).tar.gz"
tar -czf "$stage/$name" -C "$stage" ritmo.sqlite3 ritmo.sql application.tar.gz MANIFEST.txt
tar -tzf "$stage/$name" > /dev/null
mv "$stage/$name" "$OUT/$name"
(cd "$OUT" && sha256sum "$name" > "$name.sha256")
log "SUCESSO LOCAL: $name ($(du -h "$OUT/$name" | cut -f1))."

# Mantém só os KEEP_LOCAL pacotes locais mais recentes (daily); manual nunca é apagado.
{ ls -1t "$OUT"/ritmo-daily-*.tar.gz 2>/dev/null || true; } | tail -n +$((KEEP_LOCAL + 1)) | while read -r old; do
    rm -f "$old" "$old.sha256"
done

# 4) Google Drive.
if ! rclone listremotes 2>/dev/null | grep -qx "$REMOTE_NAME:"; then
    log "FALHA DRIVE: remote '$REMOTE_NAME' não configurado no rclone. Cópia local preservada."
    exit 2
fi
rclone copyto "$OUT/$name" "$REMOTE/$name" --retries 3 --low-level-retries 5
rclone copyto "$OUT/$name.sha256" "$REMOTE/$name.sha256" --retries 3
remote_md5="$(rclone hashsum md5 "$REMOTE/$name" 2>/dev/null | awk '{print $1}')"
local_md5="$(md5sum "$OUT/$name" | awk '{print $1}')"
if [[ -z "$remote_md5" || "$remote_md5" != "$local_md5" ]]; then
    log "FALHA DRIVE: verificação MD5 divergente para $name. Nada foi apagado."
    exit 3
fi
log "SUCESSO DRIVE: $name verificado por MD5."

# 5) Cópia mensal (uma por mês) e retenção — somente depois do envio verificado.
if [[ "$MODE" == daily ]]; then
    monthly="ritmo-monthly-$(date +%Y%m).tar.gz"
    if [[ -z "$(rclone lsf "$REMOTE" --include "$monthly" 2>/dev/null)" ]]; then
        rclone copyto "$REMOTE/$name" "$REMOTE/$monthly"
        log "Cópia mensal criada: $monthly."
    fi
    rclone delete "$REMOTE" --include 'ritmo-daily-*' --min-age "${KEEP_DAILY_DAYS}d" || log 'Aviso: retenção diária não concluída.'
    rclone delete "$REMOTE" --include 'ritmo-monthly-*' --min-age "${KEEP_MONTHLY_DAYS}d" || log 'Aviso: retenção mensal não concluída.'
fi

[[ "$MODE" != daily ]] || date +%F > "$STATE"
log "SUCESSO: backup ($MODE) local e Drive concluídos."
