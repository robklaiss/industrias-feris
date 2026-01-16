# SIFEN Production Go-Live Guide

## Overview

Guía completa para activar SIFEN en producción, incluyendo configuración de secretos, ejecución de smoke tests y operaciones de rutina.

## Pre-Go-Live Checklist

### 1. Infraestructura y Seguridad

- [ ] **Dominio y TLS configurados**
  - Dominio apuntando a la instancia Lightsail
  - Certificado Let's Encrypt activo y auto-renovable
  - Nginx configurado con HTTPS y headers de seguridad

- [ ] **Backups configurados**
  - Script `/usr/local/bin/sifen-backup.sh` instalado
  - Cron diario configurado (2 AM)
  - S3 bucket `sifen-backup` creado con políticas de retención

- [ ] **Secretos en SSM Parameter Store**
  - Parámetros creados bajo `/sifen/prod/*`
  - Políticas IAM de mínimo privilegio aplicadas
  - Script `/usr/local/bin/sifen-fetch-secrets.sh` instalado

- [ ] **Logs y Monitoreo**
  - CloudWatch Logs configurado para `/var/log/sifen/*`
  - Logrotate configurado (30 días retención)
  - Alarms críticas configuradas (CPU > 80%, disco > 90%)

### 2. Configuración SIFEN

- [ ] **Credenciales de Producción**
  - CSC real de producción cargado en SSM (SecureString)
  - Usuario/clave SOAP de producción en SSM
  - Timbrado electrónico activo (Marangatu)

- [ ] **Certificados Digitales**
  - Certificado P12 de producción instalado
  - Permisos correctos (600, usuario sifen)
  - mTLS configurado para endpoints SIFEN

- [ ] **Variables de Entorno**
  - `/etc/sifen/sifen.env` generado desde SSM
  - `SIFEN_ENV=prod`
  - `SIFEN_EMISOR_RUC=4554737-8`
  - `SIFEN_TIMBRADO_PROD=18578288`

## Cargar Secretos en SSM

### 1. Crear parámetros básicos

```bash
# Ambiente
aws ssm put-parameter \
  --name "/sifen/ENV" \
  --value "prod" \
  --type "String" \
  --description "SIFEN environment"

# Datos del emisor
aws ssm put-parameter \
  --name "/sifen/prod/SIFEN_EMISOR_RUC" \
  --value "4554737-8" \
  --type "String" \
  --description "RUC del emisor"

aws ssm put-parameter \
  --name "/sifen/prod/SIFEN_TIMBRADO_PROD" \
  --value "18578288" \
  --type "String" \
  --description "Timbrado de producción"
```

### 2. Cargar secretos (SecureString)

```bash
# CSC de producción (NUNCA exponer este valor)
aws ssm put-parameter \
  --name "/sifen/prod/SIFEN_IDCSC_PROD" \
  --value "IDCSC_REAL" \
  --type "String" \
  --description "IdCSC producción"

aws ssm put-parameter \
  --name "/sifen/prod/SIFEN_CSC_PROD" \
  --value "CSC_REAL_SECRETO" \
  --type "SecureString" \
  --description "CSC producción (SecureString)"

# Credenciales SOAP
aws ssm put-parameter \
  --name "/sifen/prod/SIFEN_SOAP_USER_PROD" \
  --value "usuario_real" \
  --type "String" \
  --description "Usuario SOAP producción"

aws ssm put-parameter \
  --name "/sifen/prod/SIFEN_SOAP_PASS_PROD" \
  --value "password_real" \
  --type "SecureString" \
  --description "Password SOAP producción (SecureString)"
```

### 3. Política IAM mínima

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "SSMReadSifenParameters",
      "Effect": "Allow",
      "Action": [
        "ssm:GetParameters",
        "ssm:GetParameter"
      ],
      "Resource": [
        "arn:aws:ssm:*:*:parameter/sifen/ENV",
        "arn:aws:ssm:*:*:parameter/sifen/prod/*"
      ]
    },
    {
      "Sid": "SSMDecryptSecureParameters",
      "Effect": "Allow",
      "Action": ["ssm:Decrypt"],
      "Resource": ["arn:aws:kms:*:*:key/*"]
    }
  ]
}
```

## Ejecutar Smoke Test

### 1. Preparar entorno local

```bash
# Activar entorno virtual
source .venv/bin/activate

# Opción A: Usar archivo .env.local (para testing)
cp .env.example .env.local
# Editar .env.local con secretos reales de producción
```

### 2. Ejecutar smoke test completo

```bash
# Opción 1: Con archivo de entorno
./tools/prod_smoketest.sh --env-file .env.local

# Opción 2: Con secretos de SSM (en producción)
./tools/prod_smoketest.sh

# Opción 3: Dry run (solo muestra comandos)
./tools/prod_smoketest.sh --dry-run

