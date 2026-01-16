#!/bin/bash
# /usr/local/bin/sifen-backup.sh
# Backup robusto para SIFEN con SQLite consistente

set -euo pipefail

# Configuración
DATE=$(date +%Y%m%d_%H%M%S)
BACKUP_DIR="/home/sifen/backups"
BACKUP_DATE_DIR="$BACKUP_DIR/$DATE"
S3_BUCKET="sifen-backup"
LOG_FILE="/var/log/sifen/backup.log"
RETENTION_DAYS=30

# Directorios de origen
APP_DIR="/home/sifen/app/tesaka-cv"
DB_FILE="$APP_DIR/tesaka.db"
CERTS_DIR="/home/sifen/certs"
ARTIFACTS_DIR="/home/sifen/artifacts"
LOGS_DIR="/var/log/sifen"

# Función de logging
log() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $*" | tee -a "$LOG_FILE"
}

# Función para verificar espacio disponible
check_space() {
    local required_mb="$1"
    local available_mb
    available_mb=$(df "$BACKUP_DIR" | awk 'NR==2 {print int($4/1024)}')
    
    if [ "$available_mb" -lt "$required_mb" ]; then
        log "ERROR: Espacio insuficiente. Requerido: ${required_mb}MB, Disponible: ${available_mb}MB"
        exit 1
    fi
}

# Función para backup SQLite consistente
backup_sqlite() {
    local src_db="$1"
    local dst_db="$2"
    
    log "Iniciando backup SQLite consistente"
    
    # Verificar que la base de datos no esté bloqueada
    if ! sqlite3 "$src_db" "PRAGMA busy_timeout = 5000; SELECT 1;" >/dev/null 2>&1; then
        log "ERROR: Base de datos bloqueada o inaccesible"
        return 1
    fi
    
    # Backup usando el comando .backup (más seguro que cp)
    if sqlite3 "$src_db" ".backup '$dst_db'"; then
        log "Backup SQLite completado: $dst_db"
        
        # Verificar integridad del backup
        if sqlite3 "$dst_db" "PRAGMA integrity_check;" | grep -q "ok"; then
            log "Integridad del backup verificada"
            return 0
        else
            log "ERROR: Backup SQLite falló verificación de integridad"
            rm -f "$dst_db"
            return 1
        fi
    else
        log "ERROR: Falló comando .backup de SQLite"
        return 1
    fi
}

# Función para subir a S3 con verificación
upload_to_s3() {
    local local_path="$1"
    local s3_path="$2"
    
    log "Subiendo a S3: $local_path -> s3://$S3_BUCKET/$s3_path"
    
    # Subir con multipart para archivos grandes
    if aws s3 cp "$local_path" "s3://$S3_BUCKET/$s3_path" --storage-class STANDARD_IA; then
        log "Upload exitoso"
        
        # Verificar con checksum
        local local_md5
        local s3_md5
        local_md5=$(md5sum "$local_path" | cut -d' ' -f1)
        s3_md5=$(aws s3api head-object --bucket "$S3_BUCKET" --key "$s3_path" --query 'ETag' --output text | tr -d '"')
        
        if [ "$local_md5" = "$s3_md5" ]; then
            log "Checksum verificado: $local_md5"
            return 0
        else
            log "ERROR: Checksum mismatch. Local: $local_md5, S3: $s3_md5"
            return 1
        fi
    else
        log "ERROR: Falló upload a S3"
        return 1
    fi
}

# Función para cleanup local
cleanup_local() {
    log "Iniciando cleanup local (retención: $RETENTION_DAYS días)"
    
    # Eliminar directorios antiguos
    find "$BACKUP_DIR" -type d -name "????????_??????" -mtime +$RETENTION_DAYS -exec rm -rf {} \; 2>/dev/null || true
    
    # Eliminar logs antiguos
    find "$LOGS_DIR" -name "*.log" -mtime +7 -delete 2>/dev/null || true
    
    # Reportar espacio liberado
    local backups_count
    backups_count=$(find "$BACKUP_DIR" -type d -name "????????_??????" | wc -l)
    local backups_size
    backups_size=$(du -sh "$BACKUP_DIR" | cut -f1)
    
    log "Cleanup completado. Backups locales: $backups_count, Tamaño: $backups_size"
}

# Función para cleanup S3
cleanup_s3() {
    log "Iniciando cleanup S3 (retención: $RETENTION_DAYS días)"
    
    # Calcular fecha límite
    local cutoff_date
    cutoff_date=$(date -d "$RETENTION_DAYS days ago" +%Y%m%d)
    
    # Eliminar objetos antiguos
    aws s3api list-objects-v2 \
        --bucket "$S3_BUCKET" \
        --prefix "daily/" \
        --query "Contents[?LastModified<='$(date -d "$RETENTION_DAYS days ago" --iso-8601)'].Key" \
        --output text |
    while read -r key; do
        if [ -n "$key" ] && [ "$key" != "None" ]; then
            aws s3 rm "s3://$S3_BUCKET/$key"
            log "Eliminado de S3: $key"
        fi
    done
}

# Inicio del backup
log "=== INICIANDO BACKUP SIFEN ==="
log "Fecha: $DATE"
log "Directorio: $BACKUP_DATE_DIR"

# Verificar prerequisitos
if [ ! -f "$DB_FILE" ]; then
    log "ERROR: Base de datos no encontrada: $DB_FILE"
    exit 1
