#!/usr/bin/env bash
# Backup automático de SQLite con cifrado AES-256-CBC PBKDF2
# Uso: DB_PATH="..." OUT_DIR="..." PASSPHRASE_FILE="..." ./backup_sqlite.sh

set -euo pipefail

# Variables de entorno requeridas (con defaults para desarrollo)
DB_PATH="${DB_PATH:-}"
OUT_DIR="${OUT_DIR:-$HOME/backups/app}"
PASSPHRASE_FILE="${PASSPHRASE_FILE:-$HOME/secrets/backup_passphrase.txt}"

# Validar variables requeridas
if [[ -z "$DB_PATH" ]]; then
    echo "ERROR: DB_PATH no está configurado" >&2
    exit 1
fi

if [[ ! -f "$DB_PATH" ]]; then
    echo "ERROR: Base de datos no encontrada: $DB_PATH" >&2
    exit 1
fi

if [[ ! -f "$PASSPHRASE_FILE" ]]; then
    echo "ERROR: Archivo de passphrase no encontrado: $PASSPHRASE_FILE" >&2
    exit 1
fi

# Crear directorio de salida si no existe
mkdir -p "$OUT_DIR"

# Timestamp para nombres únicos
ts="$(date +%Y%m%d_%H%M%S)"
db_basename="$(basename "$DB_PATH" .db)"
tmp_backup="${OUT_DIR}/${db_basename}_${ts}.bak"
archive="${OUT_DIR}/${db_basename}_${ts}.bak.gz"
encrypted="${OUT_DIR}/${db_basename}_${ts}.bak.gz.enc"

# Logging básico (sin exponer secretos)
log_file="${OUT_DIR}/backup.log"
err_file="${OUT_DIR}/backup.err"

log() {
    echo "[$(date +'%Y-%m-%d %H:%M:%S')] $*" >> "$log_file"
}

log_err() {
    echo "[$(date +'%Y-%m-%d %H:%M:%S')] ERROR: $*" | tee -a "$err_file" >&2
}

# Iniciar backup
log "Iniciando backup de: $(basename "$DB_PATH")"

# 1. Crear backup de SQLite
if ! sqlite3 "$DB_PATH" ".backup '${tmp_backup}'" 2>>"$err_file"; then
    log_err "Falló el backup SQLite"
    rm -f "$tmp_backup"
    exit 1
fi

# 2. Comprimir
if ! gzip -c "$tmp_backup" > "$archive" 2>>"$err_file"; then
    log_err "Falló la compresión"
    rm -f "$tmp_backup" "$archive"
    exit 1
fi

# 3. Cifrar con OpenSSL AES-256-CBC PBKDF2
if ! openssl enc -aes-256-cbc -pbkdf2 -salt \
    -pass "file:${PASSPHRASE_FILE}" \
    -in "$archive" -out "$encrypted" 2>>"$err_file"; then
    log_err "Falló el cifrado"
    rm -f "$tmp_backup" "$archive" "$encrypted"
    exit 1
fi

# 4. Limpiar archivos temporales
rm -f "$tmp_backup" "$archive"

# 5. Obtener tamaño del archivo cifrado (para logging)
encrypted_size=$(stat -f%z "$encrypted" 2>/dev/null || stat -c%s "$encrypted" 2>/dev/null || echo "unknown")

log "Backup generado exitosamente: $(basename "$encrypted") (${encrypted_size} bytes)"

# 6. Rotación: eliminar backups más antiguos de 30 días
log "Iniciando rotación de backups (mantener últimos 30 días)"
deleted_count=0
while IFS= read -r old_file; do
    if [[ -f "$old_file" ]]; then
        rm -f "$old_file"
        deleted_count=$((deleted_count + 1))
        log "Eliminado backup antiguo: $(basename "$old_file")"
    fi
done < <(find "$OUT_DIR" -name "*.enc" -type f -mtime +30 2>/dev/null || true)

if [[ $deleted_count -gt 0 ]]; then
    log "Rotación completada: $deleted_count archivo(s) eliminado(s)"
else
    log "Rotación completada: no se eliminaron archivos"
fi

log "Backup finalizado exitosamente"
exit 0
