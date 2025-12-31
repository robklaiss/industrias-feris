# Uso de send_sirecepde.py

## Ejemplo básico

```bash
# Activar entorno virtual (si aplica)
source .venv/bin/activate

# Enviar XML a SIFEN test
python -m tools.send_sirecepde --env test --xml latest
```

## Con validación XSD local

Para validar el XML contra esquemas XSD locales antes de enviar a SIFEN:

```bash
# Activar entorno virtual
source .venv/bin/activate

# Configurar variables de entorno
export SIFEN_DEBUG_SOAP=1
export SIFEN_VALIDATE_XSD=1
export SIFEN_XSD_DIR="/path/to/xsd/dir"

# Ejecutar con validación
python -m tools.send_sirecepde --env test --xml latest
```

**Esperado**: Si hay algo inválido, ver el/los elementos exactos en consola (línea + mensaje), y NO se hace POST.

## Variables de entorno

- `SIFEN_DEBUG_SOAP=1`: Guarda SOAP enviado/recibido en `artifacts/`
- `SIFEN_VALIDATE_XSD=1`: Valida XML contra XSD locales antes de enviar
- `SIFEN_XSD_DIR`: Directorio donde están los archivos XSD (default: `docs/set/ekuatia.set.gov.py/sifen/xsd`)
- `SIFEN_CERT_PATH`: Path al certificado P12/PFX
- `SIFEN_CERT_PASSWORD`: Contraseña del certificado

## Ejemplo completo con todas las opciones

```bash
source .venv/bin/activate

export SIFEN_DEBUG_SOAP=1
export SIFEN_VALIDATE_XSD=1
export SIFEN_XSD_DIR="/Users/robinklaiss/Dev/industrias-feris-facturacion-electronica-simplificado/rshk-jsifenlib/docs/set/ekuatia.set.gov.py/sifen/xsd"
export SIFEN_CERT_PATH="/path/to/cert.p12"
export SIFEN_CERT_PASSWORD="password"

python -m tools.send_sirecepde --env test --xml artifacts/sirecepde_rebuild.xml
```

