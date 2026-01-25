#!/usr/bin/env bash
set -euo pipefail

# Script para ejecutar consulta-lote en ambiente TEST con artifacts de Desktop
# Uso:
#   bash tesaka-final/run_test_follow.sh [--quiet] [--tail 150]
#   bash tesaka-final/run_test_follow.sh --help

QUIET=false
TAIL_LINES=120
TIMESTAMP=$(date +"%Y%m%d_%H%M%S")

show_help() {
    cat <<EOF
Uso: $0 [OPCIONES]

Runner para follow/consulta-lote contra artifacts locales.

Opciones:
  --quiet            Captura el output completo en log y solo muestra tail en vivo
  --tail <N>         Cambia las líneas mostradas en modo quiet (defecto: $TAIL_LINES)
  -h, --help         Muestra esta ayuda y sale

Ejemplos:
  $0
  $0 --quiet
  $0 --quiet --tail 200
EOF
}

while [[ $# -gt 0 ]]; do
    case "$1" in
        --quiet)
            QUIET=true
            shift
            ;;
        --tail)
            if [[ $# -lt 2 ]]; then
                echo "❌ Falta valor para --tail" >&2
                exit 1
            fi
            TAIL_LINES="$2"
            shift 2
            ;;
        -h|--help)
            show_help
            exit 0
            ;;
        *)
            echo "❌ Opción desconocida: $1" >&2
            show_help
            exit 1
            ;;
    esac
done

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

COMMAND=(bash ./tools/sifen_run.sh test follow --once "$RESPONSE_FILE" --artifacts-dir "$ARTIFACTS_DIR")

echo ""
echo "⚡ Ejecutando: ${COMMAND[*]}"
echo ""

if [[ "$QUIET" == true ]]; then
    LOG_FILE="$ARTIFACTS_DIR/run_test_follow_${TIMESTAMP}.log"
    echo "🔇 Modo quiet habilitado. Mostrando tail -n $TAIL_LINES (log completo: $LOG_FILE)"
    : > "$LOG_FILE"

    "${COMMAND[@]}" >"$LOG_FILE" 2>&1 &
    CMD_PID=$!

    tail -n "$TAIL_LINES" -f "$LOG_FILE" &
    TAIL_PID=$!

    set +e
    wait $CMD_PID
    CMD_EXIT=$?
    set -e

    # Dar un pequeño margen para que tail procese lo último
    sleep 0.5
    kill "$TAIL_PID" 2>/dev/null || true
    wait "$TAIL_PID" 2>/dev/null || true

    echo ""
    echo "📄 Log completo guardado en: $LOG_FILE"
    if [[ $CMD_EXIT -eq 0 ]]; then
        echo "✅ Ejecución completada (exit 0)."
    else
        echo "❌ Ejecución falló con exit $CMD_EXIT. Revisa el log."
    fi
    exit $CMD_EXIT
else
    # Usar el .venv del repositorio principal
    "${COMMAND[@]}"
fi

echo ""
echo "✅ Ejecución completada. Revisa los dumps en: $ARTIFACTS_DIR"
echo "   - Busca: zeep_consulta_lote_sent_try*.xml (request SOAP)"
echo "   - Busca: zeep_consulta_lote_headers_*.txt (headers enviados)"
