#!/bin/bash
# Runner oficial para ejecutar scripts desde el clipboard
# Evita crasheos de Terminal al pegar scripts enormes

set -euo pipefail

# Configuración
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
LOGS_DIR="$PROJECT_ROOT/logs"
TIMESTAMP=$(date +"%Y%m%d_%H%M%S")

# Crear directorio de logs si no existe
mkdir -p "$LOGS_DIR"

# Archivos de log
LOG_FILE="$LOGS_DIR/patch_run_$TIMESTAMP.log"
CLIPBOARD_FILE="$LOGS_DIR/clipboard_$TIMESTAMP.py"

# Colores para output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Función de logging
log() {
    echo -e "${BLUE}[$(date '+%Y-%m-%d %H:%M:%S')]${NC} $1" | tee -a "$LOG_FILE"
}

error() {
    echo -e "${RED}[ERROR]${NC} $1" | tee -a "$LOG_FILE"
}

success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1" | tee -a "$LOG_FILE"
}

warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1" | tee -a "$LOG_FILE"
}

# Función para mostrar ayuda
show_help() {
    cat << EOF
Uso: $0 [OPCIONES]

Runner para ejecutar scripts Python desde el clipboard con logging seguro.

Opciones:
    -h, --help          Muestra esta ayuda
    -v, --verbose       Modo verbose (muestra más detalle)
    -d, --dry-run       Solo muestra el script sin ejecutarlo
    -k, --keep          Mantiene el archivo temporal del script

    --python CMD        Usa CMD como intérprete Python (defecto: python3)
    --type TIPO         Fuerza tipo: auto|python|bash (defecto: auto)

Ejemplos:

    $0                  # Ejecuta script desde clipboard
    $0 -v               # Modo verbose
    $0 -d               # Solo muestra lo que se ejecutaría
    $0 --python .venv/bin/python  # Usa venv específico
    $0 --type bash       # Fuerza ejecución como script bash

EOF
}

# Valores por defecto
VERBOSE=false
DRY_RUN=false
KEEP_FILE=false
TYPE="auto"

# Preferir el python del venv del proyecto si existe
if [[ -x "$PROJECT_ROOT/.venv/bin/python" ]]; then
    PYTHON_CMD="$PROJECT_ROOT/.venv/bin/python"
else
    PYTHON_CMD="python3"
fi

# Parsear argumentos
while [[ $# -gt 0 ]]; do
    case $1 in
        -h|--help)
            show_help
            exit 0
            ;;
        -v|--verbose)
            VERBOSE=true
            shift
            ;;
        -d|--dry-run)
            DRY_RUN=true
            shift
            ;;
        -k|--keep)
            KEEP_FILE=true
            shift
            ;;
        --python)
            PYTHON_CMD="$2"
            shift 2
            ;;
        --type)
            TYPE="$2"
            shift 2
            ;;
        *)
            error "Opción desconocida: $1"
            show_help
            exit 1
            ;;
    esac
done

# Iniciar ejecución
log "Iniciando run_patch_from_clipboard.sh"
log "Log file: $LOG_FILE"

# Verificar pbpaste (macOS)
if ! command -v pbpaste &> /dev/null; then
    error "pbpaste no encontrado. Este script requiere macOS."
    exit 1
fi

# Obtener contenido del clipboard
log "Leyendo contenido del clipboard..."
CLIPBOARD_CONTENT=$(pbpaste)

if [[ -z "$CLIPBOARD_CONTENT" ]]; then
    error "El clipboard está vacío."
    exit 1
fi

# Stop hardcoding extension before detection
CLIPBOARD_BASE="$LOGS_DIR/clipboard_$TIMESTAMP"

# Determinar tipo de script (auto|python|bash)
SCRIPT_TYPE="$TYPE"

