# Flujo Completo: siRecepLoteDE (Envío de Lote a SIFEN)

## Resumen Ejecutivo

Este documento traza el flujo completo desde el endpoint web/CLI hasta la llamada HTTP final para `siRecepLoteDE`, incluyendo dónde se parsea `dCodRes` y dónde se decide reintentar o cortar.

---

## 1. PUNTO DE ENTRADA

### 1.1 Web Endpoint (FastAPI)
**Archivo**: `web/main.py`  
**Función**: `de_send_to_sifen(request, doc_id, mode="lote")` (línea ~607)

**Flujo**:
- Valida `mode` ("lote" o "direct")
- Obtiene documento desde BD: `db.get_document(doc_id)`
- Extrae `de_xml` del documento
- Si `mode == "lote"` → continúa con flujo de lote

**Referencias clave**:
- Línea 664: `if mode == "lote":`
- Línea 665: `from tools.send_sirecepde import build_r_envio_lote_xml, build_and_sign_lote_from_xml`
- Línea 712: `response = client.recepcion_lote(payload_xml)`

### 1.2 CLI (Herramienta de línea de comandos)
**Archivo**: `tools/send_sirecepde.py`  
**Función**: `main()` (línea ~4509) → `send_sirecepde()` (línea 3912)

**Flujo**:
- Parsea argumentos CLI (`--env`, `--xml`, `--dump-http`)
- Llama `send_sirecepde(xml_path, env, artifacts_dir, dump_http)`

---

## 2. CONSTRUCCIÓN Y FIRMA DEL LOTE

### 2.1 Verificación de Dependencias
**Archivo**: `tools/send_sirecepde.py`  
**Función**: `_check_signing_dependencies()` (línea ~2305)

**Acción**:
- Verifica que `lxml` y `xmlsec` estén instalados
- Si faltan → `RuntimeError` con mensaje claro
- Guarda `artifacts/sign_blocked_reason.txt` y `sign_blocked_input.xml`

### 2.2 Construcción del Lote y Firma
**Archivo**: `tools/send_sirecepde.py`  
**Función**: `build_and_sign_lote_from_xml()` (línea 2330)

**Flujo**:
1. **Parsear XML de entrada** (rDE/DE/rEnviDe)
   - Detecta formato por `local-name(root.tag)`
   - Extrae `DE` desde cualquier formato (namespace-agnostic)
   - Soporta: rDE, DE, rEnviDe con xDE base64, rEnviDe con xDE hijos, rLoteDE

2. **Construir árbol lote completo**:
   - Crea `<rLoteDE>` con namespace SIFEN
   - Envuelve `rDE` dentro de `rLoteDE`
   - Aplica `ensure_rde_sifen()` para garantizar default xmlns SIFEN

3. **Firmar el DE** (no el rDE completo):
   - Extrae `DE` del `rDE`
   - Serializa solo `DE` a bytes
   - Llama `sign_de_with_p12()` (de `app/sifen_client/xmlsec_signer.py`)
   - Valida post-firma: `DE Id`, `ds:Signature` dentro de `DE`, algoritmos SHA256, `Reference URI`
   - Reconstruye `rDE` wrapper con `dVerFor=150` y `DE` firmado

4. **Crear ZIP**:
   - Serializa `lote.xml` (rLoteDE con rDE firmado) a bytes UTF-8
   - Crea ZIP con `zipfile.ZipFile(mode='w', compression=ZIP_DEFLATED)`
   - Guarda `lote.xml` dentro del ZIP
   - **IMPORTANTE**: `lote.xml` contiene `<rDE>` directo, NO `<xDE>`

5. **Base64 del ZIP**:
   - Codifica ZIP a base64: `base64.b64encode(zip_bytes).decode('ascii')`

6. **Debug del ZIP**:
   - Llama `_save_zip_debug()` (línea 2111)
   - Guarda `artifacts/zip_debug_YYYYMMDD_HHMMSS.json` con:
     - `zip_bytes_len`, `zip_sha256`, `zip_namelist`
     - Por cada XML: `filename`, `first_200_chars`, `root_tag`, `counts` (xDE, rDE, DE_Id)

