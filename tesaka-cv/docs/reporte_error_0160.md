# Reporte Técnico: Error 0160 "XML Mal Formado" en SIFEN

## Resumen Ejecutivo

Se confirmó que ** solo se realiza un POST** a SIFEN. El error 0160 "XML Mal Formado" es causado por una inconsistencia entre el envelope SOAP 1.2 y el Content-Type utilizado. Aunque se corrigió el Content-Type, el error persiste, indicando que hay otros problemas de formato en el XML.

## Hallazgos

### 1. Confirmación de flujo único

- **No hay 2 envíos**: Solo se realiza un POST en `send_recibe_lote`
- **VERIFICADOR E2E** estaba leyendo archivos antiguos (con nombres `soap_raw_response_lote_*`) que contenían responses previos con 0301
- **Response real** siempre fue 0160, como se evidencia en `response_recepcion_*.json`

### 2. Problema de trazabilidad resuelto

- Se implementó **request_id único** (ej: `20260117_163506_3067`) en cada request
- Se guardan artifacts con nombres claros:
  - `recibe_lote_REQ_<request_id>.xml`
  - `recibe_lote_REQ_<request_id>_headers.json`
  - `recibe_lote_RESP_<request_id>.xml`
  - `recibe_lote_RESP_<request_id>_meta.json`
- El response incluye `request_id` para correlacionar 1:1

### 3. Causa identificada del 0160

#### Problema principal: Content-Type incorrecto
- **SOAP envelope**: `http://www.w3.org/2003/05/soap-envelope` (SOAP 1.2)
- **Content-Type original**: `application/xml; charset=utf-8` (SOAP 1.1)
- **Content-Type corregido**: `application/soap+xml; charset=utf-8; action="siRecepLoteDE"`

Este mismatch causa que SIFEN rechace con 0160.

#### Evidencia:
```xml
<!-- Envelope SOAP 1.2 -->
<env:Envelope xmlns:env="http://www.w3.org/2003/05/soap-envelope">

<!-- Content-Type incorrecto -->
Content-Type: application/xml; charset=utf-8
```

### 4. Script de replay creado

Se creó `tools/replay_recibe_lote.py` que:
- Lee el último request guardado
- Re-envía exactamente el mismo XML y headers
- Confirma que el mismo request produce 0160 consistentemente

### 5. Estructura XML verificada

El XML interno del lote es correcto:
- ✅ `dVerFor` presente como primer hijo de `rDE`
- ✅ Sin prefijos `ns2:` en elementos SIFEN
- ✅ `Signature` sin prefijos
- ✅ Estructura válida según XSD v150

## Cambios Aplicados

### 1. Fix en VERIFICADOR E2E (`tools/send_sirecepde.py`)
```python
# Ahora lee archivos correctos:
sent_files = sorted(artifacts_dir.glob("recibe_lote_sent_*.xml"))
headers_sent_files = sorted(artifacts_dir.glob("recibe_lote_headers_*.json"))
resp_files = sorted(artifacts_dir.glob("recibe_lote_raw_*.xml"))
```

### 2. Request_id en `app/sifen_client/soap_client.py`
```python
# Generar ID único
request_id = f"{datetime.now().strftime('%Y%m%d_%H%M%S')}_{secrets.token_hex(2)[:4]}"

# Guardar en artifacts
(artifacts_dir / f"recibe_lote_REQ_{request_id}.xml").write_text(payload_xml)
(artifacts_dir / f"recibe_lote_RESP_{request_id}.xml").write_text(raw_xml)
```

### 3. Content-Type corregido
```python
headers = {
    "Accept": "application/xml, text/xml, */*",
    "Content-Type": "application/soap+xml; charset=utf-8; action=\"siRecepLoteDE\"",
    "Connection": "close",
}
```

## Estado Actual

- ✅ VERIFICADOR E2E muestra el response correcto (0160)
- ✅ Request/response trazable con request_id
- ✅ Content-Type corregido para SOAP 1.2
- ❌ Error 0160 persiste (hay otras causas no identificadas)

## Próximos Pasos Sugeridos

1. **Validar con XMLSec**: Verificar que la firma sea válida con el XML exacto enviado
2. **Comparar con request funcional**: Obtener un XML que sí funcione y comparar byte por byte
3. **Revisar encoding**: Asegurar que el XML se envíe con UTF-8 sin BOM
4. **Contactar SIFEN**: Solicitar detalles específicos del error 0160

## Comandos de Verificación

```bash
# 1. Ejecutar envío con dump
export SIFEN_SKIP_RUC_GATE=1
.venv/bin/python -m tools.send_sirecepde --env test --xml artifacts/last_lote.xml --dump-http

# 2. Ver artifacts generados
ls -la artifacts/*REQ_* artifacts/*RESP_*

# 3. Replay del último request
.venv/bin/python tools/replay_recibe_lote.py --env test

# 4. Extraer y verificar lote XML
python3 -c "
import base64, re
with open('artifacts/soap_last_request_SENT.xml', 'r') as f:
    soap = f.read()
b64 = re.search(r'<xDE>(.*?)</xDE>', soap, re.DOTALL).group(1)
open('artifacts/xde.zip', 'wb').write(base64.b64decode(b64))
"
unzip -p artifacts/xde.zip lote.xml > artifacts/lote.xml
```

## Conclusión

Se implementó trazabilidad completa y se corrigió el Content-Type, pero el error 0160 persiste. Se requiere análisis más profundo del XML o contacto con SIFEN para identificar la causa exacta del rechazo.
