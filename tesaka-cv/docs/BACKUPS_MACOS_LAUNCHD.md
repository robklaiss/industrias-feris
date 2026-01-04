# Backup Automático SQLite con launchd (macOS)

Este documento describe cómo configurar backups automáticos diarios de la base de datos SQLite usando `launchd` en macOS.

## Requisitos Previos

1. **Script de backup**: `~/backup_sqlite.sh` debe existir y ser ejecutable
2. **Passphrase**: Archivo `~/secrets/backup_passphrase.txt` con permisos 600
3. **Directorio de backups**: `~/backups/app` (se crea automáticamente)

## Estructura de Archivos

```
~/
├── backup_sqlite.sh                    # Script de backup (ejecutable)
├── secrets/
│   └── backup_passphrase.txt          # Passphrase para cifrado (permisos 600)
└── backups/
    └── app/                            # Directorio de backups
        ├── backup.log                  # Log de stdout
        ├── backup.err                  # Log de stderr
        └── tesaka_YYYYMMDD_HHMMSS.bak.gz.enc  # Backups cifrados
```

## Configuración

### 1. Preparar el Script de Backup

El script `backup_sqlite.sh` debe estar en `$HOME` y ser ejecutable:

```bash
chmod +x ~/backup_sqlite.sh
```

### 2. Crear el Archivo de Passphrase

```bash
mkdir -p ~/secrets
echo "tu-passphrase-segura-aqui" > ~/secrets/backup_passphrase.txt
chmod 600 ~/secrets/backup_passphrase.txt
```

**⚠️ IMPORTANTE**: Guarda la passphrase en un lugar seguro. Sin ella, no podrás restaurar los backups.

### 3. Configurar el LaunchAgent

#### 3.1. Editar el plist Template

Copia el template desde el repositorio:

```bash
cp tesaka-cv/scripts/com.industriasferis.sqlitebackup.plist \
   ~/Library/LaunchAgents/com.industriasferis.sqlitebackup.plist
```

#### 3.2. Personalizar la Ruta de la Base de Datos

Edita `~/Library/LaunchAgents/com.industriasferis.sqlitebackup.plist` y actualiza:

1. **DB_PATH**: Ruta completa a tu base de datos SQLite
   ```xml
   <string>DB_PATH="/ruta/completa/a/tesaka.db" OUT_DIR="$HOME/backups/app" PASSPHRASE_FILE="$HOME/secrets/backup_passphrase.txt" "$HOME/backup_sqlite.sh"</string>
   ```

2. **StandardOutPath** y **StandardErrorPath**: Asegúrate de que apunten a `$HOME/backups/app/`
   ```xml
   <key>StandardOutPath</key>
   <string>/Users/TU_USUARIO/backups/app/backup.log</string>
   
   <key>StandardErrorPath</key>
   <string>/Users/TU_USUARIO/backups/app/backup.err</string>
   ```

**Ejemplo completo** (reemplazar `TU_USUARIO` con tu usuario real):

```xml
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.industriasferis.sqlitebackup</string>
    
    <key>ProgramArguments</key>
    <array>
        <string>/bin/zsh</string>
        <string>-lc</string>
        <string>DB_PATH="/Users/TU_USUARIO/Dev/industrias-feris-facturacion-electronica-simplificado/tesaka-cv/tesaka.db" OUT_DIR="$HOME/backups/app" PASSPHRASE_FILE="$HOME/secrets/backup_passphrase.txt" "$HOME/backup_sqlite.sh"</string>
    </array>
    
    <key>StartCalendarInterval</key>
    <dict>
        <key>Hour</key>
        <integer>2</integer>
        <key>Minute</key>
        <integer>15</integer>
    </dict>
    
    <key>StandardOutPath</key>
    <string>/Users/TU_USUARIO/backups/app/backup.log</string>
    
    <key>StandardErrorPath</key>
    <string>/Users/TU_USUARIO/backups/app/backup.err</string>
    
    <key>RunAtLoad</key>
    <false/>
    
    <key>KeepAlive</key>
    <false/>
</dict>
</plist>
```

### 4. Cargar el LaunchAgent

```bash
# Desactivar si ya estaba cargado (ignorar error si no existe)
launchctl unload ~/Library/LaunchAgents/com.industriasferis.sqlitebackup.plist 2>/dev/null || true

# Cargar el nuevo plist
launchctl load ~/Library/LaunchAgents/com.industriasferis.sqlitebackup.plist

# Iniciar manualmente (opcional, para probar)
launchctl start com.industriasferis.sqlitebackup
```

### 5. Verificar que Está Funcionando

```bash
# Ver el estado
launchctl list | grep sqlitebackup

# Ver los logs
tail -f ~/backups/app/backup.log
tail -f ~/backups/app/backup.err

# Verificar que se creó un backup
ls -lh ~/backups/app/*.enc
```