**Retorna**: `(zip_base64, lote_xml_bytes, zip_bytes, None)`

### 2.3 Construcción del rEnvioLote
**Archivo**: `tools/send_sirecepde.py`  
**Función**: `build_r_envio_lote_xml()` (línea 3677)

**Flujo**:
1. **Generar dId único de 15 dígitos**:
   - Llama `make_did_15()` (línea 3690)
   - Formato: `YYYYMMDDHHMMSS` (14 dígitos) + 1 dígito random = 15 dígitos
   - **IMPORTANTE**: Ignora el parámetro `did` de entrada, siempre genera uno nuevo

2. **Construir XML rEnvioLote**:
   - Crea `<rEnvioLote>` con namespace SIFEN (prefijo `xsd`)
   - Crea `<dId>` hijo con el dId de 15 dígitos
   - Crea `<xDE>` hijo con el base64 del ZIP
   - Serializa a string UTF-8

**Retorna**: XML string del `rEnvioLote` completo

---

## 3. VALIDACIÓN PREFLIGHT

### 3.1 Preflight Local
**Archivo**: `tools/send_sirecepde.py`  
**Función**: `preflight_soap_request()` (línea 3313)

**Validaciones**:
- Parsea `payload_xml` (rEnvioLote) y verifica estructura
- Extrae `xDE` y valida que sea base64 decodificable
- Decodifica ZIP y verifica que contenga `lote.xml`
- Parsea `lote.xml` y valida:
  - Root es `rLoteDE`
  - Contiene al menos 1 `<rDE>` directo
  - NO contiene `<dId>` (pertenece al SOAP)
  - NO contiene `<xDE>` (pertenece al SOAP)
- Valida estructura del `DE` dentro del `rDE`:
  - `DE` tiene atributo `Id` (CDC)
  - `ds:Signature` está dentro de `DE`
  - `Reference URI` coincide con `#<DE@Id>`

**Si falla**: Guarda `artifacts/preflight_*.xml` y `preflight_zip.zip`, retorna `(False, error_msg)`

---

## 4. ENVÍO SOAP A SIFEN

### 4.1 Cliente SOAP
**Archivo**: `app/sifen_client/soap_client.py`  
**Función**: `recepcion_lote()` (línea 1707)

**Flujo**:

#### 4.1.1 Validaciones Iniciales
- Valida tamaño del XML (línea 1721): `_validate_size(service, xml_renvio_lote)`
- Parsea XML y verifica que root sea `rEnvioLote` (línea 1727-1742)
- Valida `xDE` base64 y ZIP (línea 1754-1802):
  - Decodifica base64
  - Verifica que sea ZIP válido (`zipfile.BadZipFile`)
  - Verifica que contenga `lote.xml`
  - Parsea `lote.xml` para confirmar que es well-formed

#### 4.1.2 Inspección WSDL
- Descarga/usa WSDL cacheado de `recibe_lote` (línea 1805-1842)
- Inspecciona WSDL con `wsdl_introspect`:
  - Determina `operation_name`, `body_root_qname`, `is_wrapped`, `soap_action`, `soap_version`, `target_ns`
- Guarda `artifacts/wsdl_inspected.json` y `diag_wsdl_expectations.txt`

#### 4.1.3 Construcción del SOAP Envelope
- Construye envelope SOAP 1.2 (línea 1893-1940):
  - Namespace: `http://www.w3.org/2003/05/soap-envelope`
  - Header vacío
  - Body según estilo (wrapped o bare):
    - **Wrapped**: Crea wrapper con nombre de operación, dentro `rEnvioLote`
    - **Bare**: `rEnvioLote` va directamente en Body

#### 4.1.4 Headers HTTP
- Headers finales (línea 1966-1970):
  ```
  Content-Type: application/soap+xml; charset=utf-8; action="siRecepLoteDE"
  Accept: application/soap+xml, text/xml, */*
  ```
  - **NO** se envía header `SOAPAction` separado (SOAP 1.2)

