#!/bin/bash
# tools/prod_smoketest.sh
# Smoke test end-to-end para SIFEN en producción
# Genera XML → Firma → QR → Envía WS PROD

set -euo pipefail

# Configuración
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
SMOKE_DIR="$PROJECT_ROOT/artifacts/prod_smoketest/$TIMESTAMP"
LOG_FILE="$SMOKE_DIR/smoketest.log"

# Colores para output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Función de logging
log() {
    echo -e "${BLUE}[$(date '+%Y-%m-%d %H:%M:%S')]${NC} $*" | tee -a "$LOG_FILE"
}

log_error() {
    echo -e "${RED}[$(date '+%Y-%m-%d %H:%M:%S')] ERROR:${NC} $*" | tee -a "$LOG_FILE"
}

log_success() {
    echo -e "${GREEN}[$(date '+%Y-%m-%d %H:%M:%S')] SUCCESS:${NC} $*" | tee -a "$LOG_FILE"
}

log_warning() {
    echo -e "${YELLOW}[$(date '+%Y-%m-%d %H:%M:%S')] WARNING:${NC} $*" | tee -a "$LOG_FILE"
}

# Función para mostrar ayuda
show_help() {
    cat << EOF
SIFEN Production Smoke Test

Uso: $0 [opciones]

Opciones:
    --env-file FILE    Archivo .env con secretos de producción (default: busca en orden)
    --no-send         Genera XML pero no envía a SIFEN
    --dry-run         Solo muestra comandos que se ejecutarían
    --help            Muestra esta ayuda

El script:
1. Carga secretos desde archivo .env o SSM
2. Genera XML DE de prueba con datos reales
3. Firma XML y recalcula QR
4. Envía a SIFEN producción (si no se usa --no-send)
5. Guarda toda evidencia en artifacts/prod_smoketest/<timestamp>/

EOF
}

