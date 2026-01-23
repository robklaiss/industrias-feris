#!/bin/bash
# Script para ejecutar el servidor web_smoke_api.py con CORS habilitado

set -euo pipefail

# Ir al directorio del proyecto
cd "$(dirname "$0")/.."

# Activar venv si existe
if [ -f "../.venv/bin/activate" ]; then
    source ../.venv/bin/activate
elif [ -f ".venv/bin/activate" ]; then
    source .venv/bin/activate
fi

# Configurar modo desarrollo para habilitar CORS
export TESAKA_DEV_MODE=1

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

# Ejecutar servidor en el puerto 8009
echo "🚀 Iniciando servidor web_smoke_api en http://127.0.0.1:8009"
echo "   CORS habilitado para localhost:3000, localhost:4200"
echo "   Endpoint POST /send-de disponible"
echo ""

# Opción: usar --reload para desarrollo
if [ "${1:-}" == "--reload" ]; then
    python -m uvicorn web_smoke_api:app --reload --host 127.0.0.1 --port 8009
else
    python -m uvicorn web_smoke_api:app --host 127.0.0.1 --port 8009
fi