#### 4.1.5 Validación Pre-Envio (HARD FAIL)
- Llama `_assert_request_is_valid()` (línea 1944-1650):
  - Parsea `soap_bytes` y extrae `dId` y `xDE`
  - Valida que `xDE` sea base64 decodificable a ZIP válido
  - Extrae `lote.xml` del ZIP y lo guarda en `artifacts/diag_lote_from_request.xml`
  - Valida estructura de `lote.xml`:
    - Root localname, hijos directos, rDE/xDE counts
    - `DE` tiene `Id`
    - `ds:Signature` dentro de `DE`
    - `Reference URI` coincide con `#<DE@Id>`
  - Guarda diagnósticos: `diag_dId.txt`, `diag_xDE.txt`, `diag_lote_structure.txt`, `diag_de_id.txt`, `diag_sig_reference_uri.txt`
  - **Si falla**: `RuntimeError` y NO envía HTTP

#### 4.1.6 Guardar "SOURCE OF TRUTH"
- Guarda bytes exactos del request (línea 1932-1940):
  - `artifacts/soap_last_request_BYTES.bin` (bytes binarios)
  - `artifacts/soap_last_request_SENT.xml` (XML textual)
  - `artifacts/soap_marker_before.txt` (timestamp + nonce antes de HTTP)

#### 4.1.7 POST HTTP
- Llama `session.post()` (línea 2032-2037):
  - URL: WSDL URL sin `?wsdl`
  - Data: `soap_bytes` (SOAP completo con xDE real, sin redactar)
  - Headers: `headers_final` (Content-Type con action)
  - Timeout: `(connect_timeout, read_timeout)`

#### 4.1.8 Dump HTTP (si `dump_http=True`)
- Llama `_save_dump_http_artifacts()` (línea 2040-2048):
  - Guarda `soap_raw_sent_lote_*.xml`
  - Guarda `http_headers_sent_lote_*.json`
  - Guarda `http_response_headers_lote_*.json`
  - Guarda `soap_raw_response_lote_*.xml`

#### 4.1.9 Marcador Post-Envio
- Guarda `artifacts/soap_marker_after.txt` (línea 2050-2061):
  - Timestamp, nonce, `status_code`

---

## 5. PARSEO DE RESPUESTA

### 5.1 Parseo Inicial
**Archivo**: `app/sifen_client/soap_client.py`  
**Función**: `_parse_recepcion_response_from_xml()` (línea 1334)

**Campos extraídos** (namespace-agnostic con XPath `local-name()`):
- `dCodRes`: `find_text('//*[local-name()="dCodRes"]')` (línea 1359)
- `dMsgRes`: `find_text('//*[local-name()="dMsgRes"]')` (línea 1360)
- `dEstRes`: `find_text('//*[local-name()="dEstRes"]')` (línea 1361)
- `dProtConsLote`: `find_text('//*[local-name()="dProtConsLote"]')` (línea 1366) ⭐
- `dTpoProces`: `find_text('//*[local-name()="dTpoProces"]')` (línea 1367)

**Determinación de `ok`** (línea 1371-1372):
```python
codigo = (result.get("codigo_respuesta") or "").strip()
result["ok"] = codigo in ("0200", "0300", "0301", "0302")
```

**Retorna**: Dict con `ok`, `codigo_respuesta`, `mensaje`, `d_prot_cons_lote`, `d_tpo_proces`, etc.

### 5.2 Mapeo a Estado de Documento
**Archivo**: `web/sifen_status_mapper.py`  
**Función**: `map_recepcion_response_to_status()` (línea 33)

**Lógica de decisión** (línea 65-88):
```python
# Si dCodRes == "0300" y dProtConsLote > 0: ENVIADO/ENCOLADO
if codigo == "0300" and d_prot_int and d_prot_int > 0:
    return STATUS_SENT_TO_SIFEN, codigo, mensaje

# Si dCodRes != "0300" (ej 0301) o dProtConsLote == 0: ERROR/RECHAZADO
if codigo != "0300" or (d_prot_int is not None and d_prot_int == 0):
    if codigo == "0301":
        return STATUS_ERROR, codigo, "Lote no encolado para procesamiento"
    else:
        return STATUS_ERROR, codigo, mensaje or "Error en recepción"
```

**Punto crítico**: Si `dCodRes=0301` o `dProtConsLote=0` → **NO se consulta el lote** (no hay protocolo)

