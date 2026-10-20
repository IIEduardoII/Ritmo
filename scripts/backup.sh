#!/usr/bin/env bash
set -Eeuo pipefail
export TZ=America/Sao_Paulo
umask 077
cd "$(dirname "$(realpath "$0")")/.."
mkdir -p backups
exec 9>backups/backup.lock
flock -n 9 || { echo 'Outro backup está em execução.'; exit 1; }
log(){ printf '%s %s\n' "$(date -Is)" "$*" | tee -a backups/backup.log; }
trap 'log "FALHA: backup interrompido na linha $LINENO."' ERR
mode=${1:-weekly}
[[ "$mode" == weekly || "$mode" == pre-update ]] || { log 'Modo inválido.'; exit 1; }
USB_MOUNT= DRIVE_REMOTE= RCLONE_CONFIG_DIR="$HOME/.config/treinos-rclone"
[[ ! -f backup.conf ]] || source backup.conf
stage=$(mktemp -d backups/.stage-XXXXXX)
trap 'rm -rf "$stage"' EXIT
log 'INÍCIO: exportando banco e aplicação.'
docker compose exec -T db sh -c 'MYSQL_PWD="$MYSQL_PASSWORD" exec mysqldump -u"$MYSQL_USER" --single-transaction --no-tablespaces --set-gtid-purged=OFF "$MYSQL_DATABASE"' > "$stage/database.sql"
[[ -s "$stage/database.sql" ]]
# O .env é necessário para restaurar a aplicação; o arquivo final não é criptografado.
tar --exclude='./backups' --exclude='./.git' --exclude='./backup.conf' --exclude='./.venv' --exclude='*.log' --exclude='*/__pycache__' -czf "$stage/application.tar.gz" .
if [[ "$mode" == weekly ]]; then name=weekly.tar.gz; else name=pre-update-$(date +%Y%m%d-%H%M%S).tar.gz; fi
tar -czf "$stage/$name" -C "$stage" database.sql application.tar.gz
tar -tzf "$stage/$name" >/dev/null
mv "$stage/$name" "backups/$name"
(cd backups && sha256sum "$name" > "$name.sha256")
log "SUCESSO LOCAL: $name criado."
failed=0
if [[ -n "$USB_MOUNT" ]] && mountpoint -q "$USB_MOUNT"; then
    if mkdir -p "$USB_MOUNT/treinos" && cp "backups/$name" "$USB_MOUNT/treinos/.$name.tmp" && mv "$USB_MOUNT/treinos/.$name.tmp" "$USB_MOUNT/treinos/$name" && cp "backups/$name.sha256" "$USB_MOUNT/treinos/$name.sha256"; then
        sync -f "$USB_MOUNT/treinos/$name"; log 'SUCESSO USB: cópia concluída.'
    else log 'FALHA USB: não foi possível copiar.'; failed=1; fi
else log 'FALHA USB: pendrive não configurado ou não montado.'; failed=1; fi
if [[ -n "$DRIVE_REMOTE" && -f "$RCLONE_CONFIG_DIR/rclone.conf" ]]; then
    rclone(){ docker run --rm --user "$(id -u):$(id -g)" -v "$RCLONE_CONFIG_DIR:/config/rclone" -v "$PWD/backups:/data:ro" rclone/rclone:1.70.3 "$@"; }
    if rclone copyto "/data/$name" "$DRIVE_REMOTE/$name" && rclone copyto "/data/$name.sha256" "$DRIVE_REMOTE/$name.sha256"; then
        log 'SUCESSO DRIVE: cópia concluída.'
    else log 'FALHA DRIVE: envio não concluído.'; failed=1; fi
else log 'FALHA DRIVE: autenticação/configuração pendente.'; failed=1; fi
[[ "$failed" == 0 ]] && log 'SUCESSO: todos os destinos concluídos.'
exit "$failed"
