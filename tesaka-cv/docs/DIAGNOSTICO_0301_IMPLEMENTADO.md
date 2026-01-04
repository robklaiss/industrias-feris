# Modo Diagnóstico Automático para dCodRes=0301

## Resumen

Se implementó un modo diagnóstico automático que se activa cuando SIFEN devuelve `dCodRes=0301` con `dProtConsLote=0`. Este modo guarda un paquete completo de evidencia para facilitar el diagnóstico.

---

## Implementación

### Función Principal

**Archivo**: `tools/send_sirecepde.py`  
**Función**: `_save_0301_diagnostic_package()` (línea 546)

**Activación automática**:
- Se ejecuta automáticamente cuando se detecta `dCodRes=0301` y `dProtConsLote=0`
- No requiere flags adicionales (siempre activo)
- No bloquea el flujo si falla (solo imprime warning)

---

## Artifacts Generados

### 1. `diagnostic_0301_summary_{timestamp}.json`

**Contenido**:
- `diagnostic_package`: Trigger, timestamp, ambiente
- `response`: dCodRes, dMsgRes, dProtConsLote, dTpoProces, ok
- `request`: dId, SOAP request (redactado), headers enviados (redactados)
- `response_details`: Headers recibidos, respuesta completa
- `zip`: SHA256 del ZIP, tamaño en bytes
- `de_info`: 
  - DE Id (CDC)
  - RUC emisor
  - DV RUC
  - Timbrado
  - Establecimiento
  - Punto de expedición
  - Número de documento
  - Tipo de documento
  - Fecha de emisión
- `artifacts`: Referencias a artifacts existentes (dump-http si está activo)
- `notes`: Notas sobre redacción y ubicación de artifacts

### 2. `diagnostic_0301_soap_request_redacted_{timestamp}.xml`

**Contenido**: SOAP request completo con `xDE` base64 redactado (reemplazado por `[BASE64_REDACTED_FOR_DIAGNOSTIC]`)

---

## Redacción de Secretos

### ✅ Headers Redactados

- `Authorization`: Reemplazado por `[REDACTED]`
- `X-API-Key`: Reemplazado por `[REDACTED]`

### ✅ SOAP Request Redactado

- `xDE` base64: Reemplazado por `[BASE64_REDACTED_FOR_DIAGNOSTIC]`
- **Nota**: El SOAP completo (sin redactar) está disponible en `artifacts/soap_last_request_SENT.xml` si `--dump-http` está activo

### ✅ No se Incluyen

- Passwords de certificados (no se pasan como parámetros)
- Contenido de certificados (solo paths si están disponibles)
- Variables de entorno sensibles

---

## Integración con `--dump-http`

Si `--dump-http` está activo, el summary.json incluye referencias a:

- `soap_raw_sent_lote_{timestamp}.xml`: SOAP request completo (sin redactar)
- `http_headers_sent_lote_{timestamp}.json`: Headers HTTP enviados
- `http_response_headers_lote_{timestamp}.json`: Headers HTTP recibidos
- `soap_raw_response_lote_{timestamp}.xml`: SOAP response completo

**Nota**: Estos artifacts se generan automáticamente cuando `--dump-http` está activo, y el summary.json los referencia para facilitar el diagnóstico.

---

## Ubicación de Artifacts

**Directorio**: `artifacts/`

**Archivos generados**:
- `diagnostic_0301_summary_{YYYYMMDD_HHMMSS}.json`
- `diagnostic_0301_soap_request_redacted_{YYYYMMDD_HHMMSS}.xml`

**Archivos referenciados** (si existen):
- `soap_raw_sent_lote_{timestamp}.xml` (si `--dump-http` activo)
- `http_headers_sent_lote_{timestamp}.json` (si `--dump-http` activo)
- `http_response_headers_lote_{timestamp}.json` (si `--dump-http` activo)
- `soap_raw_response_lote_{timestamp}.xml` (si `--dump-http` activo)
- `soap_last_request_SENT.xml` (siempre disponible)
- `soap_last_request_BYTES.bin` (siempre disponible)
- `preflight_lote.xml` (siempre disponible)
- `preflight_zip.zip` (siempre disponible)

---

## Ejemplo de Uso

### CLI

```bash
# Envío normal (diagnóstico automático si 0301)
python -m tools.send_sirecepde --env test --xml artifacts/de.xml

# Con dump-http (más artifacts)
python -m tools.send_sirecepde --env test --xml artifacts/de.xml --dump-http
```

### Web

El diagnóstico se activa automáticamente en el endpoint `/de/{id}/send` cuando se recibe `dCodRes=0301` con `dProtConsLote=0`.

---

## Estructura del summary.json

