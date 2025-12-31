# Conversión P12/PFX a PEM Temporales para mTLS

## Resumen

Este módulo convierte certificados PKCS#12 (`.p12`/`.pfx`) a archivos PEM temporales para uso con librerías que requieren formato PEM en mTLS (mutual TLS) con SIFEN.

**El P12/PFX es la fuente de verdad**; los archivos PEM son temporales y se crean automáticamente cuando se usa un certificado P12/PFX.

## Configuración

Las variables de entorno siguen siendo las mismas:

```bash
SIFEN_CERT_PATH=/ruta/al/certificado.pfx  # o .p12
SIFEN_CERT_PASSWORD=tu_password_aqui
SIFEN_USE_MTLS=true
```

El sistema detecta automáticamente si el certificado es `.p12`/`.pfx` y lo convierte a PEM temporales antes de usarlo con Zeep/requests/httpx.

## Funcionamiento

1. **Detección automática**: Si `SIFEN_CERT_PATH` apunta a un archivo `.p12` o `.pfx`, se convierte automáticamente.
2. **Creación temporal**: Se crean dos archivos PEM en el directorio temporal del sistema:
   - `sifen_cert_*.pem`: Certificado X.509
   - `sifen_key_*.pem`: Clave privada (sin cifrar)
3. **Permisos 600**: Los archivos se crean con permisos 600 (solo lectura/escritura para el propietario).
4. **Limpieza automática**: Los archivos se eliminan cuando se cierra el cliente SOAP (`close()` o context manager).

## Seguridad

- **No se loggean secretos**: Las contraseñas y rutas completas de archivos temporales no aparecen en logs.
- **Permisos restrictivos**: Archivos PEM con permisos 600.
- **Limpieza automática**: Archivos temporales se eliminan al cerrar el cliente.
- **P12 como fuente de verdad**: Los PEM son temporales; el P12 original no se modifica.

## Notas

- Si el certificado ya es PEM (`.pem`), se usa directamente sin conversión.
- Los archivos temporales se crean en el directorio temporal del sistema (`tempfile.gettempdir()`).
- En caso de error, los archivos temporales se limpian automáticamente.

