#!/usr/bin/env bash
set -euo pipefail

BACKUP_DIR="${HOME}/projetos/Ritmo/1.0"
PROD_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DB_SRC="${RITMO_DB_PATH:-$HOME/.local/share/ritmo/ritmo.sqlite3}"

echo "=========================================================="
echo " [TRAVA DE SEGURANÇA] INICIANDO BACKUP DA VERSÃO 1.0      "
echo "=========================================================="

mkdir -p "$BACKUP_DIR"

if [ -f "$DB_SRC" ]; then
    echo "==> Realizando snapshot consistente do banco SQLite..."
    sqlite3 "$DB_SRC" ".backup '$BACKUP_DIR/ritmo_v1.0.db'"
    echo "[OK] Banco de dados salvo em: $BACKUP_DIR/ritmo_v1.0.db"
else
    echo "[AVISO] Arquivo de banco $DB_SRC não encontrado. Prosseguindo com código..."
fi

echo "==> Copiando snapshot integral do código-fonte..."
rsync -av \
    --exclude '__pycache__' \
    --exclude '*.pyc' \
    --exclude '.git' \
    --exclude '.env' \
    --exclude 'versao_1.1.txt' \
    --exclude 'melhorias' \
    "$PROD_DIR/" "$BACKUP_DIR/"

if [ ! -f "$BACKUP_DIR/backend/app.py" ] && [ ! -f "$BACKUP_DIR/app.py" ]; then
    echo "=========================================================="
    echo " [ERRO FATAL] O backup não pôde ser validado com sucesso! "
    echo " Abortando deploy em produção para evitar perda de dados.  "
    echo "=========================================================="
    exit 1
fi

echo "=========================================================="
echo " [SUCESSO] Backup da v1.0 homologado e travado em:        "
echo " $BACKUP_DIR "
echo " Liberado para executar migrações e atualizações da v1.1. "
echo "=========================================================="