---

## 6. GUARDADO Y CONSULTA AUTOMÁTICA

### 6.1 Guardado en BD (Web)
**Archivo**: `web/main.py`  
**Función**: `de_send_to_sifen()` (línea 744-751)

**Acción**:
- Guarda respuesta: `db.update_document_status(doc_id, status, code, message, sirecepde_xml, d_prot_cons_lote)`
- Si `dProtConsLote > 0` (línea 764-795):
  - Guarda lote en BD: `lotes_db.create_lote(env, d_prot_cons_lote, de_document_id)`
  - Consulta automática: `await _check_lote_status_async(lote_id, env, d_prot_cons_lote)`

### 6.2 Consulta Automática de Lote
**Archivo**: `web/main.py`  
**Función**: `_check_lote_status_async()` (línea 859)

**Flujo**:
1. Llama `check_lote_status()` (de `app/sifen_client/lote_checker.py`)
2. Obtiene `dCodResLot`, `dMsgResLot`, `response_xml`
3. Determina estado: `determine_status_from_cod_res_lot(cod_res_lot)`
4. Actualiza lote: `lotes_db.update_lote_status(...)`
5. Actualiza DEs asociados usando `map_lote_consulta_to_de_status()`

**Códigos de lote**:
- `0361`: Lote en procesamiento → `STATUS_PENDING_SIFEN`
- `0362`: Procesamiento concluido → parsea `gResProc` para cada DE
- `0364`: Consulta extemporánea (>48h) → requiere consulta por CDC

---

## 7. DECISIÓN DE REINTENTO/CORTE

### 7.1 Puntos de Corte (NO Reintento)

#### 7.1.1 Dependencias Faltantes
**Archivo**: `tools/send_sirecepde.py`  
**Función**: `_check_signing_dependencies()` (línea 2305)

**Acción**: Si faltan `lxml` o `xmlsec` → `RuntimeError` → **CORTE INMEDIATO**

#### 7.1.2 Preflight Fallido
**Archivo**: `tools/send_sirecepde.py`  
**Función**: `preflight_soap_request()` (línea 3313)

**Acción**: Si preflight falla → retorna `(False, error_msg)` → **CORTE** (no envía a SIFEN)

#### 7.1.3 Validación Pre-Envio Fallida
**Archivo**: `app/sifen_client/soap_client.py`  
**Función**: `_assert_request_is_valid()` (línea 1444)

**Acción**: Si validación falla → `RuntimeError` → **CORTE** (no envía HTTP)

#### 7.1.4 Error HTTP != 200
**Archivo**: `app/sifen_client/soap_client.py`  
**Función**: `recepcion_lote()` (línea 2141-2237)

**Acción**: Si `resp.status_code != 200` y no hay respuesta XML válida → `SifenClientError` → **CORTE**

#### 7.1.5 dCodRes != "0300" o dProtConsLote == 0
**Archivo**: `web/sifen_status_mapper.py`  
**Función**: `map_recepcion_response_to_status()` (línea 69-77)

**Acción**: 
- Si `dCodRes=0301` → `STATUS_ERROR` con mensaje "Lote no encolado"
- Si `dProtConsLote=0` → **NO se consulta el lote** (no hay protocolo)

### 7.2 Puntos de Continuación (Éxito)

#### 7.2.1 dCodRes == "0300" y dProtConsLote > 0
**Archivo**: `web/sifen_status_mapper.py`  
**Función**: `map_recepcion_response_to_status()` (línea 65-67)

**Acción**: Retorna `STATUS_SENT_TO_SIFEN` → se guarda lote y se consulta automáticamente

---

## 8. ARTIFACTS DE DEBUG

### 8.1 Artifacts Generados (si `SIFEN_DEBUG_SOAP=1`)

**Durante construcción**:
- `artifacts/zip_debug_YYYYMMDD_HHMMSS.json` (siempre)
- `artifacts/de_before_sign.xml`
- `artifacts/de_after_sign.xml`
- `artifacts/rde_after_wrap.xml`