# Opción 4: Generar XML sin enviar
./tools/prod_smoketest.sh --no-send
```

### 3. Verificar resultado

El smoke test genera:

```
artifacts/prod_smoketest/YYYYMMDD_HHMMSS/
├── de_final.xml          # XML firmado con QR
├── metadata.json         # Metadata del DE
├── soap_request.xml      # Request enviado a SIFEN
├── soap_response.xml     # Respuesta de SIFEN
└── smoketest.log        # Log completo
```

**Resultado OK esperado:**
- Código de respuesta: `01` (Aprobado) o `001` (Aceptado)
- Mensaje: "Aprobado" o "Recibido con éxito"
- CDC generado y válido

## Operaciones de Rutina

### 1. Generar y enviar DE

```bash
# Generar DE desde JSON
./tools/make_de_wrapper.sh \
  --env prod \
  --gen '.venv/bin/python tools/generar_prevalidador.py --json mi_factura.json --out /tmp/de.xml' \
  --sign 'echo "Firma incluida"' \
  --out artifacts/de_final.xml

# Enviar a SIFEN
python -m tools.send_sirecepde --env prod --xml artifacts/de_final.xml
```

### 2. Consultar lote

```bash
# Consultar estado de lote
python -m tools/send_sirecepde --env prod --consulta-lote --nro-lote 12345
```

### 3. Validar XML localmente

```bash
# Validar contra XSD
python -m tools.send_sirecepde --env prod --validate-xsd --xml artifacts/de_final.xml
```

## Regla de Oro: QR y Firma

**IMPORTANTE**: Cualquier cambio en el DE requiere recalcular el QR:

```bash
# Siempre usar el wrapper para asegurar QR correcto
./tools/make_de_wrapper.sh --env prod --gen ... --sign ... --out final.xml
```

El wrapper garantiza:
1. XML se genera correctamente
2. Firma digital se aplica antes del QR
3. QR se calcula con el hash del XML firmado
4. Estructura correcta: Signature → gCamFuFD

## Rotación de Secretos

### 1. Rotar CSC

```bash
# 1. Subir nuevo CSC a SSM
aws ssm put-parameter \
  --name "/sifen/prod/SIFEN_CSC_PROD" \
  --value "NUEVO_CSC_SECRETO" \
  --type "SecureString" \
  --overwrite

# 2. Recargar secretos en servidor
sudo /usr/local/bin/sifen-fetch-secrets.sh

# 3. Reiniciar servicio
sudo systemctl restart sifen-web

# 4. Ejecutar smoke test para verificar
./tools/prod_smoketest.sh --no-send
```

### 2. Rotar certificado digital

```bash
# 1. Reemplazar archivo P12
sudo cp nuevo_certificado.p12 /home/sifen/certs/sifen.p12
sudo chmod 600 /home/sifen/certs/sifen.p12
sudo chown sifen:sifen /home/sifen/certs/sifen.p12

# 2. Actualizar password si cambió
# (editar /etc/sifen/sifen.env o SSM)

# 3. Reiniciar servicio
sudo systemctl restart sifen-web

# 4. Probar con smoke test
./tools/prod_smoketest.sh
```

## Troubleshooting

### Error: "Certificado no encontrado"

```bash
# Verificar ruta y permisos
ls -la /home/sifen/certs/sifen.p12
# Debe ser: -rw------- sifen sifen

# Verificar variable de entorno
grep SIFEN_CERT_PATH /etc/sifen/sifen.env
```

### Error: "CSC inválido"

```bash
# Verificar CSC cargado (sin mostrar valor completo)
aws ssm get-parameter \
  --name "/sifen/prod/SIFEN_CSC_PROD" \
  --with-decryption \
  --query 'Parameter.Value' \
  --output text | wc -c
# Debe tener longitud esperada (generalmente 48-64 chars)
```

### Error: "Timeout en envío"

```bash
# Verificar endpoint de producción
python -c "
from app.sifen_client.config import get_sifen_config
cfg = get_sifen_config('prod')
print(cfg.get_soap_service_url('recibe_lote'))
"

# Verificar conectividad
curl -k https://sifen.set.gov.py/de/ws/async/recibe-lote.wsdl?wsdl
```

## Monitoreo

### 1. Logs importantes

```bash
# Logs de aplicación
sudo journalctl -u sifen-web -f

# Logs de SIFEN
tail -f /var/log/sifen/sifen.log

# Logs de Nginx
sudo tail -f /var/log/nginx/sifen_access.log
```

### 2. Métricas clave

- **Tasa de éxito de envíos**: > 95%
- **Tiempo de respuesta SOAP**: < 30s
- **Uso de disco**: < 80%
- **CPU**: < 70% promedio

### 3. Alertas recomendadas

- Fallos consecutivos de envío (> 3)
- Error de autenticación SIFEN
- Disco > 90%
- Servicio caído

## Contacto de Emergencia

- **SOPORTE SIFEN**: [Número oficial]
- **Equipo Técnico**: [Contactos internos]
- **AWS Support**: [Plan de soporte]

---

**IMPORTANTE**: Este documento contiene información sensible. No compartir fuera del equipo autorizado.