# Función para cargar secretos
load_secrets() {
    local env_file="$1"
    
    log "Cargando secretos de producción..."
    
    # Buscar archivo de entorno
    if [[ -n "$env_file" ]]; then
        if [[ ! -f "$env_file" ]]; then
            log_error "Archivo de entorno no encontrado: $env_file"
            exit 1
        fi
        log "Usando archivo de entorno: $env_file"
    else
        # Buscar en orden
        for loc in "/etc/sifen/sifen.env" "$HOME/.sifen.env" "$PROJECT_ROOT/.env.prod" "$PROJECT_ROOT/.env"; do
            if [[ -f "$loc" ]]; then
                env_file="$loc"
                log "Archivo de entorno encontrado: $loc"
                break
            fi
        done
        
        if [[ -z "$env_file" ]]; then
            log_error "No se encontró archivo de entorno. Buscando en:"
            log_error "  - /etc/sifen/sifen.env"
            log_error "  - ~/.sifen.env"
            log_error "  - .env.prod"
            log_error "  - .env"
            exit 1
        fi
    fi
    
    # Cargar variables (con export para subprocesos)
    set -a
    source "$env_file"
    set +a
    
    # Validar variables críticas
    local required_vars=("SIFEN_ENV" "SIFEN_IDCSC_PROD" "SIFEN_CSC_PROD" "SIFEN_EMISOR_RUC")
    local missing_vars=()
    
    for var in "${required_vars[@]}"; do
        if [[ -z "${!var:-}" ]]; then
            missing_vars+=("$var")
        fi
    done
    
    if [[ ${#missing_vars[@]} -gt 0 ]]; then
        log_error "Faltan variables requeridas:"
        for var in "${missing_vars[@]}"; do
            log_error "  - $var"
        done
        exit 1
    fi
    
    # Validar ambiente
    if [[ "$SIFEN_ENV" != "prod" ]]; then
        log_error "Ambiente incorrecto: SIFEN_ENV=$SIFEN_ENV (debe ser 'prod')"
        exit 1
    fi
    
    # Ocultar CSC en logs
    log "Secretos cargados:"
    log "  - Ambiente: ${SIFEN_ENV}"
    log "  - IdCSC: ${SIFEN_IDCSC_PROD}"
    log "  - CSC: ***$(echo "${SIFEN_CSC_PROD}" | tail -c 5)"
    log "  - Emisor RUC: ${SIFEN_EMISOR_RUC}"
    
    # Validar certificado
    if [[ -n "${SIFEN_CERT_PATH:-}" ]]; then
        if [[ ! -f "$SIFEN_CERT_PATH" ]]; then
            log_error "Certificado no encontrado: SIFEN_CERT_PATH=$SIFEN_CERT_PATH"
            exit 1
        fi
        log "  - Certificado: $SIFEN_CERT_PATH"
    fi
}

# Función para generar XML de prueba
generate_xml() {
    log "Generando XML DE de prueba para producción..."
    
    # Crear JSON de prueba temporal
    local test_json="$SMOKE_DIR/test_de.json"
    
    # Extraer RUC y DV
    local ruc="${SIFEN_EMISOR_RUC%-*}"
    local dv="${SIFEN_EMISOR_RUC##*-}"
    
    # Usar timbrado de producción si está definido
    local timbrado="${SIFEN_TIMBRADO_PROD:-18578288}"
    
    # Generar número de documento único (timestamp)
  local _hms=$(date +%H%M%S)
  local _bump=${DOC_BUMP:-0}
  local doc_num=$(printf "%06d" $((10#$_hms + ($_bump % 1000000))))
    
    cat > "$test_json" << EOF
{
  "emisor": {
    "ruc": "$ruc",
    "dv": "$dv",
    "razon_social": "MARCIO RUBEN FERIS AGUILERA",
    "direccion": "LAMBARE",
    "numero_casa": "1234",
    "departamento": "12",
    "ciudad": "6106",
    "telefono": "0971 123456",
    "email": "info@empresa.com.py",
    "actividad_economica": {
      "codigo": "46103",
      "descripcion": "COMERCIO AL POR MAYOR DE ALIMENTOS, BEBIDAS Y TABACO"
    }
  },
  "timbrado": {
    "numero": "$timbrado",
    "establecimiento": "001",
    "punto_expedicion": "001",
    "tipo_documento": "1",
    "numero_documento": "$doc_num"
  },
  "receptor": {
    "tipo_naturaleza": "1",
    "tipo_operacion": "1",
    "pais": "PRY",
    "pais_descripcion": "Paraguay",
    "ruc": "1234567",
    "dv": "9",
    "nombre": "CLIENTE SMOKE TEST SA",
    "direccion": "ASUNCION",
    "numero_casa": "999",
    "departamento": "12",
    "departamento_descripcion": "CENTRAL",
    "ciudad": "1",
    "ciudad_descripcion": "Asunción"
  },
  "condicion_operacion": {
    "codigo": "1",
    "descripcion": "Contado"
  },
  "tipo_contado": {
    "codigo": "1",
    "descripcion": "Efectivo"
  },
  "items": [
    {
      "codigo": "SMOKE001",
      "descripcion": "SERVICIO DE SMOKE TEST SIFEN",
      "unidad_medida": "77",
      "unidad_medida_descripcion": "UNI",
      "cantidad": 1.0,
      "precio_unitario": 100000,
      "tasa_iva": 10
    }
  ],
  "fecha_emision": "$(date +%Y-%m-%d)",
  "hora_emision": "$(date +%H:%M:%S)"
}
EOF
    
    log "JSON de prueba creado: $test_json"
    
    # Generar XML usando wrapper
    local xml_output="$SMOKE_DIR/de_final.xml"
    local temp_xml="$SMOKE_DIR/smoke_de.xml"
    
    if [[ "$DRY_RUN" == "1" ]]; then
        log "[DRY-RUN] Ejecutaría:"
        log "  export PYTHONPATH=."
export TMP_XML="$OUT_DIR/smoke_de.xml"
        TMP_XML="$OUT_DIR/smoke_de.xml" log "  ./tools/make_de_wrapper.sh --env prod --env-file $env_file"
        log "    --gen '.venv/bin/python tools/generar_prevalidador.py --json $test_json --out $temp_xml'"
        log "    --sign 'echo \"Firma ya incluida en generador\"'"
        log "    --out '$xml_output'"
        return 0
    fi
    
    log "Ejecutando wrapper para generar XML..."
    
    # Exportar PYTHONPATH para todos los comandos
    export PYTHONPATH="."
    
    if ./tools/make_de_wrapper.sh \
        --env prod \
        --env-file "$env_file" \
        --gen ".venv/bin/python tools/generar_prevalidador.py --json $test_json --out $temp_xml" \
        --sign "echo 'Firma ya incluida en generador'" \
        --out "$xml_output" 2>&1 | tee -a "$LOG_FILE"; then
        
        log_success "XML generado exitosamente"
        
        # Verificar que existe
        if [[ ! -f "$xml_output" ]]; then
            log_error "XML no encontrado en salida esperada: $xml_output"
            exit 1
        fi
        
        # Extraer metadata
        local cdc=$(grep -o 'Id="[^"]*"' "$xml_output" | head -1 | cut -d'"' -f2)
        local total=$(grep -o '<dTotGralOpe>[^<]*' "$xml_output" | head -1 | sed 's/<dTotGralOpe>//' | sed 's/\.00000000//')
        local receptor=$(grep -o '<dNomRec>[^<]*' "$xml_output" | head -1 | sed 's/<dNomRec>//')
        
        # Guardar metadata
        cat > "$SMOKE_DIR/metadata.json" << EOF
{
  "timestamp": "$(date -Iseconds)",
  "cdc": "$cdc",
  "emisor": {
    "ruc": "$SIFEN_EMISOR_RUC",
    "timbrado": "$timbrado"
  },
  "receptor": {
    "nombre": "$receptor"
  },
  "totales": {
    "total": "$total"
  },
  "xml_file": "de_final.xml"
}
EOF
        
        log "Metadata guardada:"
        log "  - CDC: $cdc"
        log "  - Total: Gs. $total"
        log "  - Receptor: $receptor"
        
    else
        log_error "Falló generación de XML"
        exit 1
    fi
}

# Función para enviar a SIFEN
send_to_sifen() {
    if [[ "$NO_SEND" == "1" ]]; then
        log_warning "--no-send especificado, omitiendo envío a SIFEN"
        return 0
    fi
    
    if [[ "$DRY_RUN" == "1" ]]; then
        log "[DRY-RUN] Ejecutaría:"
        log "  python -m tools.send_sirecepde --env prod --xml $SMOKE_DIR/de_final.xml"
        return 0
    fi
    
    log "Enviando XML a SIFEN producción..."
    
    # Enviar usando send_sirecepde
    if .venv/bin/python -m tools.send_sirecepde \
        --env prod \
        --xml "$SMOKE_DIR/de_final.xml" 2>&1 | tee -a "$LOG_FILE"; then
        
        log_success "Envío a SIFEN completado"
        
        # Buscar archivos de respuesta
        local artifacts_dir="$PROJECT_ROOT/artifacts"
        local latest_response=$(find "$artifacts_dir" -name "soap_last_response_RECV.xml" -type f -mmin -5 | head -1)
        
        if [[ -n "$latest_response" ]]; then
            cp "$latest_response" "$SMOKE_DIR/soap_response.xml"
            log "Respuesta SOAP guardada: soap_response.xml"
            
            # Extraer resultado
            local cod_res=$(grep -o '<dCodRes>[^<]*' "$SMOKE_DIR/soap_response.xml" | head -1 | sed 's/<dCodRes>//' || echo "N/A")
            local msg_res=$(grep -o '<dMsgRes>[^<]*' "$SMOKE_DIR/soap_response.xml" | head -1 | sed 's/<dMsgRes>//' || echo "N/A")
            
            # Actualizar metadata con resultado
            local temp_metadata=$(mktemp)
            jq ". += {
                \"envio\": {
                    \"codigo_respuesta\": \"$cod_res\",
                    \"mensaje_respuesta\": \"$msg_res\",
                    \"timestamp\": \"$(date -Iseconds)\"
                }
            }" "$SMOKE_DIR/metadata.json" > "$temp_metadata"
            mv "$temp_metadata" "$SMOKE_DIR/metadata.json"
            
            log "Resultado del envío:"
            log "  - Código: $cod_res"
            log "  - Mensaje: $msg_res"
            
            # Verificar si fue aprobado
            case "$cod_res" in
                "01"|"001")
                    log_success "✅ DE APROBADO/ACEPTADO por SIFEN"
                    ;;
                "02"|"002")
                    log_warning "⚠️  DE RECHAZADO por SIFEN"
                    ;;
                "03"|"003")
                    log_warning "⚠️  DE OBSERVADO por SIFEN"
                    ;;
                *)
                    log_warning "Código de respuesta desconocido: $cod_res"
                    ;;
            esac
            
        else
            log_warning "No se encontró respuesta SOAP reciente"
        fi
        
        # Copiar request enviado
        local latest_request=$(find "$artifacts_dir" -name "soap_last_request_SENT.xml" -type f -mmin -5 | head -1)
        if [[ -n "$latest_request" ]]; then
            cp "$latest_request" "$SMOKE_DIR/soap_request.xml"
            log "Request SOAP guardado: soap_request.xml"
        fi
        
    else
        log_error "Falló envío a SIFEN"
        exit 1
    fi
}

