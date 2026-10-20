#!/data/data/com.termux/files/usr/bin/sh
set -eu
termux-wake-lock
exec "$HOME/ritmo-termux/scripts/termux-start-services.sh"
