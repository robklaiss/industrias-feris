#!/usr/bin/env bash
set -euo pipefail

# Script para ejecutar consulta-lote en ambiente TEST con artifacts de Desktop
# Uso: bash tesaka-final/run_test_follow.sh

echo "🚀 Ejecutando follow/consulta-lote con ambiente limpio..."

# Configurar entorno
cd "$(dirname "$0")/.."  # Ir a tesaka-cv
export SIFEN_ENV=test
export SIFEN_XSD_DIR="$(pwd)/tesaka-final/schemas_sifen"

# Path al artifacts dir con los datos de prueba
ARTIFACTS_DIR="/Users/robinklaiss/Desktop/SIFEN_ARTIFACTS_TEST_20260123"

# Verificar que existe el artifacts dir
if [[ ! -d "$ARTIFACTS_DIR" ]]; then
    echo "❌ No existe el directorio: $ARTIFACTS_DIR"
    exit 1
fi

# Buscar el último response_recepcion_*.json
RESPONSE_FILE=$(ls -t "$ARTIFACTS_DIR"/response_recepcion_*.json 2>/dev/null | head -n1 || true)

if [[ -z "$RESPONSE_FILE" ]]; then
    echo "❌ No se encontró response_recepcion_*.json en $ARTIFACTS_DIR"
    exit 1
fi

echo "📁 Usando artifacts dir: $ARTIFACTS_DIR"
echo "📄 Usando response: $(basename "$RESPONSE_FILE")"

# Ejecutar follow con consulta-lote
echo ""
echo "⚡ Ejecutando: bash ./tools/sifen_run.sh test follow --once \"$RESPONSE_FILE\" --artifacts-dir \"$ARTIFACTS_DIR\""
echo ""

# Usar el .venv del repositorio principal
bash ./tools/sifen_run.sh test follow --once "$RESPONSE_FILE" --artifacts-dir "$ARTIFACTS_DIR"

echo ""
echo "✅ Ejecución completada. Revisa los dumps en: $ARTIFACTS_DIR"
echo "   - Busca: zeep_consulta_lote_sent_try*.xml (request SOAP)"
echo "   - Busca: zeep_consulta_lote_headers_*.txt (headers enviados)"
