# Mock Server mTLS para Pruebas Locales

Este documento describe cómo usar el mock server mTLS para probar la integración SIFEN **sin conectarse a SIFEN real**.

## Requisitos

- Python 3.11 o 3.12
- OpenSSL (para generar certificados DEV)
- Flask (`pip install flask`)
- Certificados DEV generados (ver sección "Generar Certificados DEV")

## Estructura

```
tools/mtls_mock/
├── generate_dev_certs.sh    # Script para generar certificados DEV
├── mock_server.py           # Servidor mock mTLS
├── test_mtls_mock.py        # Test automático
├── certs/                   # Certificados DEV (NO commitear)
│   ├── ca-dev.crt
│   ├── ca-dev.key
│   ├── server-dev.crt
│   ├── server-dev.key
│   ├── client-dev.crt
│   ├── client-dev.key
│   ├── client-dev.p12       # Password: dev123
│   └── ca-bundle-dev.crt
└── artifacts/               # Artifacts de requests (sanitizados)
    └── last_request_*.xml
```

## Generar Certificados DEV

**IMPORTANTE**: Estos certificados son **SOLO para desarrollo local**. NO usar en producción ni commitear al repositorio.

```bash
cd tesaka-cv
tools/mtls_mock/generate_dev_certs.sh
```

Esto generará:
- **CA DEV**: `certs/ca-dev.crt` y `certs/ca-dev.key`
- **Server cert**: `certs/server-dev.crt` y `certs/server-dev.key`
- **Client cert**: `certs/client-dev.crt`, `certs/client-dev.key`, y `certs/client-dev.p12` (password: `dev123`)
- **CA Bundle**: `certs/ca-bundle-dev.crt`

## Levantar el Mock Server

```bash
cd tesaka-cv
python tools/mtls_mock/mock_server.py
```

El servidor escuchará en `https://127.0.0.1:9443` y requerirá certificado de cliente (mTLS).

### Endpoints

- `POST /de/ws/async/recibe-lote` - Simula `siRecepLoteDE`
- `POST /soap` - Endpoint genérico SOAP
- `GET /health` - Health check (sin mTLS requerido)

### Variables de Entorno

- `MTLS_MOCK_HOST` - Host del servidor (default: `127.0.0.1`)
- `MTLS_MOCK_PORT` - Puerto del servidor (default: `9443`)

## Usar el Cliente Real con el Mock

### Opción 1: Variables de Entorno

```bash
export SIFEN_MOCK=1
export SIFEN_ENV=test
export SIFEN_CERT_PEM_PATH=/path/to/tools/mtls_mock/certs/client-dev.crt
export SIFEN_KEY_PEM_PATH=/path/to/tools/mtls_mock/certs/client-dev.key
export SIFEN_CA_BUNDLE_PATH=/path/to/tools/mtls_mock/certs/ca-bundle-dev.crt

# Ejecutar el cliente
python tools/send_sirecepde.py --xml artifacts/algun_de.xml
```

### Opción 2: Usar P12 DEV

```bash
export SIFEN_MOCK=1
export SIFEN_ENV=test
export SIFEN_MTLS_P12_PATH=/path/to/tools/mtls_mock/certs/client-dev.p12
export SIFEN_MTLS_P12_PASSWORD=dev123
export SIFEN_CA_BUNDLE_PATH=/path/to/tools/mtls_mock/certs/ca-bundle-dev.crt

# Ejecutar el cliente
python tools/send_sirecepde.py --xml artifacts/algun_de.xml
```

### Opción 3: URL Personalizada

```bash
export SIFEN_MOCK=1
export SIFEN_MOCK_BASE_URL=https://127.0.0.1:9443
export SIFEN_ENV=test
# ... resto de variables de certificados ...
```

## Test Automático

Ejecutar el test completo que:
1. Levanta el mock server
2. Prueba handshake mTLS
3. Prueba request SOAP
4. Verifica artifacts
5. Baja el servidor

