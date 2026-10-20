#!/data/data/com.termux/files/usr/bin/sh
set -eu
"$PREFIX/bin/sv" down ritmo-api ritmo-nginx ritmo-backup ritmo-push
termux-wake-unlock
