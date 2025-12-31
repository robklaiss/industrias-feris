# Reporte de Higiene Post-Merge - Integración Lotes SIFEN

## 1. SANITY MAP (Solo Reporte)

### ¿Dónde se envía el lote?
- **Archivo**: `web/main.py`
- **Función**: `de_send_to_sifen()` (línea 508)
- **Llamada**: `client.recepcion_lote(payload_xml)` (línea 546)
- **Método SOAP**: `SoapClient.recepcion_lote()` en `app/sifen_client/soap_client.py` (línea 964)

### ¿Dónde se guarda dProtConsLote?
- **Archivo**: `web/main.py`
- **Función**: `de_send_to_sifen()` (línea 584)
- **Llamada**: `lotes_db.create_lote(env, d_prot_cons_lote, de_document_id)`
- **Implementación**: `web/lotes_db.py` función `create_lote()` (línea 81)

### ¿Dónde se consulta el lote RAW?
- **Archivo**: `app/sifen_client/lote_checker.py`
- **Función**: `check_lote_status()` (línea 115)
- **Llamada RAW**: `call_consulta_lote_raw()` (línea 147)
- **Implementación RAW**: `tools/consulta_lote_de.py` función `call_consulta_lote_raw()` (línea 212)

### ¿Dónde se muestra en admin?
- **Routes**:
  - `GET /admin/sifen/lotes` → `admin_lotes_list()` (línea 671 en `web/main.py`)
  - `GET /admin/sifen/lotes/{lote_id}` → `admin_lote_detail()` (línea 698)
  - `POST /admin/sifen/lotes/{lote_id}/check` → `admin_lote_check_manual()` (línea 710)
- **Templates**:
  - `web/templates/admin_lotes_list.html`
  - `web/templates/admin_lote_detail.html`

---

## 2. DUPLICACIONES E INCONSISTENCIAS DETECTADAS

### ❌ PROBLEMA 1: Dos funciones P12→PEM (DUPLICACIÓN)

**Ubicaciones**:
1. `tools/consulta_lote_de.py`: `p12_to_pem_files()` (línea 27)
   - Simple, sin fallback OpenSSL
   - Retorna `TempCertPair` (namedtuple)
   
2. `app/sifen_client/pkcs12_utils.py`: `p12_to_temp_pem_files()` (línea 185)
   - Robusto, con fallback OpenSSL para algoritmos legacy
   - Retorna `Tuple[str, str]` (cert_path, key_path)

**Impacto**:
- `lote_checker.py` importa la versión simple desde `tools/consulta_lote_de.py` (línea 19)
- Debería usar la versión robusta de `pkcs12_utils.py` que tiene fallback

**Solución propuesta**: Cambiar import en `lote_checker.py` para usar `p12_to_temp_pem_files` de `pkcs12_utils.py` y adaptar el código que usa `TempCertPair`.

---

### ❌ PROBLEMA 2: Variables de entorno inconsistentes

**Estándar actual (mezclado)**:
- `SIFEN_CERT_PATH` / `SIFEN_CERT_PASSWORD` (usado en `soap_client.py`, `config.py`)
- `SIFEN_SIGN_P12_PATH` / `SIFEN_SIGN_P12_PASSWORD` (usado en `send_sirecepde.py`, `build_sirecepde.py`)

**Uso actual**:
- `lote_checker.py`: `SIFEN_CERT_PATH` o `SIFEN_SIGN_P12_PATH` (línea 123)
- `poll_sifen_lotes.py`: `SIFEN_CERT_PATH` o `SIFEN_SIGN_P12_PATH` (línea 155)
- `consulta_lote_de.py`: `SIFEN_SIGN_P12_PATH` o `SIFEN_CERT_PATH` (línea 270)
- `send_sirecepde.py`: Solo `SIFEN_SIGN_P12_PATH` (línea 361)

**Solución propuesta**: Crear helper unificado en `app/sifen_client/config.py` o `pkcs12_utils.py` que resuelva prioridad:
1. `SIFEN_CERT_PATH` / `SIFEN_CERT_PASSWORD` (estándar)
2. `SIFEN_SIGN_P12_PATH` / `SIFEN_SIGN_P12_PASSWORD` (alias, mantener compatibilidad)

---

### ❌ PROBLEMA 3: Test usa constante incorrecta

**Ubicación**: `tests/test_lote_checker.py` línea 117

**Problema**:
```python
determine_status_from_cod_res_lot("0364"), LOTE_STATUS_EXPIRED_WINDOW
```

**Realidad**:
- `lote_checker.py` línea 211: `0364` → `LOTE_STATUS_REQUIRES_CDC`
- `lotes_db.py` define ambos: `LOTE_STATUS_EXPIRED_WINDOW` y `LOTE_STATUS_REQUIRES_CDC`
- `poll_sifen_lotes.py` línea 117: usa `LOTE_STATUS_EXPIRED_WINDOW` (inconsistente)

**Solución propuesta**: Corregir test para usar `LOTE_STATUS_REQUIRES_CDC` y verificar que `poll_sifen_lotes.py` use la misma constante.

---

## 3. VERIFICACIÓN FLUJO ORIGINAL

### ✅ Cambio documentado
- `web/main.py` línea 511: docstring dice "Envía un documento a SIFEN como lote (siRecepLoteDE)"
- **Antes**: Probablemente usaba `recepcion_de()` (envío individual)
- **Ahora**: Usa `recepcion_lote()` (envío por lote)
- **Razón**: Necesario para obtener `dProtConsLote` y consultar estado del lote

**Estado**: ✅ Documentado en docstring. No hay flujo "directo" adicional que se haya roto.

---

## 4. ROBUSTEZ MÍNIMA

