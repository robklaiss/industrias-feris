#!/bin/bash
# Script para ejecutar el servidor web TESAKA-SIFEN

set -euo pipefail

# Ir al directorio del proyecto
cd "$(dirname "$0")/.."

# Activar venv si existe
if [ -f "../.venv/bin/activate" ]; then
    source ../.venv/bin/activate
elif [ -f ".venv/bin/activate" ]; then
    source .venv/bin/activate
fi

# Verificar que SIFEN_EMISOR_RUC esté configurado
if [ -z "${SIFEN_EMISOR_RUC:-}" ]; then
    echo "⚠️  SIFEN_EMISOR_RUC no está configurado"
    echo "   Ejecuta: export SIFEN_EMISOR_RUC='4554737-8'"
    echo ""
    read -p "¿Continuar de todos modos? (y/n) " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        exit 1
    fi
fi

# Ejecutar servidor
echo "🚀 Iniciando servidor web en http://127.0.0.1:8000"
echo ""
python -m uvicorn web.main:app --reload --host 127.0.0.1 --port 8000