## Comandos Útiles

### Recargar después de cambios

```bash
launchctl unload ~/Library/LaunchAgents/com.industriasferis.sqlitebackup.plist
launchctl load ~/Library/LaunchAgents/com.industriasferis.sqlitebackup.plist
```

### Detener el servicio

```bash
launchctl stop com.industriasferis.sqlitebackup
```

### Iniciar manualmente

```bash
launchctl start com.industriasferis.sqlitebackup
```

### Ver logs en tiempo real

```bash
# Logs de éxito
tail -f ~/backups/app/backup.log

# Logs de errores
tail -f ~/backups/app/backup.err
```

### Desactivar completamente

```bash
launchctl unload ~/Library/LaunchAgents/com.industriasferis.sqlitebackup.plist
rm ~/Library/LaunchAgents/com.industriasferis.sqlitebackup.plist
```

## Características del Script de Backup

### Rotación Automática

El script elimina automáticamente backups más antiguos de 30 días. Esto se hace al final de cada ejecución usando:

```bash
find "$OUT_DIR" -name "*.enc" -type f -mtime +30 -delete
```

### Cifrado

Los backups se cifran con:
- **Algoritmo**: AES-256-CBC
- **Derivación de clave**: PBKDF2
- **Passphrase**: Leída desde `$HOME/secrets/backup_passphrase.txt`

### Logging

- **backup.log**: Logs de operaciones exitosas (sin exponer secretos)
- **backup.err**: Errores y warnings

Los logs incluyen:
- Timestamp de cada operación
- Nombre del archivo generado (sin ruta completa)
- Tamaño del backup
- Resultado de la rotación

**⚠️ IMPORTANTE**: Los logs NO incluyen:
- Passphrase
- Rutas completas sensibles
- Contenido de archivos

## Restaurar un Backup

Para restaurar un backup cifrado:

```bash
# 1. Desencriptar
openssl enc -d -aes-256-cbc -pbkdf2 \
  -pass "file:$HOME/secrets/backup_passphrase.txt" \
  -in ~/backups/app/tesaka_20250127_021500.bak.gz.enc \
  -out restore.bak.gz

# 2. Descomprimir
gunzip restore.bak.gz

# 3. Restaurar a SQLite
sqlite3 tesaka_restored.db ".restore 'restore.bak'"
```

## Troubleshooting

### El backup no se ejecuta

1. Verificar que el plist está cargado:
   ```bash
   launchctl list | grep sqlitebackup
   ```

2. Verificar logs de errores:
   ```bash
   cat ~/backups/app/backup.err
   ```

3. Verificar permisos:
   ```bash
   ls -l ~/backup_sqlite.sh
   ls -l ~/secrets/backup_passphrase.txt
   ```

4. Probar manualmente:
   ```bash
   DB_PATH="/ruta/a/tesaka.db" \
   OUT_DIR="$HOME/backups/app" \
   PASSPHRASE_FILE="$HOME/secrets/backup_passphrase.txt" \
   ~/backup_sqlite.sh
   ```

### Error: "Permission denied"

- Verificar que `~/backup_sqlite.sh` es ejecutable: `chmod +x ~/backup_sqlite.sh`
- Verificar que `~/secrets/backup_passphrase.txt` tiene permisos 600: `chmod 600 ~/secrets/backup_passphrase.txt`
- Verificar que el directorio `~/backups/app` existe y es escribible

### Error: "Base de datos no encontrada"

- Verificar que `DB_PATH` en el plist apunta a la ruta correcta
- Verificar que la base de datos existe en esa ubicación

### Los logs no aparecen

- Verificar que las rutas en `StandardOutPath` y `StandardErrorPath` del plist son correctas
- Verificar que el directorio `~/backups/app` existe
- Verificar permisos de escritura en `~/backups/app`

## Notas de Seguridad

1. **Passphrase**: Nunca commitees la passphrase en git. Está en `.gitignore`.
2. **Permisos**: El archivo de passphrase debe tener permisos 600 (solo lectura para el propietario).
3. **Backups**: Los backups cifrados son seguros, pero no los subas a repositorios públicos.
4. **Rotación**: Los backups antiguos se eliminan automáticamente después de 30 días.

## Cambiar la Hora del Backup

Edita el plist y modifica `StartCalendarInterval`:

```xml
<key>StartCalendarInterval</key>
<dict>
    <key>Hour</key>
    <integer>3</integer>    <!-- Cambiar hora (0-23) -->
    <key>Minute</key>
    <integer>30</integer>   <!-- Cambiar minuto (0-59) -->
</dict>
```

Luego recarga:
```bash
launchctl unload ~/Library/LaunchAgents/com.industriasferis.sqlitebackup.plist
launchctl load ~/Library/LaunchAgents/com.industriasferis.sqlitebackup.plist
```