### ✅ Cleanup de temporales PEM
- `lote_checker.py` línea 170-177: `finally` con cleanup ✓

### ✅ Connection: close
- `consulta_lote_de.py` línea 241: Header `"Connection": "close"` ✓

### ✅ Timeouts
- `consulta_lote_de.py` línea 244: `timeout=timeout` en POST ✓
- `lote_checker.py` línea 148: `timeout=timeout` pasado a `call_consulta_lote_raw()` ✓

### ✅ No loguear passwords
- Revisado: No se encontraron logs de passwords ✓

---

## 5. TESTS MÍNIMOS

### ✅ Tests existentes
- `tests/test_lote_checker.py`:
  - `test_validate_prot_cons_lote_valid()` ✓
  - `test_validate_prot_cons_lote_invalid()` ✓
  - `test_parse_lote_response_0361()` ✓
  - `test_parse_lote_response_0362()` ✓
  - `test_parse_lote_response_0364()` ✓ (pero usa constante incorrecta)

**Estado**: Tests existen, solo falta corregir el test de `0364`.

---

## RESUMEN DE CAMBIOS PROPUESTOS (Máximo 6)

### Cambio 1: Usar función robusta P12→PEM en lote_checker.py
**Archivo**: `app/sifen_client/lote_checker.py`
**Líneas**: 19, 138-142
**Cambio**: 
- Cambiar import de `p12_to_pem_files` (tools) a `p12_to_temp_pem_files` (pkcs12_utils)
- Adaptar código que usa `TempCertPair` a tupla `(cert_path, key_path)`
**Por qué**: Usar función con fallback OpenSSL para certificados legacy

### Cambio 2: Helper unificado para variables env de certificado
**Archivo**: `app/sifen_client/pkcs12_utils.py` (nuevo helper)
**Cambio**: Agregar función `get_cert_path_and_password()` que resuelva:
```python
cert_path = os.getenv("SIFEN_CERT_PATH") or os.getenv("SIFEN_SIGN_P12_PATH")
password = os.getenv("SIFEN_CERT_PASSWORD") or os.getenv("SIFEN_SIGN_P12_PASSWORD")
```
**Por qué**: Unificar resolución de env vars en un solo lugar

### Cambio 3: Usar helper unificado en lote_checker.py
**Archivo**: `app/sifen_client/lote_checker.py`
**Líneas**: 122-127
**Cambio**: Reemplazar lógica de resolución de env vars por llamada al helper
**Por qué**: Consistencia y mantenibilidad

### Cambio 4: Corregir test de 0364
**Archivo**: `tests/test_lote_checker.py`
**Línea**: 117
**Cambio**: 
```python
# Antes:
determine_status_from_cod_res_lot("0364"), LOTE_STATUS_EXPIRED_WINDOW

# Después:
determine_status_from_cod_res_lot("0364"), LOTE_STATUS_REQUIRES_CDC
```
**Por qué**: Test debe reflejar el comportamiento real del código

### Cambio 5: Verificar/corregir poll_sifen_lotes.py si usa constante incorrecta
**Archivo**: `tools/poll_sifen_lotes.py`
**Línea**: 117
**Cambio**: Si usa `LOTE_STATUS_EXPIRED_WINDOW` para 0364, cambiarlo a `LOTE_STATUS_REQUIRES_CDC`
**Por qué**: Consistencia con `lote_checker.py`

### Cambio 6: (Opcional) Actualizar imports en consulta_lote_de.py si se elimina p12_to_pem_files
**Archivo**: `tools/consulta_lote_de.py`
**Nota**: Si `p12_to_pem_files` solo se usa en `consulta_lote_de.py`, dejarlo como está (no es duplicación problemática si es uso interno). Si se usa en otros lugares, considerar deprecar y redirigir a `pkcs12_utils.py`.

---

## CHECKLIST DE PRUEBA LOCAL

### 1. Configurar variables de entorno
```bash
export SIFEN_EMISOR_RUC="4554737-8"
export SIFEN_CERT_PATH="/ruta/al/certificado.p12"  # o SIFEN_SIGN_P12_PATH
export SIFEN_CERT_PASSWORD="contraseña"              # o SIFEN_SIGN_P12_PASSWORD
export SIFEN_ENV="test"
```

### 2. Iniciar servidor
```bash
cd tesaka-cv/
source ../.venv/bin/activate
python -m uvicorn web.main:app --reload --host 127.0.0.1 --port 8000
```

### 3. Enviar documento desde UI
- Abrir http://127.0.0.1:8000
- Crear/ver un DE
- Hacer clic en "Enviar a SIFEN"
- Verificar que redirige a `/de/{doc_id}?sent=1`

### 4. Verificar lote en admin
- Abrir http://127.0.0.1:8000/admin/sifen/lotes
- Verificar que aparece el lote con:
  - `d_prot_cons_lote` guardado
  - `status` actualizado (processing/done/requires_cdc/error)
  - `last_cod_res_lot` y `last_msg_res_lot` poblados
  - `attempts` > 0
  - `last_checked_at` con timestamp

### 5. Ejecutar polling una vez
```bash
cd tesaka-cv/
source ../.venv/bin/activate
python -m tools.poll_sifen_lotes --env test --once
```

### 6. Verificar en BD
```bash
sqlite3 tesaka.db "SELECT id, d_prot_cons_lote, status, last_cod_res_lot, attempts, last_checked_at FROM sifen_lotes ORDER BY id DESC LIMIT 1;"
```

---

## NOTAS FINALES

- **No hay cambios críticos de arquitectura necesarios**
- **Duplicaciones son menores y manejables**
- **Tests están presentes, solo falta corrección menor**
- **Flujo end-to-end está funcional**