if [[ "$SCRIPT_TYPE" == "auto" ]]; then
    first_line="$(printf '%s\n' "$CLIPBOARD_CONTENT" | head -n 1)"

    if [[ "$first_line" == \#!* ]]; then
        if echo "$first_line" | grep -qiE 'bash|/sh'; then
            SCRIPT_TYPE="bash"
        elif echo "$first_line" | grep -qiE 'python'; then
            SCRIPT_TYPE="python"
        else
            SCRIPT_TYPE="python"
        fi
    else
        if echo "$CLIPBOARD_CONTENT" | grep -qE '^\s*(from|import)\s+'; then
            SCRIPT_TYPE="python"
        elif echo "$CLIPBOARD_CONTENT" | grep -qE '^\s*(cd |export |bash |chmod |mv |cp |sed |grep |cat |echo )'; then
            SCRIPT_TYPE="bash"
        else
            SCRIPT_TYPE="python"
        fi
    fi
fi

case "$SCRIPT_TYPE" in
    python) EXT="py" ;;
    bash)   EXT="sh" ;;
    *)
        error "Tipo inválido: $SCRIPT_TYPE (usa auto|python|bash)"
        exit 1
        ;;
esac

CLIPBOARD_FILE="$CLIPBOARD_BASE.$EXT"

# Guardar clipboard en archivo temporal
printf '%s\n' "$CLIPBOARD_CONTENT" > "$CLIPBOARD_FILE"
chmod +x "$CLIPBOARD_FILE" 2>/dev/null || true

log "Tipo detectado: $SCRIPT_TYPE"

# Validación de sintaxis
if [[ "$SCRIPT_TYPE" == "python" ]]; then
    if [[ "$VERBOSE" == true ]]; then
        log "Verificando sintaxis de Python..."
    fi

    if ! "$PYTHON_CMD" -m py_compile "$CLIPBOARD_FILE" 2>> "$LOG_FILE"; then
        error "El script no tiene sintaxis Python válida. Revisa el log."
        if [[ "$KEEP_FILE" == false ]]; then
            rm -f "$CLIPBOARD_FILE"
        fi
        exit 1
    fi
else
    if [[ "$VERBOSE" == true ]]; then
        log "Verificando sintaxis de Bash..."
    fi

    if ! bash -n "$CLIPBOARD_FILE" 2>> "$LOG_FILE"; then
        error "El script no tiene sintaxis Bash válida. Revisa el log."
        if [[ "$KEEP_FILE" == false ]]; then
            rm -f "$CLIPBOARD_FILE"
        fi
        exit 1
    fi
fi

# Mostrar información del script
SCRIPT_LINES=$(echo "$CLIPBOARD_CONTENT" | wc -l | tr -d ' ')
SCRIPT_SIZE=$(du -h "$CLIPBOARD_FILE" | cut -f1)

log "Script detectado: $SCRIPT_LINES líneas, $SCRIPT_SIZE"

if [[ "$VERBOSE" == true ]] || [[ "$DRY_RUN" == true ]]; then
    echo
    echo "--- INICIO DEL SCRIPT ---"
    echo "$CLIPBOARD_CONTENT"
    echo "--- FIN DEL SCRIPT ---"
    echo
fi

# Ejecutar o mostrar dry-run
if [[ "$DRY_RUN" == true ]]; then
    log "Dry-run: el script no fue ejecutado."
    log "Archivo temporal guardado en: $CLIPBOARD_FILE"
else
    if [[ "$SCRIPT_TYPE" == "python" ]]; then
        log "Ejecutando script (python) con: $PYTHON_CMD"
    else
        log "Ejecutando script (bash) con: bash"
    fi

    # Cambiar al directorio del proyecto para ejecutar
    cd "$PROJECT_ROOT"

    # Ejecutar y capturar salida
    if [[ "$SCRIPT_TYPE" == "python" ]]; then
        if "$PYTHON_CMD" "$CLIPBOARD_FILE" 2>&1 | tee -a "$LOG_FILE"; then
            success "Script ejecutado exitosamente."
            EXIT_CODE=0
        else
            error "Script falló con exit code: ${PIPESTATUS[0]}"
            EXIT_CODE=${PIPESTATUS[0]}
        fi
    else
        if bash "$CLIPBOARD_FILE" 2>&1 | tee -a "$LOG_FILE"; then
            success "Script ejecutado exitosamente."
            EXIT_CODE=0
        else
            error "Script falló con exit code: ${PIPESTATUS[0]}"
            EXIT_CODE=${PIPESTATUS[0]}
        fi
    fi

    # Limpiar archivo temporal si no se quiere mantener
    if [[ "$KEEP_FILE" == false ]]; then
        rm -f "$CLIPBOARD_FILE"
    else
        log "Archivo temporal mantenido en: $CLIPBOARD_FILE"
    fi

    log "Log completo guardado en: $LOG_FILE"
    exit $EXIT_CODE
fi