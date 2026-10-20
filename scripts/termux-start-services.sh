#!/data/data/com.termux/files/usr/bin/sh
set -eu
ROOT="$HOME/ritmo-termux"
DATA="$HOME/.local/share/ritmo"
mkdir -p "$DATA/log/api" "$DATA/log/nginx" "$PREFIX/var/service"
termux-wake-lock
for service in ritmo-api ritmo-nginx ritmo-backup ritmo-push; do
    target="$PREFIX/var/service/$service"
    source="$ROOT/services/$service"
    if [ -e "$target" ] && [ "$(readlink "$target" 2>/dev/null || true)" != "$source" ]; then
        echo "Serviço já existe em $target; não será substituído." >&2
        exit 1
    fi
    [ -e "$target" ] || ln -s "$source" "$target"
done
export SVDIR="$PREFIX/var/service"
export LOGDIR="$PREFIX/var/log"
"$PREFIX/bin/service-daemon" start || true
sleep 1
"$PREFIX/bin/sv" up ritmo-api ritmo-nginx ritmo-backup ritmo-push