**Durante envío**:
- `artifacts/soap_last_request_BYTES.bin` (siempre)
- `artifacts/soap_last_request_SENT.xml` (siempre)
- `artifacts/soap_last_request_REAL.xml` (si `SIFEN_DEBUG_SOAP=1`)
- `artifacts/soap_last_request.xml` (redactado, siempre)
- `artifacts/soap_marker_before.txt` (siempre)
- `artifacts/soap_marker_after.txt` (siempre)
- `artifacts/diag_*.txt` (varios diagnósticos)
- `artifacts/wsdl_inspected.json`
- `artifacts/diag_wsdl_expectations.txt`

**Durante respuesta**:
- `artifacts/soap_last_response.xml`
- `artifacts/last_lote_response_parsed.json` (si `SIFEN_DEBUG_SOAP=1`)
- `artifacts/diag_summary.txt` (resumen completo)

**Si `--dump-http`**:
- `artifacts/soap_raw_sent_lote_*.xml`
- `artifacts/http_headers_sent_lote_*.json`
- `artifacts/http_response_headers_lote_*.json`
- `artifacts/soap_raw_response_lote_*.xml`

---

## 9. RESUMEN DEL FLUJO COMPLETO

```
1. ENTRADA
   ├─ Web: web/main.py::de_send_to_sifen() (línea 607)
   └─ CLI: tools/send_sirecepde.py::main() → send_sirecepde() (línea 3912)

2. VERIFICACIÓN
   └─ tools/send_sirecepde.py::_check_signing_dependencies() (línea 2305)
      └─ Si falla → CORTE

3. CONSTRUCCIÓN Y FIRMA
   └─ tools/send_sirecepde.py::build_and_sign_lote_from_xml() (línea 2330)
      ├─ Parsea XML → extrae DE
      ├─ Construye rLoteDE con rDE
      ├─ Firma DE (solo el DE, no el rDE)
      ├─ Crea ZIP con lote.xml
      ├─ Base64 del ZIP
      └─ Guarda zip_debug.json

4. CONSTRUCCIÓN rEnvioLote
   └─ tools/send_sirecepde.py::build_r_envio_lote_xml() (línea 3677)
      ├─ Genera dId de 15 dígitos (siempre nuevo)
      └─ Construye <rEnvioLote><dId>...</dId><xDE>base64</xDE></rEnvioLote>

5. PREFLIGHT
   └─ tools/send_sirecepde.py::preflight_soap_request() (línea 3313)
      └─ Si falla → CORTE

6. ENVÍO SOAP
   └─ app/sifen_client/soap_client.py::recepcion_lote() (línea 1707)
      ├─ Valida xDE y ZIP
      ├─ Inspecciona WSDL
      ├─ Construye SOAP 1.2 envelope
      ├─ Headers: Content-Type con action="siRecepLoteDE"
      ├─ _assert_request_is_valid() (HARD FAIL si falla)
      ├─ Guarda "SOURCE OF TRUTH" (BYTES.bin, SENT.xml)
      ├─ POST HTTP (session.post)
      └─ Guarda dump HTTP (si dump_http=True)

7. PARSEO RESPUESTA
   └─ app/sifen_client/soap_client.py::_parse_recepcion_response_from_xml() (línea 1334)
      ├─ Extrae dCodRes (línea 1359) ⭐
      ├─ Extrae dMsgRes (línea 1360)
      ├─ Extrae dProtConsLote (línea 1366) ⭐
      └─ Extrae dTpoProces (línea 1367)

8. MAPEO A ESTADO
   └─ web/sifen_status_mapper.py::map_recepcion_response_to_status() (línea 33)
      ├─ Si dCodRes="0300" y dProtConsLote>0 → STATUS_SENT_TO_SIFEN
      └─ Si dCodRes!="0300" o dProtConsLote=0 → STATUS_ERROR (CORTE, no consulta)

9. GUARDADO Y CONSULTA
   └─ web/main.py::de_send_to_sifen() (línea 744-795)
      ├─ Guarda en BD
      └─ Si dProtConsLote>0 → consulta automática (_check_lote_status_async)
```

---

## 10. PUNTOS CRÍTICOS DE DECISIÓN