fi

if ! command -v aws &> /dev/null; then
    log "ERROR: AWS CLI no está instalado"
    exit 1
fi

# Verificar credenciales AWS
if ! aws sts get-caller-identity &> /dev/null; then
    log "ERROR: No se pueden verificar credenciales AWS"
    exit 1
fi

# Crear directorio de backup
mkdir -p "$BACKUP_DATE_DIR"

# Verificar espacio (requerir al menos 1GB)
check_space 1024

# Backup 1: Base de datos SQLite
DB_BACKUP="$BACKUP_DATE_DIR/tesaka.db"
if backup_sqlite "$DB_FILE" "$DB_BACKUP"; then
    upload_to_s3 "$DB_BACKUP" "daily/$DATE/tesaka.db"
else
    log "ERROR: Falló backup de base de datos"
    exit 1
fi

# Backup 2: Certificados (si existen)
if [ -d "$CERTS_DIR" ] && [ "$(ls -A "$CERTS_DIR" 2>/dev/null)" ]; then
    CERTS_BACKUP="$BACKUP_DATE_DIR/certs.tar.gz"
    tar -czf "$CERTS_BACKUP" -C "$(dirname "$CERTS_DIR")" "$(basename "$CERTS_DIR")"
    upload_to_s3 "$CERTS_BACKUP" "daily/$DATE/certs.tar.gz"
    log "Certificados backup completado"
else
    log "WARNING: Directorio de certificados vacío o no existe"
fi

# Backup 3: Artifacts recientes (últimos 7 días)
if [ -d "$ARTIFACTS_DIR" ] && [ "$(ls -A "$ARTIFACTS_DIR" 2>/dev/null)" ]; then
    ARTIFACTS_BACKUP="$BACKUP_DATE_DIR/artifacts_recent.tar.gz"
    find "$ARTIFACTS_DIR" -type f -mtime -7 -print0 | tar -czf "$ARTIFACTS_BACKUP" --null -T -
    upload_to_s3 "$ARTIFACTS_BACKUP" "daily/$DATE/artifacts_recent.tar.gz"
    log "Artifacts recientes backup completado"
else
    log "WARNING: Directorio de artifacts vacío o no existe"
fi

# Backup 4: Logs recientes (últimos 3 días)
if [ -d "$LOGS_DIR" ] && [ "$(ls -A "$LOGS_DIR" 2>/dev/null)" ]; then
    LOGS_BACKUP="$BACKUP_DATE_DIR/logs_recent.tar.gz"
    find "$LOGS_DIR" -type f -mtime -3 -name "*.log" -print0 | tar -czf "$LOGS_BACKUP" --null -T -
    upload_to_s3 "$LOGS_BACKUP" "daily/$DATE/logs_recent.tar.gz"
    log "Logs recientes backup completado"
else
    log "WARNING: Directorio de logs vacío o no existe"
fi

# Backup 5: Configuración importante
CONFIG_BACKUP="$BACKUP_DATE_DIR/config.tar.gz"
tar -czf "$CONFIG_BACKUP" \
    -C "$(dirname "$APP_DIR")" \
    --exclude="*.pyc" \
    --exclude="__pycache__" \
    --exclude=".git" \
    --exclude="artifacts" \
    --exclude="*.db" \
    "$(basename "$APP_DIR")/deploy" \
    "$(basename "$APP_DIR")/tools" \
    "$(basename "$APP_DIR")/web" \
    "$(basename "$APP_DIR")/requirements.txt" \
    "$(basename "$APP_DIR")/.env.example" 2>/dev/null || true

if [ -f "$CONFIG_BACKUP" ]; then
    upload_to_s3 "$CONFIG_BACKUP" "daily/$DATE/config.tar.gz"
    log "Configuración backup completada"
fi

# Backup 6: Metadata del backup
METADATA_FILE="$BACKUP_DATE_DIR/metadata.json"
cat > "$METADATA_FILE" << EOF
{
    "backup_date": "$DATE",
    "timestamp": "$(date -Iseconds)",
    "hostname": "$(hostname)",
    "db_size_bytes": $(stat -f%z "$DB_FILE" 2>/dev/null || stat -c%s "$DB_FILE" 2>/dev/null || echo "0"),
    "db_checksum": "$(md5sum "$DB_FILE" | cut -d' ' -f1)",
    "backups_created": [
        "tesaka.db",
        "certs.tar.gz",
        "artifacts_recent.tar.gz",
        "logs_recent.tar.gz",
        "config.tar.gz"
    ]
}
EOF

upload_to_s3 "$METADATA_FILE" "daily/$DATE/metadata.json"

# Cleanup local y S3
cleanup_local
cleanup_s3

# Reporte final
local_size=$(du -sh "$BACKUP_DATE_DIR" | cut -f1)
s3_size=$(aws s3 ls "s3://$S3_BUCKET/daily/$DATE/" --recursive --summarize --human-readable | tail -1 | awk '{print $1}')

log "=== BACKUP COMPLETADO EXITOSAMENTE ==="
log "Tamaño local: $local_size"
log "Tamaño S3: $s3_size"
log "Directorio: $BACKUP_DATE_DIR"
log "S3: s3://$S3_BUCKET/daily/$DATE/"

# Verificación final
if [ $? -eq 0 ]; then
    log "Backup verificado y completado exitosamente"
    exit 0
else
    log "ERROR: Backup completado con errores"
    exit 1
fi