# Función principal
main() {
    local env_file=""
    DRY_RUN="0"
    NO_SEND="0"
    
    # Parse argumentos
    while [[ $# -gt 0 ]]; do
        case $1 in
            --env-file)
                env_file="$2"
                shift 2
                ;;
            --no-send)
                NO_SEND="1"
                shift
                ;;
            --dry-run)
                DRY_RUN="1"
                shift
                ;;
            --help)
                show_help
                exit 0
                ;;
            *)
                log_error "Opción desconocida: $1"
                show_help
                exit 1
                ;;
        esac
    done
    
    # Header
    echo -e "${BLUE}"
    echo "=================================="
    echo "  SIFEN PRODUCTION SMOKE TEST"
    echo "=================================="
    echo -e "${NC}"
    
    # Crear directorio de salida
    mkdir -p "$SMOKE_DIR"
    log "Directorio de salida: $SMOKE_DIR"
    
    # Ejecutar flujo
    load_secrets "$env_file"
    generate_xml
    send_to_sifen
    
    # Resumen final
    echo -e "${GREEN}"
    echo "=================================="
    echo "  SMOKE TEST COMPLETADO"
    echo "=================================="
    echo -e "${NC}"
    
    log "Archivos generados:"
    ls -la "$SMOKE_DIR" | tee -a "$LOG_FILE"
    
    log "Revisar resultados en: $SMOKE_DIR"
    
    # Mostrar resultado final
    if [[ -f "$SMOKE_DIR/metadata.json" ]]; then
        echo -e "\n${BLUE}Resumen:${NC}"
        jq -r '"- CDC: " + .cdc + "\n" +
              "- Emisor: " + .emisor.ruc + "\n" +
              "- Receptor: " + .receptor.nombre + "\n" +
              "- Total: Gs. " + .totales.total' "$SMOKE_DIR/metadata.json"
        
        if jq -e '.envio' "$SMOKE_DIR/metadata.json" >/dev/null 2>&1; then
            echo -e "\n${BLUE}Envío SIFEN:${NC}"
            jq -r '"- Código: " + .envio.codigo_respuesta + "\n" +
                  "- Mensaje: " + .envio.mensaje_respuesta' "$SMOKE_DIR/metadata.json"
        fi
    fi
}

# Ejecutar main
main "$@"