### 10.1 Dónde se parsea `dCodRes`
- **Primera extracción**: `app/sifen_client/soap_client.py::_parse_recepcion_response_from_xml()` línea 1359
- **Uso en mapeo**: `web/sifen_status_mapper.py::map_recepcion_response_to_status()` línea 51

### 10.2 Dónde se parsea `dProtConsLote`
- **Primera extracción**: `app/sifen_client/soap_client.py::_parse_recepcion_response_from_xml()` línea 1366
- **Uso en decisión**: `web/sifen_status_mapper.py::map_recepcion_response_to_status()` línea 55-63
- **Uso en guardado**: `web/main.py::de_send_to_sifen()` línea 715-730

### 10.3 Dónde se decide NO consultar (CORTE)
- **`dCodRes != "0300"`**: `web/sifen_status_mapper.py` línea 70 → `STATUS_ERROR`
- **`dProtConsLote == 0`**: `web/main.py` línea 754 → NO llama `_check_lote_status_async()`
- **`dCodRes=0301`**: `web/sifen_status_mapper.py` línea 72 → mensaje específico "Lote no encolado"

### 10.4 Dónde se decide consultar (CONTINUACIÓN)
- **`dCodRes == "0300"` y `dProtConsLote > 0`**: `web/main.py` línea 764 → guarda lote y consulta automáticamente

---

## 11. REFERENCIAS CLAVE

### 11.1 Archivos Principales
- `web/main.py`: Endpoint web `/de/{id}/send`
- `tools/send_sirecepde.py`: CLI y funciones de construcción/firma
- `app/sifen_client/soap_client.py`: Cliente SOAP y envío HTTP
- `app/sifen_client/xmlsec_signer.py`: Firma XML con xmlsec
- `web/sifen_status_mapper.py`: Mapeo de respuestas a estados

### 11.2 Funciones Críticas
- `build_and_sign_lote_from_xml()`: Construye lote y firma
- `build_r_envio_lote_xml()`: Construye rEnvioLote con dId y xDE
- `recepcion_lote()`: Envía SOAP a SIFEN
- `_parse_recepcion_response_from_xml()`: Parsea respuesta
- `map_recepcion_response_to_status()`: Mapea a estado

### 11.3 Campos SIFEN
- `dCodRes`: Código de respuesta (0300=OK, 0301=No encolado, etc.)
- `dMsgRes`: Mensaje de respuesta
- `dProtConsLote`: Protocolo de consulta de lote (0 si no encolado)
- `dTpoProces`: Tipo de procesamiento
- `xDE`: Base64 del ZIP que contiene lote.xml
- `rLoteDE`: Root del lote.xml dentro del ZIP
- `rDE`: Documento electrónico dentro del lote

---

## 12. FLUJO DE DATOS (Resumen Visual)

```
XML Input (rDE/DE/rEnviDe)
    ↓
build_and_sign_lote_from_xml()
    ├─ Parsea → DE
    ├─ Construye rLoteDE + rDE
    ├─ Firma DE
    ├─ Crea ZIP (lote.xml)
    └─ Base64 ZIP
    ↓
build_r_envio_lote_xml()
    ├─ Genera dId (15 dígitos)
    └─ Construye <rEnvioLote><dId>...</dId><xDE>base64</xDE></rEnvioLote>
    ↓
preflight_soap_request()
    └─ Valida estructura (si falla → CORTE)
    ↓
recepcion_lote()
    ├─ Valida xDE/ZIP
    ├─ Inspecciona WSDL
    ├─ Construye SOAP 1.2
    ├─ _assert_request_is_valid() (si falla → CORTE)
    └─ POST HTTP
    ↓
_parse_recepcion_response_from_xml()
    ├─ Extrae dCodRes ⭐
    ├─ Extrae dProtConsLote ⭐
    └─ Retorna dict
    ↓
map_recepcion_response_to_status()
    ├─ Si dCodRes="0300" y dProtConsLote>0 → STATUS_SENT_TO_SIFEN
    └─ Si dCodRes!="0300" o dProtConsLote=0 → STATUS_ERROR (CORTE)
    ↓
de_send_to_sifen()
    ├─ Guarda en BD
    └─ Si dProtConsLote>0 → consulta automática
```

---

**Última actualización**: 2025-01-XX  
**Versión**: 1.0