```bash
cd tesaka-cv
python tools/mtls_mock/test_mtls_mock.py
```

## Verificar con curl

```bash
curl -k -v \
  --cert tools/mtls_mock/certs/client-dev.crt \
  --key tools/mtls_mock/certs/client-dev.key \
  --cacert tools/mtls_mock/certs/ca-bundle-dev.crt \
  https://127.0.0.1:9443/health
```

## Respuesta del Mock

El mock server responde con un SOAP dummy que simula `siRecepLoteDE`:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<soap:Envelope xmlns:soap="http://www.w3.org/2003/05/soap-envelope">
  <soap:Body>
    <rResEnviLoteDe xmlns="http://ekuatia.set.gov.py/sifen/xsd">
      <dId>123456789012345</dId>
      <dCodRes>0300</dCodRes>
      <dMsgRes>Lote recibido correctamente (MOCK)</dMsgRes>
      <dProtConsLote>999999999</dProtConsLote>
      <dTpoProces>1</dTpoProces>
    </rResEnviLoteDe>
  </soap:Body>
</soap:Envelope>
```

## Artifacts

El mock server guarda requests sanitizados en `tools/mtls_mock/artifacts/last_request_*.xml`.

**Sanitización**: El contenido de `<xDE>` se redacta para no exponer datos sensibles.

## Troubleshooting

### Error: "Certificados del servidor no encontrados"

**Solución**: Ejecutar `tools/mtls_mock/generate_dev_certs.sh`

### Error: "unknown ca" o "certificate verify failed"

**Solución**: Asegurarse de que `SIFEN_CA_BUNDLE_PATH` apunta a `certs/ca-bundle-dev.crt`

### Error: "handshake failure" o "peer did not return a certificate"

**Solución**: 
- Verificar que el cliente está enviando el certificado correcto
- Verificar que `SIFEN_CERT_PEM_PATH` y `SIFEN_KEY_PEM_PATH` apuntan a los certs DEV
- Verificar que el servidor está usando `certs/ca-dev.crt` para verificar client certs

### Error: "wrong content-type"

**Solución**: El mock server acepta `application/soap+xml` y `text/xml`. Si el cliente envía otro Content-Type, el mock lo loguea pero no rechaza.

### Error: "Connection refused"

**Solución**: 
- Verificar que el servidor está corriendo: `ps aux | grep mock_server`
- Verificar que el puerto 9443 no está en uso: `lsof -i :9443`
- Verificar firewall/localhost restrictions

### El servidor no inicia

**Solución**:
- Verificar que Flask está instalado: `pip install flask`
- Verificar permisos de los certificados: `ls -la tools/mtls_mock/certs/`
- Verificar logs del servidor (se imprimen en stdout)

## Seguridad

⚠️ **ADVERTENCIA**: 

- Los certificados DEV son **SOLO para desarrollo local**
- **NO commitear** certificados privados (`.key`, `.p12`, `.pfx`) al repositorio
- El mock server **NO valida** la estructura real del XML SOAP
- El mock server **NO valida** firmas XML
- El mock server **NO valida** reglas de negocio SIFEN

## Integración con CI/CD

Para usar en CI/CD, generar los certificados DEV una vez y guardarlos como secrets (NO en el repo):

```bash
# En CI/CD
tools/mtls_mock/generate_dev_certs.sh
# Guardar certs/ como secrets (ej: GitHub Secrets, GitLab CI Variables)
# En cada run, restaurar certs/ desde secrets
```

## Próximos Pasos

Una vez que el mock funciona localmente:
1. Probar con el cliente real del proyecto
2. Verificar que TLS 1.2 está forzado (ver logs del cliente)
3. Probar con certificados P12 reales (fuera del repo)
4. Integrar en tests automatizados

---

**Última actualización**: 2025-01-XX  
**Versión**: 1.0

