#!/bin/bash
# /usr/local/bin/sifen-fetch-secrets.sh
# Obtiene secretos desde SSM Parameter Store y genera /etc/sifen/sifen.env

set -euo pipefail

# Configuración
ENV_FILE="/etc/sifen/sifen.env"
ENV_FILE_TMP="/etc/sifen/sifen.env.tmp"
BACKUP_DIR="/etc/sifen/backups"
LOG_FILE="/var/log/sifen/fetch-secrets.log"

# Crear directorios necesarios
mkdir -p "$(dirname "$ENV_FILE")" "$BACKUP_DIR" "$(dirname "$LOG_FILE")"

# Función de logging
log() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $*" | tee -a "$LOG_FILE"
}

# Función para obtener parámetro SSM
get_ssm_param() {
    local param_name="$1"
    local is_secure="${2:-false}"
    
    if [ "$is_secure" = "true" ]; then
        aws ssm get-parameter \
            --name "$param_name" \
            --with-decryption \
            --query 'Parameter.Value' \
            --output text 2>/dev/null || {
            log "ERROR: No se pudo obtener parámetro seguro: $param_name"
            return 1
        }
    else
        aws ssm get-parameter \
            --name "$param_name" \
            --query 'Parameter.Value' \
            --output text 2>/dev/null || {
            log "ERROR: No se pudo obtener parámetro: $param_name"
            return 1
        }
    fi
}

# Verificar AWS CLI
if ! command -v aws &> /dev/null; then
    log "ERROR: AWS CLI no está instalado"
    exit 1
fi

# Verificar credenciales AWS
if ! aws sts get-caller-identity &> /dev/null; then
    log "ERROR: No se pueden verificar credenciales AWS"
    exit 1
fi

log "Iniciando obtención de secretos desde SSM"

# Backup del archivo anterior si existe
if [ -f "$ENV_FILE" ]; then
    cp "$ENV_FILE" "$BACKUP_DIR/sifen.env.$(date +%Y%m%d_%H%M%S).bak"
    log "Backup creado: $BACKUP_DIR/sifen.env.$(date +%Y%m%d_%H%M%S).bak"
fi

# Crear archivo temporal
cat > "$ENV_FILE_TMP" << 'EOF'
# Archivo de entorno generado automáticamente por sifen-fetch-secrets.sh
# NO EDITAR MANUALMENTE - Se sobrescribe en cada ejecución
# Generado: $(date)
EOF

# Obtener ambiente (default: prod)
SIFEN_ENV=$(get_ssm_param "/sifen/ENV" || echo "prod")
echo "SIFEN_ENV=$SIFEN_ENV" >> "$ENV_FILE_TMP"

# Obtener credenciales SIFEN
SIFEN_IDCSC=$(get_ssm_param "/sifen/$SIFEN_ENV/SIFEN_IDCSC")
SIFEN_CSC=$(get_ssm_param "/sifen/$SIFEN_ENV/SIFEN_CSC" "true")

if [ -n "$SIFEN_IDCSC" ] && [ -n "$SIFEN_CSC" ]; then
    echo "SIFEN_IDCSC=$SIFEN_IDCSC" >> "$ENV_FILE_TMP"
    echo "SIFEN_CSC=$SIFEN_CSC" >> "$ENV_FILE_TMP"
    log "Credenciales SIFEN obtenidas para ambiente: $SIFEN_ENV"
else
    log "ERROR: No se pudieron obtener credenciales SIFEN"
    rm -f "$ENV_FILE_TMP"
    exit 1
fi

# Obtener credenciales de administración web
ADMIN_USER=$(get_ssm_param "/sifen/$SIFEN_ENV/ADMIN_USER")
ADMIN_PASS=$(get_ssm_param "/sifen/$SIFEN_ENV/ADMIN_PASS" "true")

if [ -n "$ADMIN_USER" ] && [ -n "$ADMIN_PASS" ]; then
    echo "ADMIN_USER=$ADMIN_USER" >> "$ENV_FILE_TMP"
    echo "ADMIN_PASS=$ADMIN_PASS" >> "$ENV_FILE_TMP"
    log "Credenciales de administración obtenidas"
else
    log "ERROR: No se pudieron obtener credenciales de administración"
    rm -f "$ENV_FILE_TMP"
    exit 1
fi

# Obtener credenciales de SOAP (si existen)
SOAP_USER=$(get_ssm_param "/sifen/$SIFEN_ENV/SOAP_USER" || true)
SOAP_PASS=$(get_ssm_param "/sifen/$SIFEN_ENV/SOAP_PASS" "true" || true)

if [ -n "$SOAP_USER" ] && [ -n "$SOAP_PASS" ]; then
    echo "SOAP_USER=$SOAP_USER" >> "$ENV_FILE_TMP"
    echo "SOAP_PASS=$SOAP_PASS" >> "$ENV_FILE_TMP"
    log "Credenciales SOAP obtenidas"
else
    echo "# SOAP credentials no configuradas" >> "$ENV_FILE_TMP"
    log "WARNING: Credenciales SOAP no encontradas"
fi

# Obtener configuración adicional
SIFEN_EMISOR_RUC=$(get_ssm_param "/sifen/$SIFEN_ENV/SIFEN_EMISOR_RUC" || true)
if [ -n "$SIFEN_EMISOR_RUC" ]; then
    echo "SIFEN_EMISOR_RUC=$SIFEN_EMISOR_RUC" >> "$ENV_FILE_TMP"
    log "RUC emisor configurado: $SIFEN_EMISOR_RUC"
fi

# Obtener configuración de dominio
SIFEN_DOMAIN=$(get_ssm_param "/sifen/$SIFEN_ENV/SIFEN_DOMAIN" || true)
if [ -n "$SIFEN_DOMAIN" ]; then
    echo "SIFEN_DOMAIN=$SIFEN_DOMAIN" >> "$ENV_FILE_TMP"
    log "Dominio configurado: $SIFEN_DOMAIN"
fi

# Mover archivo temporal a producción
mv "$ENV_FILE_TMP" "$ENV_FILE"
chmod 600 "$ENV_FILE"
chown sifen:sifen "$ENV_FILE"

log "Secretos obtenidos exitosamente"
log "Archivo generado: $ENV_FILE (permisos: 600)"

# Recargar servicio si está corriendo
if systemctl is-active --quiet sifen-web; then
    log "Recargando servicio sifen-web"
    systemctl reload sifen-web || {
        log "WARNING: No se pudo recargar sifen-web, intentando restart"
        systemctl restart sifen-web
    }
fi

log "Proceso completado exitosamente"
