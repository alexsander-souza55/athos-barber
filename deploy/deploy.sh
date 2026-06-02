#!/usr/bin/env bash
# deploy.sh — atualiza a aplicação em produção (zero-downtime com Gunicorn reload)
# Uso: bash deploy.sh
# Executar como: sudo -u barberhub bash deploy.sh

set -euo pipefail

APP_DIR="/var/www/barberhub"
VENV="$APP_DIR/venv/bin"
SERVICE="barberhub"

echo "==> [1/5] Entrando no diretório da aplicação..."
cd "$APP_DIR"

echo "==> [2/5] Atualizando código do repositório..."
git pull --ff-only

echo "==> [3/5] Instalando/atualizando dependências..."
"$VENV/pip" install -r requirements.txt --quiet --no-cache-dir

echo "==> [4/5] Aplicando migrações de banco (init-db é idempotente)..."
FLASK_CONFIG=production "$VENV/flask" --app wsgi init-db

echo "==> [5/5] Recarregando serviço (graceful reload)..."
sudo systemctl reload "$SERVICE"

echo ""
echo "Deploy concluído com sucesso em $(date '+%Y-%m-%d %H:%M:%S')."
echo "Status: sudo systemctl status $SERVICE"
