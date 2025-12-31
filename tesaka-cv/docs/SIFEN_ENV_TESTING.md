# Guía de Testing y Envío a SIFEN

## Variables de Entorno Requeridas

Para usar el cliente SOAP de SIFEN, configure las siguientes variables de entorno:

### Variables Obligatorias

```bash
# Certificado y autenticación
SIFEN_CERT_PATH=/ruta/al/certificado.pfx        # o .p12
SIFEN_CERT_PASSWORD=tu_password_aqui

# Ambiente (opcional, default: test)
SIFEN_ENV=test                                    # o 'prod'
```

### Variables Opcionales

```bash
# Configuración mTLS
SIFEN_USE_MTLS=true                               # default: true
SIFEN_CA_BUNDLE_PATH=/ruta/a/ca-bundle.pem       # opcional

# Timeouts SOAP
SIFEN_SOAP_TIMEOUT_CONNECT=15                     # segundos (default: 15)
SIFEN_SOAP_TIMEOUT_READ=45                        # segundos (default: 45)
SIFEN_SOAP_MAX_RETRIES=3                          # default: 3
```

## Uso del Script de Envío

El script `tools/send_sirecepde.py` permite enviar documentos electrónicos a SIFEN de forma sencilla.

### Ejemplos de Uso

#### 1. Enviar archivo específico a ambiente TEST

```bash
python -m tools.send_sirecepde --env test --xml artifacts/sirecepde_20251226_233653.xml
```

#### 2. Enviar el archivo más reciente a TEST

```bash
python -m tools.send_sirecepde --env test --xml latest
```

#### 3. Enviar a PRODUCCIÓN

```bash
python -m tools.send_sirecepde --env prod --xml latest
```

#### 4. Guardar respuesta en directorio específico

```bash
python -m tools.send_sirecepde --env test --xml latest --artifacts-dir /tmp/respuestas
```

### Formato del XML

El XML debe ser un `siRecepDE` completo (estructura `rEnviDe` con `xDE`), generado por:
- `tools/build_sirecepde.py` (wrappea un DE dentro de rEnviDe)
- O cualquier herramienta que genere XML válido según `WS_SiRecepDE_v150.xsd`

### Respuesta del Script

El script imprime:
- ✅ Estado del envío (OK/ERROR)
- Código de respuesta SIFEN (ej: '0500', '0502')
- Mensaje de respuesta
- CDC (Código de Control) si está presente
- Estado del documento

Y guarda la respuesta completa en JSON en `artifacts/response_recepcion_YYYYMMDD_HHMMSS.json`

## Uso Programático

También puede usar `SoapClient` directamente desde Python:

```python
from app.sifen_client import SoapClient, get_sifen_config

# Configurar
config = get_sifen_config(env="test")

# Leer XML
xml_content = Path("artifacts/sirecepde_20251226_233653.xml").read_text()

# Enviar
with SoapClient(config) as client:
    response = client.recepcion_de(xml_content)
    
    print(f"OK: {response['ok']}")
    print(f"Código: {response.get('codigo_respuesta')}")
    print(f"Mensaje: {response.get('mensaje')}")
    print(f"CDC: {response.get('cdc')}")
```

## Estructura de la Respuesta

La respuesta de `recepcion_de()` es un diccionario con:

```python
{
    'ok': bool,                    # True si la operación fue exitosa
    'codigo_estado': int,           # Código HTTP (si aplica)
    'codigo_respuesta': str,        # Código SIFEN (ej: '0500', '0502')
    'mensaje': str,                 # Mensaje de respuesta
    'cdc': str,                     # Código de Control (CDC)
    'estado': str,                  # Estado del documento
    'raw_response': str,            # Respuesta XML cruda (limitada, sin datos sensibles)
    'parsed_fields': dict           # Campos adicionales parseados
}
```

## Códigos de Respuesta SIFEN

- **0500**: Éxito (RUC encontrado, documento recibido)
- **0502**: Éxito (documento procesado correctamente)
- **0200**: Mensaje excede tamaño máximo (siRecepDE > 1000 KB)
- **0183**: RUC del certificado no activo/válido
- **02xx**: Errores de validación/rechazo

## Troubleshooting

### Error: "Certificado no encontrado"
- Verifique que `SIFEN_CERT_PATH` apunta a un archivo existente
- Verifique permisos de lectura del archivo

### Error: "Contraseña del certificado P12 incorrecta"
- Verifique `SIFEN_CERT_PASSWORD`
- Asegúrese de que el certificado no esté corrupto

### Error: "Operación 'rEnviDe' no encontrada en el WSDL"
- Verifique que la URL del WSDL sea correcta
- Verifique conectividad a SIFEN
- Verifique que el ambiente (test/prod) sea correcto

### Error: "Error de transporte"
- Verifique conectividad a internet
- Verifique que el certificado sea válido y no esté expirado
- Verifique configuración de firewall/proxy

### Error: "XML excede tamaño máximo"
- El XML debe ser <= 1000 KB para siRecepDE
- Revise el tamaño del XML antes de enviar

## Notas de Seguridad

- **NO** se loggean contraseñas ni datos sensibles
- Los archivos PEM temporales se crean con permisos 600
- Los archivos PEM temporales se eliminan automáticamente al cerrar el cliente
- El P12/PFX es la fuente de verdad; los PEM son temporales

