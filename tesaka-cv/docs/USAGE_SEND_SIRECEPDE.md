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
- `SIFEN_SKIP_RUC_GATE=1`: (solo pruebas) Omitir el gate siConsRUC/dRUCFactElec cuando falla o no responde

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

## Resolver 0301 por CDC repetido (solo TEST)

Si SIFEN devuelve `dCodRes=0301` con `dProtConsLote=0`, significa que no encoló el lote (frecuente al reenviar el mismo CDC).

1. Editá el XML y cambiá `dNumDoc`.
2. Reenviá con `--bump-doc <nuevo_numdoc>` para que `send_sirecepde` regenere automáticamente `DE@Id`/`dDVId` antes de firmar.

```bash
# Cambiar dNumDoc -> 0000002 y normalizar CDC/DV antes de firmar
SIFEN_SKIP_RUC_GATE=1 \
python -m tools.send_sirecepde \
  --env test \
  --xml artifacts/last_lote.xml \
  --dump-http \
  --bump-doc 2
```

- Solo funciona en `--env test`. En PROD el flag está bloqueado.
- El script guarda el XML normalizado en `artifacts/last_rde_bumped.xml`.
- En los logs verás:
  ```
  🧪 TEST bump-doc activo
     dNumDoc 0000001 -> 0000002
     CDC 010...91 -> 010...92
  ```

### Normalización automática antes de firmar

Aun sin `--bump-doc`, `send_sirecepde` ahora recalcula `DE@Id` y `dDVId` **antes de firmar** usando los valores actuales de:

- `gTimb` (`dNumTim`, `dEst`, `dPunExp`, `dNumDoc`, `iTiDE`)
- `gDatGralOpe/dFeEmiDE`
- `gTotSub/dTotalGs`
- `gEmis/dRucEm` + `dDVEmi`

Esto evita que se firme un CDC viejo cuando se edita solo `dNumDoc`.

### Mensaje cuando vuelve 0301

En caso de que igualmente recibas `dCodRes=0301`, la CLI imprime un recordatorio:

```
⚠️  SIFEN no encoló el lote (0301).
   Generá un nuevo CDC (ej: cambiar dNumDoc y usar --bump-doc) y volvé a enviar.
```

Además se guarda un paquete de diagnóstico en `artifacts/diagnostic_0301_*` (SOAP redactado + summary JSON + lote original).

### CLI auxiliar: tools.bump_numdoc.py

Cuando querés preparar un XML editado sin pasar aún por `send_sirecepde`, usá el nuevo helper:

```bash
source .venv/bin/activate

python -m tools.bump_numdoc \
  --in artifacts/last_lote.xml \
  --out artifacts/last_lote_bump3.xml \
  --numdoc 0000003 \
  --bump-date
```

- `--numdoc` acepta cualquier número y lo auto-pad a 7 dígitos.
- `--bump-date` es opcional: actualiza `dFeEmiDE` a la hora actual.
- Siempre regenera `DE@Id` y `dDVId` invocando `build_cdc_from_de_xml`.

Después reenviá con:

```bash
SIFEN_SKIP_RUC_GATE=1 \
python -m tools.send_sirecepde \
  --env test \
  --xml artifacts/last_lote_bump3.xml \
  --dump-http
```

## Verificación rápida de consulta RUC (sin enviar lote)

Para probar solo la consulta RUC (siConsRUC) sin enviar un lote completo:

### Variables de entorno requeridas

```bash
# Certificado para firma (puede ser el mismo que mTLS)
export SIFEN_SIGN_P12_PATH="/path/to/cert.p12"
export SIFEN_SIGN_P12_PASSWORD="password"

# Certificado para mTLS (puede ser el mismo que firma)
export SIFEN_MTLS_P12_PATH="/path/to/cert.p12"
export SIFEN_MTLS_P12_PASSWORD="password"
```

### Comando de prueba

```bash
# Activar entorno virtual
source .venv/bin/activate

# Consulta básica (ambiente test)
python -m tools.consulta_ruc --env test --ruc 4554737

# Con dump HTTP (guarda artifacts para diagnóstico)
python -m tools.consulta_ruc --env test --ruc 4554737 --dump-http

# Producción
python -m tools.consulta_ruc --env prod --ruc 80012345 --dump-http
```

### Resultado esperado

Si el endpoint y certificados están correctos:
- **dCodRes=0502**: RUC encontrado (éxito)
- **dCodRes=0500**: RUC inexistente
- **dCodRes=0501**: Sin permiso para consultar

Si hay error de configuración:
- **dCodRes=0160**: XML mal formado (revisar endpoint WSDL)
- **dCodRes=0183**: RUC del certificado no activo/válido

### Artifacts generados (con --dump-http)

Los siguientes archivos se guardan en `artifacts/`:
- `consulta_ruc_sent_YYYYMMDD_HHMMSS.xml` - Request SOAP enviado
- `consulta_ruc_response_YYYYMMDD_HHMMSS.xml` - Response completo
- `consulta_ruc_headers_sent_YYYYMMDD_HHMMSS.json` - Headers HTTP enviados
- `consulta_ruc_headers_received_YYYYMMDD_HHMMSS.json` - Headers HTTP recibidos

Estos artifacts permiten diagnosticar problemas sin necesidad de enviar lotes completos.

## Bypass controlado del GATE (solo pruebas)

Cuando el servicio `siConsRUC` está caído o tarda demasiado en TEST, se puede omitir temporalmente la validación de habilitación del RUC. **No uses este bypass como flujo normal.**

### Opción 1: variable de entorno

```bash
export SIFEN_SKIP_RUC_GATE=1
python -m tools.send_sirecepde --env test --xml artifacts/ultimo_lote.xml --dump-http
```

### Opción 2: flag directo en la CLI

```bash
python -m tools.send_sirecepde --env test --xml artifacts/ultimo_lote.xml --skip-ruc-gate --dump-http
```

Ambas opciones imprimen un bloque:

```
⛔⛔⛔⛔⛔ GATE BYPASS ACTIVO ⛔⛔⛔⛔⛔
BYPASS siConsRUC/dRUCFactElec habilitado (...)
Continuando SIN validar habilitación FE del RUC.
```

Y generan un archivo `artifacts/gate_bypass_YYYYMMDD_HHMMSS.txt` indicando motivo, ambiente y RUC.

- **Ambiente TEST**: puedes usar el bypass para seguir enviando lotes mientras SIFEN corrige el gate.
- **Ambiente PROD**: se mantiene bloqueado por defecto; solo habilítalo si estás 100% seguro y aceptás el riesgo de enviar desde un RUC no habilitado.

En cualquier ambiente, si no activás el bypass, el flujo se comporta como antes: si `siConsRUC` falla, el envío se detiene con mensajes detallados.