```json
{
  "diagnostic_package": {
    "trigger": "dCodRes=0301 with dProtConsLote=0",
    "timestamp": "20250115_143025",
    "env": "test"
  },
  "response": {
    "dCodRes": "0301",
    "dMsgRes": "Lote no encolado para procesamiento",
    "dProtConsLote": 0,
    "dTpoProces": null,
    "ok": false
  },
  "request": {
    "dId": "202501151430257",
    "soap_request_redacted": "<?xml version='1.0' encoding='UTF-8'?>...",
    "headers_sent": {
      "Content-Type": "application/soap+xml; charset=utf-8; action=\"siRecepLoteDE\"",
      "Accept": "application/soap+xml, text/xml, */*"
    }
  },
  "response_details": {
    "headers_received": {...},
    "response_full": {...}
  },
  "zip": {
    "sha256": "abc123...",
    "size_bytes": 12345
  },
  "de_info": {
    "de_id": "01234567890123456789012345678901234567890123",
    "ruc_emisor": "80012345",
    "dv_ruc": "7",
    "timbrado": "12345678",
    "establecimiento": "001",
    "punto_expedicion": "001",
    "numero_documento": "0000001",
    "tipo_documento": "1",
    "fecha_emision": "2025-01-15"
  },
  "artifacts": {
    "dump_http_available": true,
    "dump_http_files": {
      "soap_request_file": "soap_raw_sent_lote_20250115_143025.xml",
      "headers_sent_file": "http_headers_sent_lote_20250115_143025.json",
      "headers_response_file": "http_response_headers_lote_20250115_143025.json",
      "soap_response_file": "soap_raw_response_lote_20250115_143025.xml"
    },
    "other_artifacts": [
      "soap_last_request_SENT.xml",
      "soap_last_request_BYTES.bin",
      "preflight_lote.xml",
      "preflight_zip.zip"
    ]
  },
  "notes": [
    "Este paquete se generó automáticamente cuando SIFEN devolvió dCodRes=0301 con dProtConsLote=0",
    "El SOAP request está redactado (xDE base64 removido) para evitar archivos grandes",
    "Los headers pueden estar redactados si contenían secretos (Authorization, API keys)",
    "Para ver el SOAP completo, consultar artifacts/soap_last_request_SENT.xml",
    "Para ver el ZIP completo, consultar artifacts/preflight_zip.zip"
  ]
}
```

---

## Verificación de Secretos

### ✅ Confirmado: No se Imprimen Secretos

1. **Headers**: `Authorization` y `X-API-Key` se redactan automáticamente
2. **SOAP Request**: `xDE` base64 se redacta (reemplazado por placeholder)
3. **Passwords**: No se incluyen en ningún artifact (no se pasan como parámetros)
4. **Certificados**: Solo paths si están disponibles, no contenido

### ⚠️ Notas de Seguridad

- El SOAP completo (sin redactar) está disponible en `artifacts/soap_last_request_SENT.xml` si `--dump-http` está activo
- El ZIP completo está disponible en `artifacts/preflight_zip.zip`
- Estos archivos pueden contener información sensible (certificados en la firma)
- **Recomendación**: No compartir artifacts completos públicamente

---

## Integración

### CLI (`tools/send_sirecepde.py`)

**Línea**: 4388-4408

```python
if codigo_respuesta == "0301":
    d_prot_cons_lote_val = response.get('d_prot_cons_lote')
    if d_prot_cons_lote_val is None or d_prot_cons_lote_val == 0 or str(d_prot_cons_lote_val) == "0":
        # ... advertencia ...
        if artifacts_dir:
            _save_0301_diagnostic_package(...)
```

### Web (`web/main.py`)

**Línea**: 743-798

```python
if d_cod_res == "0301" and (d_prot_cons_lote is None or d_prot_cons_lote == 0 or str(d_prot_cons_lote) == "0"):
    # ... guardar paquete de diagnóstico ...
    _save_0301_diagnostic_package(...)
```

---

## Salida en Consola

Cuando se activa el diagnóstico, se imprime:

```
📦 Paquete de diagnóstico 0301 guardado:
   📄 Summary: diagnostic_0301_summary_20250115_143025.json
   📄 SOAP request (redactado): diagnostic_0301_soap_request_redacted_20250115_143025.xml
   🔍 DE Id (CDC): 01234567890123456789012345678901234567890123
   🏢 RUC: 80012345
   📋 Timbrado: 12345678
   📝 Nro Doc: 0000001
   📅 Fecha: 2025-01-15
   🔐 ZIP SHA256: abc123def456...
```

---

## Compatibilidad con `--dump-http`

El modo diagnóstico es **complementario** a `--dump-http`:

- **`--dump-http`**: Guarda artifacts HTTP completos (request/response) con timestamps
- **Diagnóstico 0301**: Crea un `summary.json` único que referencia y consolida información de múltiples artifacts

**Ventaja**: El `summary.json` proporciona una vista consolidada de toda la información relevante para diagnosticar `dCodRes=0301`, sin necesidad de buscar múltiples archivos.

---

**Última actualización**: 2025-01-XX  
**Versión**: 1.0
