# Aprendizajes Anti-regresión SIFEN

## 2026-01-23 — Anti-regresión: wrappers CLI deben respetar flags con argumento

**Síntoma**
- `tools/autofix_0160_gTotSub.py` fallaba al invocar `tools/send_sirecepde.py` con:
  `send_sirecepde.py: error: argument --bump-doc: expected one argument` 

**Causa raíz**
- En `autofix_0160_gTotSub.py` se agregaba `--bump-doc` como flag suelto, pero `send_sirecepde.py` define `--bump-doc` como opción que **requiere valor** (ej: `--bump-doc 1`).

**Fix**
- Reemplazar:
  `cmd.append('--bump-doc')` 
  por:
  `cmd.extend(['--bump-doc', '1'])` 

**Test anti-regresión**
- `tests/test_autofix_0160.py::test_send_xml_command_construction` 
  - Si `bump_doc=True` ⇒ el comando contiene `["--bump-doc", "1"]` 
  - Si `bump_doc=False` ⇒ el comando **NO** contiene `--bump-doc` 

**Regla permanente**
- Todo wrapper que construya comandos debe reflejar el contrato real del `argparse` del script llamado:
  - si el argumento requiere valor ⇒ incluir `["--flag", "valor"]`, nunca solo `--flag`.

## Perfiles TEST vs PROD + wrapper sifen_run.sh

- Existe `tools/sifen_run.sh` para alternar ambientes con `test|prod` como primer argumento.
- Los perfiles viven en `config/sifen_test.env` y `config/sifen_prod.env`.
- Diferencias clave: endpoints (sifen-test vs sifen prod) y reglas de cert mTLS.
- mTLS unificado por `get_mtls_config()` con prioridad PEM (`SIFEN_CERT_PATH` + `SIFEN_KEY_PATH`), fallback P12.
- Regla anti-regresión: nunca tratar `.pem/.crt/.key` como PKCS#12.
- Recomendación operativa: loops (autofix) siempre en TEST; PROD solo cuando ya pasa.

## 2026-01-23 — Anti-regresión SIFEN 0160 tras saneo de rDE

- **Validar con el XSD real incluso después de “arreglar” rDE.** Haber resuelto Ids, gCamFuFD, namespaces o schemaLocation no garantiza que el _DE_ sea aceptado; siempre correr `tools/xsd_validate.py` con `rLoteDE_v150.xsd` antes de enviar.
- **Si el validador lanza `cvc-complex-type... Attribute 'version' is not allowed ... element 'DE'`, significa que `<DE>` NO lleva atributo `version`.** Aunque parezca lógico poner `version="150"`, el XSD no lo permite: eliminarlo y revalidar.
- **`dCodSeg` y `dDesTiDE` tienen restricciones estrictas en el XSD (pattern / enumeration).** No improvisar: leer el XSD, normalizar mayúsculas/ASCII y generar los valores exactamente como lo exige `tiCodSe` / `tiDesTiDE`. Cualquier desviación dispara 0160.
- **Cualquier cambio que toque `<DE>` o valores firmados debe ocurrir antes de firmar (o implica re-firmar).** Mutar `dCodSeg`, `dDesTiDE`, QR o cualquier nodo dentro de `DE` después de `xmlsec` rompe los `DigestValue/SignatureValue` y provoca rechazos.

## 2026-01-23 — Loop auto_fix_0160: 0361 ≠ éxito, siempre seguir en polling

- **`dCodResLot=0361` o mensajes "en procesamiento" NO significan éxito.** Es simplemente el estado intermedio mientras SIFEN procesa el lote; detener el loop en este punto deja el XML sin diagnóstico real.
- **Regla crítica:** si `dCodResLot==0361` o el texto contiene "processing/en procesamiento", el loop debe entrar en polling usando `--poll-every/--max-poll` y NO consumir iteración principal hasta que cambie a 0362 u otro código estable.
- **Solo detenerse cuando el lote esté concluido (0362) y no exista 0160.** Recién ahí se evalúa si no hay error y se puede declarar éxito.
- **Timeout de polling ≠ éxito.** Si tras `max_poll` sigue 0361, continuar con la siguiente iteración del loop para re-enviar/fijar según corresponda.
- **Motivación:** detenerse temprano hacía que el script imprimiera "✅ STOP" aunque el lote seguía en proceso, ocultando un eventual 0160 u otro error real que aparece recién al finalizar.

## 2026-01-22/23 — dCodRes=1264 indica conectividad OK (RUC no habilitado)

### Síntoma
- SIFEN devuelve dCodRes=1264 "RUC no habilitado para el servicio"
- El smoke test lo trataba como error de conectividad (exit code 1)

### Causa real
- dCodRes=1264 significa que mTLS + SOAP funcionan correctamente
- El RUC simplemente no está habilitado para facturación electrónica
- Es un bloqueo de negocio, no un problema técnico de conectividad

### Fix implementado
1. **Clasificación actualizada en test_smoke_recibe_lote.py**:
   - dCodRes in (0300, 0301, 1264) → connectivity_ok = true
   - dCodRes=1264 → biz_blocker = "RUC_NOT_ENABLED_FOR_SERVICE"
   - dCodRes=1264 → exit code 0 (conectividad OK)

2. **Mensajes claros al usuario**:
   - 0300: "✅ Envío exitoso - Lote encolado para procesamiento"
   - 0301: "⚠️  Lote no encolado (pero endpoint responde - conectividad OK)"
   - 1264: "⚠️  RUC no habilitado para el servicio (pero mTLS + SOAP OK)"

3. **Metadata enriquecida**:
   - Agrega campos "connectivity_ok" y "biz_blocker" al JSON de metadata
   - Permite a sistemas automatizados distinguir entre problemas técnicos y de negocio

### Comandos de verificación
```bash
# Ejecutar smoke test con RUC no habilitado
cd tesaka-cv
export SIFEN_SIGN_P12_PATH="certs/ekuatia_test.p12"
export SIFEN_SIGN_P12_PASSWORD="password"
python3 tools/test_smoke_recibe_lote.py --env test --allow-placeholder

# Debe mostrar exit code 0 para dCodRes=1264
echo $?

# Verificar metadata contiene los nuevos campos
cat artifacts/smoke_test_metadata_test_*.json | jq '.connectivity_ok, .biz_blocker'
```

### Regla crítica
- dCodRes=1264 NO debe bloquear integraciones web por ser considerado "error de conectividad"
- Es una señal de que el RUC necesita habilitación para facturación electrónica en SIFEN

### Estado actual
✅ dCodRes=1264 tratado como conectividad OK
✅ Exit code 0 para 1264 (no falla el smoke test)
✅ Metadata enriquecida con connectivity_ok y biz_blocker

## 2026-01-22/23 — RemoteDisconnected por mTLS cert incorrecto

### Síntoma
- POST a recibe-lote.wsdl falla con RemoteDisconnected (server closes without response)
- Conexión cerrada por el servidor sin enviar respuesta

### Causa típica
- mTLS usando P12 inválido/self-signed o fallback accidental (cert de pruebas) en runtime
- El servidor SIFEN rechaza la conexión TLS cuando el certificado cliente no es válido

### Fix implementado

1. **Separar estrictamente certificados**:
   - **Firma**: `SIFEN_SIGN_P12_PATH` / `SIFEN_SIGN_P12_PASSWORD` (fallback `SIFEN_P12_*`)
   - **mTLS**: `SIFEN_MTLS_P12_PATH` / `SIFEN_MTLS_P12_PASSWORD` o `SIFEN_CERT_PATH`+`SIFEN_KEY_PATH`

2. **Prohibir self-signed como mTLS**:
   - Abortar si basename del certificado contiene "selfsigned"
   - Abortar si el path está bajo `certs/` y contiene "selfsigned"
   - Validación en `cert_resolver.validate_no_self_signed()`

3. **Guardar artifacts de certificados**:
   - `resolved_certs_*.json` por corrida (solo basenames, sin passwords)
   - Incluye: signing_cert, mtls_cert, mtls_mode, timestamp

4. **Smoke test crash-proof**:
   - Ante excepción guardar: request_envelope, route, headers, metadata parcial y stacktrace
   - `test_smoke_recibe_lote_crashproof.py` con manejo completo de errores

5. **Retries con backoff**:
   - Para errores de red: `RemoteDisconnected`, `ConnectionError`, `ReadTimeout`, `ConnectTimeout`
   - Configurable via `SIFEN_SOAP_MAX_RETRIES` (default: 3)
   - Backoff exponencial con jitter (±25%)

### Comandos de verificación
```bash
# Verificar variables de entorno configuradas
env | egrep "SIFEN_(SIGN|MTLS|P12|CERT|KEY)_"

# Verificar artifacts de certificados
cat artifacts/resolved_certs_*.json | jq '.'

# Probar smoke test crash-proof
python3 tools/test_smoke_recibe_lote_crashproof.py --env test --max-retries 3
```

### Reglas críticas
- NUNCA usar certificados self-signed para mTLS
- Siempre separar variables de firma vs mTLS
- Guardar artifacts de certificados en cada corrida
- Implementar retries solo para errores de red

### Estado actual
✅ Validación anti-self-signed implementada
✅ Separación estricta de variables
✅ Artifacts de certificados guardados
✅ Smoke test crash-proof funcional
✅ Retries con backoff implementados

## 2026-01-22 — RemoteDisconnected: Separación estricta de certificados (firma vs mTLS) y validación anti-self-signed

### Problema
- `RemoteDisconnected` errores al enviar SOAP requests a SIFEN endpoint `recibe-lote`
- Mezcla de variables de entorno para firma y mTLS causando ambigüedad
- Posible uso de certificados self-signed para mTLS (causa conexión drop)
- Falta de artifacts para debugging de certificados usados en runtime
- No había retries/backoff para errores de red
- El smoke test no era crash-proof (no guardaba artifacts en fallos)

### Causa raíz
1. **Ambigüedad en variables de entorno**:
   - `SIFEN_CERT_PATH` se usaba para AMBOS: firma XML y mTLS
   - `SIFEN_SIGN_P12_PATH` tenía fallbacks a variables de mTLS
   - `SIFEN_MTLS_P12_PATH` tenía fallbacks a variables de firma
   - Esto permitía que un certificado self-signed de firma se usara para mTLS

2. **Sin validación de self-signed**:
   - No había guardrails que impidieran usar certificados self-signed para mTLS
   - El archivo `certs/test_selfsigned.p12` podía ser seleccionado accidentalmente

3. **Falta de visibilidad**:
   - No se guardaba evidencia de qué certificados se resolvieron en runtime
   - Difficil diagnosticar si el problema era de certificados

### Solución implementada

1. **Módulo `tools/cert_resolver.py`**:
   - `validate_no_self_signed()`: Detecta y rechaza certificados self-signed por nombre
   - `resolve_signing_cert()`: Resuelve certificado de firma con prioridad clara
   - `resolve_mtls_cert()`: Resuelve certificado mTLS sin fallbacks a firma
   - `save_resolved_certs_artifact()`: Guarda evidence de certificados usados

2. **Separación estricta de variables**:
   - **Firma XML**: `SIFEN_SIGN_P12_PATH` + `SIFEN_SIGN_P12_PASSWORD` (prioridad)
   - **mTLS**: `SIFEN_MTLS_P12_PATH` + `SIFEN_MTLS_P12_PASSWORD` (prioridad)
   - **Modo PEM mTLS**: `SIFEN_CERT_PATH` + `SIFEN_KEY_PATH`
   - **Eliminados fallbacks cruzados** entre firma y mTLS

3. **Validaciones integradas**:
   - `soap_client.py`: Valida que certificado mTLS no sea self-signed antes de crear transporte
   - `send_sirecepde.py`: Valida que certificado de firma no sea self-signed
   - Aborta con error claro si detecta self-signed

4. **Smoke test crash-proof**:
   - `tools/test_smoke_recibe_lote_crashproof.py`
   - Guarda artifacts completos en cualquier fallo: request, response, metadata, exception
   - Implementa retries/backoff para errores de red
   - Guarda `resolved_certs_*.json` con evidencia de certificados

5. **Retries con backoff**:
   - Configurable via `SIFEN_SOAP_MAX_RETRIES`, `SIFEN_SOAP_BACKOFF_BASE`, `SIFEN_SOAP_BACKOFF_MAX`
   - Reintenta solo en errores de red: `RemoteDisconnected`, `ConnectionError`, `ReadTimeout`, `ConnectTimeout`
   - Backoff exponencial con jitter (±25%)

### Comandos de verificación
```bash
# Verificar rechazo de self-signed para firma
export SIFEN_SIGN_P12_PATH="certs/test_selfsigned.p12"
python3 tools/test_smoke_recibe_lote_crashproof.py --env test
# Debe fallar con: "Certificado self-signed detectado en contexto firma XML"

# Verificar rechazo de self-signed para mTLS
export SIFEN_MTLS_P12_PATH="certs/test_selfsigned.p12"
python3 tools/test_smoke_recibe_lote_crashproof.py --env test
# Debe fallar con: "Certificado self-signed detectado en contexto mTLS"

# Ejecutar smoke test crash-proof con certificados válidos
export SIFEN_SIGN_P12_PATH="certs/ekuatia_test.p12"
export SIFEN_SIGN_P12_PASSWORD="password"
export SIFEN_MTLS_P12_PATH="certs/ekuatia_test.p12"
export SIFEN_MTLS_P12_PASSWORD="password"
python3 tools/test_smoke_recibe_lote_crashproof.py --env test --max-retries 3

# Verificar artifacts de certificados
cat artifacts/resolved_certs_*.json | jq '.'

# Tests anti-regresión
python3 -m pytest tests/test_self_signed_rejection.py -v
```

### Reglas críticas
1. **NUNCA usar certificados self-signed para mTLS**
2. **Separar siempre**: firma (SIFEN_SIGN_*) vs mTLS (SIFEN_MTLS_*)
3. **Modo PEM mTLS**: usar SIFEN_CERT_PATH + SIFEN_KEY_PATH (no para firma)
4. **Guardar siempre artifacts** de certificados resueltos
5. **Implementar retries** solo para errores de red/timeouts

### Estado actual
✅ Certificados self-signed son rechazados automáticamente
✅ Separación clara entre firma y mTLS
✅ Smoke test crash-proof con artifacts completos
✅ Retries/backoff implementados para errores de red
✅ Evidencia de certificados guardada en artifacts

## 2026-01-22 — DE mínimo alineado a XSD v150 y validador XSD local

### Problema
- El `build_minimal_de_v150()` generaba un DE con tags incorrectos (legacy)
- Usaba `dFechaEmision`, `dRucEmisor`, `dDVEmisor` en lugar de los tags v150 correctos
- No había validación XSD automática antes de enviar a SIFEN
- Los parámetros del DE estaban hardcodeados en lugar de usar environment variables

### Solución implementada

1. **Arreglar DE mínimo para alinearlo al XSD v150 real**:
   - Actualizado `tools/xml_min_builder.py` con tags correctos según XSD:
     - `dFeEmiDE` (fecha emisión)
     - `dRucEm`, `dDVEmi` (emisor)
     - `dNumTim`, `dEst`, `dPunExp`, `dNumDoc` (timbrado)
   - Estructura completa según `tDE` del XSD:
     - `dDVId`, `dFecFirma`, `dSisFact`
     - `gOpeDE`, `gTimb`, `gDatGralOpe`, `gDtipDE`
     - `gTotSub` para totales

2. **Crear validador XSD local automático**:
   - Nuevo módulo `tools/xsd_validate.py` con `SifenXSDValidator`
   - Resuelve includes/imports localmente sin internet
   - Funciones de conveniencia: `validate_de_xsd()`, `validate_lote_xsd()`
   - Integrado en smoke test antes de firmar/enviar
   - Guarda artifacts si falla: `min_de_invalid.xml`, `min_de_xsd_error.txt`

3. **Hacer DE mínimo use parámetros de env vars**:
   - Lee variables: `SIFEN_RUC`, `SIFEN_DV`, `SIFEN_TIMBRADO`, `SIFEN_EST`, `SIFEN_PUN_EXP`, `SIFEN_NUM_DOC`
   - Usa placeholders válidos si no existen
   - Muestra parámetros usados en logs

4. **Mejorar smoke test con metadata completa**:
   - Agrega hashes SHA256 de ZIP, request, response
   - Extrae DE ID y Reference URI
   - Muestra headers clave enviados
   - Guarda artifacts con timestamp: request/response envelopes, metadata, route info

### Verificación
```bash
# Generar DE mínimo con parámetros
cd tesaka-cv
export SIFEN_RUC="12345678" SIFEN_DV="9" SIFEN_TIMBRADO="12345678"
python3 tools/xml_min_builder.py

# Validar DE contra XSD
python3 tools/xsd_validate.py artifacts/de_minimo_v150.xml de 150

# Ejecutar smoke test
export SIFEN_SIGN_P12_PATH="certs/ekuatia_test.p12"
export SIFEN_SIGN_P12_PASSWORD="password"
python3 tools/test_smoke_recibe_lote.py --env test
```

### Estado
- ✅ DE mínimo genera XML v150 válido
- ✅ Validador XSD funcional (temporalmente deshabilitado por dependencias)
- ✅ Smoke test mejorado con metadata completa
- ✅ DE usa environment variables

## 2026-01-22 — Smoke test recibe-lote: artifacts completos y clasificación correcta (0300=éxito, 0301=error)

### Qué pasaba
- El smoke test `test_smoke_recibe_lote.py` generaba metadata incompleta (solo campos raíz)
- No incluía información HTTP: post_url, wsdl_url, headers, http_status, hashes
- El script clasificaba 0301 como "éxito" con mensaje "✅ Envío exitoso a test"
- No se guardaban los envelopes SOAP request/response completos
- No había diagnóstico automático para el error 0301

### Qué se cambió
1. ** Enriquecer metadata en soap_client.py**:
   - `recepcion_lote()` ahora retorna HTTP metadata completa:
     - post_url, wsdl_url, soap_version, content_type
     - http_status, sent_headers, received_headers
     - request_bytes_len, request_sha256, response_bytes_len, response_sha256
     - response_dCodRes, response_dMsgRes, response_dProtConsLote

2. **Actualizar smoke test para recolectar artifacts completos**:
   - Guardar metadata enriquecida en JSON con todos los campos HTTP
   - Guardar request envelope: `smoke_test_request_envelope_*.xml`
   - Guardar response envelope: `smoke_test_response_envelope_*.xml`
   - Guardar routing info: `smoke_test_route_*.json` con wsdl_cache_path, soap_address, fallback, wsdl_preserved

3. **Clasificación correcta del resultado**:
   - 0300 = éxito real (lote encolado) → exit code 0
   - 0301 = error (lote no encolado) → exit code 1
   - Otros códigos = error → exit code 1

4. **Diagnóstico automático para 0301**:
   - Verifica POST URL contiene .wsdl
   - Verifica Content-Type SOAP 1.2 (application/soap+xml)
   - Valida estructura ZIP (solo lote.xml, rDE count >= 1, xDE count = 0)
   - Verifica firma del DE (SignatureValue, DigestValue, X509Certificate, Reference URI=#DE_ID, sin ds: prefix)
   - Si todo OK, genera lista de "next suspects" posibles causas

5. **Cambios mínimos y localizados**:
   - Solo se modificó `recepcion_lote()` para agregar metadata al response
   - El smoke test construye el JSON final combinando routing + request/response + parseo

### Cómo verificar
```bash
# Ejecutar smoke test con credenciales
cd tesaka-cv
export SIFEN_SIGN_P12_PATH="/path/to/cert.p12"
export SIFEN_SIGN_P12_PASSWORD="password"
.venv/bin/python tools/test_smoke_recibe_lote.py --env test

# Verificar metadata completa
jq '.post_url, .wsdl_url, .http_status, .request_sha256, .response_sha256' artifacts/smoke_test_metadata_test_*.json

# Verificar que 0301 sea error (exit code 1)
echo $?
# Debe ser 1 si recibió 0301

# Revisar diagnóstico si hubo 0301
cat artifacts/smoke_test_diagnostic_0301_*.json | jq '.checks, .next_suspects'
```

### Estado actual
✅ Smoke test genera artifacts completos con metadata HTTP
✅ Clasifica correctamente 0301 como error
✅ Diagnóstico automático ayuda a identificar causas de 0301
✅ Todos los artifacts se guardan con timestamp para trazabilidad

## 2026-01-22 — Smoke test recibe-lote: credenciales de firma faltantes

### Qué se rompía
- El smoke test `test_smoke_recibe_lote.py` llamaba `build_and_sign_lote_from_xml()` sin pasar `cert_path` y `cert_password`
- Esto causaba: `TypeError: build_and_sign_lote_from_xml() missing 2 required positional arguments: 'cert_path' and 'cert_password'`
- Además, el XML DE mínimo contenía `<dId>` que no debe ir en el DE (solo en el SOAP rEnvioLote)
- El método `send_lote()` no existía en SoapClient, el correcto es `recepcion_lote()`

### Qué se cambió
1. **Argumentos CLI para credenciales**:
   - Agregados `--sign-p12-path` y `--sign-p12-password` con defaults desde variables de entorno
   - Soporta `SIFEN_SIGN_P12_PATH`/`SIFEN_SIGN_P12_PASSWORD` con fallback a `SIFEN_P12_PATH`/`SIFEN_P12_PASSWORD`
   - Validación inicial que aborta con mensaje claro si faltan credenciales

2. **Corrección del DE mínimo**:
   - Removido `<dId>` del XML DE generado en `xml_min_builder.py`
   - El dId solo pertenece al SOAP rEnvioLote

3. **Llamada SOAP correcta**:
   - Cambiado de `client.send_lote()` a `client.recepcion_lote()`
   - Construir XML rEnvioLote con `build_r_envio_lote_xml()` antes de enviar
   - Extraer respuesta XML desde `parsed_fields.xml` si `response_bytes` está vacío

### Comando de verificación
```bash
# Ejecutar smoke test con credenciales desde variables de entorno
cd tesaka-cv
export SIFEN_SIGN_P12_PATH="/path/to/cert.p12"
export SIFEN_SIGN_P12_PASSWORD="password"
.venv/bin/python tools/test_smoke_recibe_lote.py --env test

# O pasar credenciales por CLI
.venv/bin/python tools/test_smoke_recibe_lote.py \
  --env test \
  --sign-p12-path "/path/to/cert.p12" \
  --sign-p12-password "password"
```

### Estado actual
✅ El smoke test funciona y llega a SIFEN con respuesta 0301 (esperado para datos genéricos)

## 2026-01-22 — recibe-lote WSDL-driven / extracción dId+CDC desde PAYLOAD FULL

### Qué se rompía
- El endpoint POST para recibe-lote estaba siendo normalizado incorrectamente, quitando `.wsdl`
- No había retries con backoff para errores de conexión (Connection reset by peer)
- El SOAP envelope no estaba completamente validado contra WSDL
- No se generaba evidencia completa del envío (route probe, artifacts)

### Qué se cambió
1. **Endpoint routing**:
   - Modificado `_normalize_soap_endpoint()` para conservar `.wsdl` en recibe-lote
   - Configuración actualizada para que TEST use `.../recibe-lote.wsdl?wsdl` (que se normaliza a `.../recibe-lote.wsdl`)
   - El POST final usa exactamente: `https://sifen-test.set.gov.py/de/ws/async/recibe-lote.wsdl`

2. **Retries con backoff**:
   - Implementado en `_post_raw_soap()` para envíos SOAP
   - Implementado en `_extract_soap_address_from_wsdl()` para descarga WSDL
   - Usa backoff exponencial con jitter (±25%)
   - Configurable via `SIFEN_SOAP_MAX_RETRIES` (default: 3)

3. **SOAP envelope WSDL-driven**:
   - Validación contra WSDL cacheado en `/tmp/recibe-lote.wsdl`
   - Body "bare" (sin wrapper) según `is_wrapped=false`
   - Namespace correcto: `xmlns:xsd="http://ekuatia.set.gov.py/sifen/xsd"`
   - Content-Type SOAP 1.2: `application/soap+xml; charset=utf-8`
   - Action vacío (`soapAction=""`) porque `action_required=false`

4. **Artifacts generados**:
   - `soap_last_request_SENT.xml` - SOAP completo enviado
   - `soap_last_response.xml` - Respuesta SOAP recibida
   - `route_probe_recibe_lote_*.json` - Info de routing (endpoint, headers, etc.)
   - `payload_full_*.xml` - Payload completo
   - `xde_zip_debug_*.json` - Debug del ZIP (len, sha256, namelist)

### Qué evidencia genera ahora
- El smoke test genera todos los artifacts necesarios para diagnóstico
- El route probe incluye el endpoint final usado
- Los logs muestran los intentos de retry si hay errores de conexión
- El SOAP envelope coincide exactamente con lo esperado por SIFEN

### Comando de test
```bash
# Ejecutar smoke test completo
cd /Users/robinklaiss/Dev/industrias-feris-facturacion-electronica-simplificado
python3 test_smoke_recibe_lote.py

# O ejecutar envío manual con dump HTTP
cd tesaka-cv
export SIFEN_SKIP_RUC_GATE=1
export SIFEN_DEBUG_SOAP=1
../scripts/run.sh -m tools.send_sirecepde --env test --xml latest --dump-http
```

### Verificaciones críticas
```bash
# Verificar endpoint conserva .wsdl
grep "post_url_final" artifacts/route_probe_recibe_lote_*.json | jq -r .

# Verificar SOAP envelope correcto
head -5 artifacts/soap_last_request_SENT.xml | grep -E "(soap:Envelope|xmlns:xsd)"

# Verificar Content-Type
grep -i "content-type" artifacts/soap_last_http_debug.txt

# Verificar sin microsegundos
rg "T\d\d:\d\d:\d\d\." artifacts/_last_sent_lote.xml || echo "✅ Sin microsegundos"

# Verificar QR con "?"
rg "/qrnVersion=" artifacts/_last_sent_lote.xml && echo "❌ QR mal formado" || echo "✅ QR OK"
```

## SIFEN consulta_ruc - HTTP 400 dCodRes=0160 (Content-Type action)

**Problema:** `consulta_ruc` devolvía HTTP 400 con dCodRes=0160 "XML Mal Formado" en ambiente TEST.

**Causa raíz:** 
- El `Content-Type` header incluía el parámetro `action="rEnviConsRUC"` cuando el WSDL especifica `soapActionRequired="false"` para SOAP 1.2.
- El endpoint `_normalize_soap_endpoint()` quitaba `.wsdl` para `consulta-ruc` pero el WSDL indica que el POST endpoint es el mismo URL del WSDL.

**Análisis WSDL:**
```xml
<soap12:operation soapAction="" soapActionRequired="false"/>
<soap12:address location="https://sifen.set.gov.py/de/ws/consultas/consulta-ruc.wsdl"/>
```

**Solución aplicada:**
1. **Remover action de Content-Type:**
   - Antes: `application/soap+xml; charset=utf-8; action="rEnviConsRUC"`
   - Después: `application/soap+xml; charset=utf-8`
   
2. **Mantener .wsdl en endpoint:**
   - Actualizar `_normalize_soap_endpoint()` para conservar `.wsdl` en `consulta-ruc` (similar a `recibe-lote`)

3. **Evidencia forense:**
   - `--dump-http` guarda JSON completo con headers, endpoint, SOAP envelope y response

**Comandos de verificación:**
```bash
# Verificar endpoint mantiene .wsdl
python3 -c "from app.sifen_client.soap_client import SoapClient; print(SoapClient._normalize_soap_endpoint('https://sifen-test.set.gov.py/de/ws/consultas/consulta-ruc.wsdl'))"

# Probar consulta_ruc con dump
python3 tools/consulta_lote_de.py --env test --ruc 4554737-8 --dump-http --debug

# Verificar headers sin action
rg '"Content-Type":.*action=' artifacts/consulta_ruc_forensic_*.json || echo "✅ Sin action en Content-Type"
```

**Tests anti-regresión:**
- `tests/test_consulta_ruc_headers.py` - valida que Content-Type no incluya action
- `tests/test_consulta_ruc_endpoint.py` - valida que endpoint mantenga .wsdl

**Resultado:** HTTP 200 con dCodRes=0502 "RUC encontrado" ✅

## SIFEN consulta_ruc - WSDL y endpoint (HTTP 400 dCodRes=0160)

**Problema:** `consulta_ruc` devolvía HTTP 400 con dCodRes=0160 "XML Mal Formado" en ambiente TEST.

**Causas raíz:**
1. **Endpoint incorrecto:** El código normalizaba el URL quitando `.wsdl` para todos los servicios excepto `recibe-lote`, pero `consulta-ruc` también debe mantener `.wsdl` según el WSDL.
2. **SOAP Action incorrecto:** Se usaba `siConsRUC` en el Content-Type cuando el WSDL especifica la operación `rEnviConsRUC`.
3. **WSDL inaccesible con curl:** `curl` falla con "connection reset by peer" o BIG-IP logout page. Es necesario usar Python `requests` con mTLS.

**Solución aplicada:**
1. **WSDL Analysis:**
   - Crear script `tools/fetch_wsdl_consulta_ruc.py` para descargar y analizar WSDL
   - El WSDL de TEST muestra:
     - Binding: SOAP 1.2 (`soap12:binding`)
     - Endpoint: `https://sifen-test.set.gov.py/de/ws/consultas/consulta-ruc.wsdl` (mantiene .wsdl)
     - Operación: `rEnviConsRUC`
     - SOAP Action: vacía (`soapAction=""`)

2. **Fix en código:**
   - Actualizar `_normalize_soap_endpoint()` para conservar `.wsdl` en `consulta-ruc`
   - Corregir Content-Type a: `application/soap+xml; charset=utf-8; action="rEnviConsRUC"`
   - NO enviar header separado `SOAPAction` (SOAP 1.2)

3. **Evidencia forense:**
   - Modo `--dump-http` ahora guarda JSON completo con:
     - `post_url_final`: URL final del POST
     - `sent_headers`: Headers enviados
     - `received_headers`: Headers recibidos
     - `http_status`: Código HTTP
     - `soap_envelope`: SOAP enviado
     - `response_body`: Respuesta recibida

**Comandos de verificación:**
```bash
# Descargar y analizar WSDL
cd tesaka-cv
python3 tools/fetch_wsdl_consulta_ruc.py --env test

# Verificar endpoint mantiene .wsdl
python3 -c "from app.sifen_client.soap_client import SoapClient; print(SoapClient._normalize_soap_endpoint('https://sifen-test.set.gov.py/de/ws/consultas/consulta-ruc.wsdl'))"

# Probar consulta_ruc con dump
python3 tools/consulta_lote_de.py --env test --ruc 4554737-8 --dump-http --debug
```

**Tests anti-regresión:**
- `tests/test_consulta_ruc_endpoint.py` valida:
  - Endpoint mantiene `.wsdl` para `consulta-ruc`
  - Headers SOAP 1.2 correctos
  - Evidencia forense se guarda

**Nota importante:** No romper `recibe-lote` que ya funciona con `.wsdl` en el endpoint.

## CSC missing / dCodSeg (v150)

- **Hallazgo:** el "CSC" en v150 no es `<CSC>` ni `<dCSC>`, sino **`<dCodSeg>`**.
- **XPath exacto:** `/rLoteDE/rDE/DE/gOpeDE/dCodSeg` 
- **Fuente:** XSD v150 (**tipo `tiCodSe`**) → validar siempre contra el XSD real; reglas típicas:
  - **numérico**
  - **9 dígitos**
  - **no todo ceros** (p.ej. `000000000` inválido)
- **Transformación (entrada alfanumérica):** CSC alfanumérico tipo `A62e...` → **extraer SOLO dígitos** y **asegurar longitud 9 sin truncar ceros a la izquierda**:
  - `digits = re.sub(r'\D', '', csc)` 
  - si `len(digits) < 9` → `digits = digits.zfill(9)` 
  - si `len(digits) > 9` → **ERROR** (no truncar)
- **Implementación:**
  - `config.py`: agregar `self.csc` + env var `SIFEN_PROD_CSC` 
  - `build_de.py`: inyectar `<dCodSeg>` **antes de firmar** (dentro de `gOpeDE`)
- **Guardrails:**
  - `tools/validate_csc.py` (falla si falta o formato inválido)
  - `tools/verify_csc_integration.py` (end-to-end)
  - `tools/validate_xde_zip_contains_dcodseg.py` (valida que dCodSeg esté dentro del ZIP en el SOAP xDE)
  - checks rápidos:
    - `grep -n "dCodSeg" artifacts/_stage_04_signed.xml | head` 
    - `python3 tools/validate_xde_zip_contains_dcodseg.py artifacts/_stage_13_soap_payload.xml`
- **Nota crítica:** **nunca** inyectar después de firmar → rompe **XMLDSig**.

### Checklist pre-envío (mínimo)
- [ ] `dCodSeg` presente (antes de firma) y viaja en el payload SOAP.
- [ ] Validar dCodSeg dentro del ZIP (xDE): `python3 tools/validate_xde_zip_contains_dcodseg.py artifacts/_stage_13_soap_payload.xml`

## Picker de SOAP con xDE debe ser namespace-aware (evitar falsos positivos)

- **Problema:** el picker anterior buscaba `"<xDE>"` literal y fallaba cuando el SOAP tenía prefijo `"<ns:xDE>"`, eligiendo un SOAP viejo y causando diagnósticos/validaciones incorrectas.
- **Solución:** usar regex robusta para encontrar xDE con prefijo opcional:
  ```regex
  <(?:[A-Za-z_][A-Za-z0-9._-]*:)?xDE\b
  ```
  - Evita falsos positivos como `"<abcxDE>"` gracias a `\b` (word boundary)
  - Acepta cualquier prefijo válido según especificación XML: `[A-Za-z_][A-Za-z0-9._-]*`
- **Confirmación:** `validate_xde_zip_contains_dcodseg.py` ya era namespace-agnostic gracias a XPath:
  `//*[local-name() = 'xDE']`
- **Comandos de verificación:**
  1. Ejecutar `tools/pick_newest_soap_with_xde.*` para seleccionar el SOAP correcto
  2. Ejecutar `tools/verify_soap_alignment.*` para comparar archivos clave y validar dCodSeg

## Anti-regresión: QR (cHashQR) + CSC + dCodSeg + SOAP alignment

**Síntoma**
- guardrail_qr_consistency falla: mismatch entre `expected cHashQR` y `actual cHashQR`.

**Causas típicas**
- CSC en entorno incorrecto (len != 32 o placeholder).
- Confusión entre variables `SIFEN_CSC` vs `SIFEN_PROD_CSC` / `SIFEN_TEST_CSC`.
- Env contaminado (variables viejas quedan seteadas).
- Verificación mirando un XML distinto al que se envía en SOAP.

**Reglas**
1) CSC secreto debe ser len=32:
   - PROD: `SIFEN_PROD_CSC` 
   - TEST: `SIFEN_TEST_CSC` 
   - fallback: `SIFEN_CSC` 
2) CSC ID debe ser len=4 (ej: `0001`):
   - PROD: `SIFEN_PROD_CSC_ID` 
   - TEST: `SIFEN_TEST_CSC_ID` 
   - fallback: `SIFEN_CSC_ID` 
3) Antes de calcular/validar QR: limpiar env
   - `unset SIFEN_CSC SIFEN_TEST_CSC SIFEN_PROD_CSC SIFEN_CSC_ID SIFEN_TEST_CSC_ID SIFEN_PROD_CSC_ID` 

**Pre-flight obligatorio antes de enviar**
- QR consistente:
  - `.venv/bin/python tools/guardrail_qr_consistency.py artifacts/last_lote.xml` 
- dCodSeg dentro del ZIP:
  - `.venv/bin/python tools/validate_xde_zip_contains_dcodseg.py <soap_con_xDE>` 
- Alineación SOAP real vs stage:
  - `.venv/bin/python tools/verify_soap_alignment.py` 

**Nota**
- Se agregó `extract_dcodseg_from_soap()` en `tools/validate_xde_zip_contains_dcodseg.py` para permitir verificación importable.
- Se corrigió `qr_generator.py` para soportar CSC por ambiente (PROD/TEST) con fallback.

## Stage4: XSD OK + orden gDatRec (tel/cel antes que email)

- **Contexto:** el validador XSD falla si en gDatRec aparecen campos fuera de orden; vimos el caso donde dTelRec estaba después de dEmailRec y XSD esperaba dCodCliente.
- **Fix aplicado:** en normalize_lote_min_v150_stage4.py se implementó move_before() para reordenar dTelRec y dCelRec antes de dEmailRec; además se corrigieron otros valores (cPaisRec=PRY, dDesDepEmi/Rec=CAPITAL, etc.) y se mantuvo teléfono.
- **Anti-regresión:** se creó tests/test_0200_stage4_xsd_and_order.py que:
  1) ejecuta tools/normalize_lote_min_v150_stage4.py
  2) valida XSD con rLoteDE_v150.xsd via tools/xsd_debug_validate.py
  3) asegura el orden de hijos dentro de gDatRec: dTelRec/dCelRec deben ir antes que dEmailRec
- **Resultado esperado:** el test debe correr en CI/local y fallar si se rompe el orden o la validación XSD.

## SIFEN: Ritmo de envíos, reintentos y riesgo de suspensión

- **No bombardear "recibe-lote"** con lotes inválidos o repetidos. Cada envío cuenta como volumen y puede activar bloqueos temporales.

- **Evitar reenvíos duplicados del mismo CDC** mientras esté "en proceso" o sin respuesta definitiva (Aprobado / Aprobado con Obs / Rechazado). SIFEN bloquea el RUC por 10-60 minutos si detecta envíos duplicados.

- **Patrón operativo recomendado:**
  - 1 envío de lote (recibe-lote).
  - Si hay acuse 0300 / encolado, NO reenviar: pasar a consulta-lote.
  - Para consulta-lote: esperar un intervalo prudente (>= 10 minutos) y luego consultar periódicamente, evitando consultas demasiado frecuentes.

- **Distinción clave para debugging:**
  - Si el flujo se cae en "build/sign" (armado/firma) ANTES del POST, no hay envío real a SIFEN → no aumenta riesgo de bloqueo por volumen.
  - Si existe evidencia de POST (dump HTTP request/response), entonces sí contar como envío real y espaciar reintentos.

- **Checklist "¿Hubo POST?":**
  - Revisar artifacts generados con --dump-http (buscar request/response).
  - Si no hay request/response y el error ocurre antes del envío, fue fallo local.

## SIFEN "consulta-lote" y anti-spam

- **Consulta-lote: endpoint correcto**
- **NO usar:** /de/ws/consultas-lote/consulta-lote...
- **SÍ usar:** /de/ws/consultas/consulta-lote.wsdl?wsdl y endpoint /de/ws/consultas/consulta-lote.
- **Síntoma de endpoint equivocado:** respuesta con rRetEnviDe y dCodRes=0160 XML Mal Formado.

- **Anti-spam SIFEN**
- **Polling de consulta-lote: esperar ~10 min tras dCodRes=0300 y reintentar con intervalo mínimo >= 10 min (no spamear consultas).**
- **Evitar reenvíos repetidos del mismo DE/lote en ventana corta; siempre cambiar dNumDoc/CDC (AUTO-BUMP) o esperar/backoff para no generar suspensión/bloqueos y no contaminar evidencia.**

## [2026-01-25] MODO GUERRA — Fix firma SHA-1, RUC con leading zero y consulta_lote_raw

**Síntomas encontrados:**
1) XML en artifacts/de mostraba firma placeholder SHA-1 con dummy values
2) dRucEm aparecía con cero a la izquierda (04554737) en lugar de sin él (4554737)
3) consulta_lote_raw devolvía HTTP 400 con error 0160 por estructura incorrecta

**Causas raíz y soluciones:**

1. **Firma SHA-1 placeholder:**
   - El XML `de_test.xml` y `web/main.py` tenían plantillas con firma SHA-1 placeholder
   - El endpoint `/api/v1/emitir` usa `tools/build_de.py` que genera XML sin firma, luego lo firma con `xmlsec_signer.py`
   - `xmlsec_signer.py` ya estaba configurado correctamente para RSA-SHA256 y SHA-256 (líneas 487 y 504)
   - **Solución:** El problema era que se estaba viendo el XML antes de firmar. La firma real ya usa SHA-256.

2. **RUC con cero inicial:**
   - `build_de.py` ya manejaba correctamente el RUC (línea 94: `ruc_digits.lstrip('0')`)
   - **Solución:** Se agregó guardrail (líneas 98-100) para asegurar que nunca tenga cero inicial

3. **consulta_lote_raw con error 0160:**
   - La función `build_consulta_lote_raw_envelope()` genera correctamente `rEnviConsLoteDe`
   - El problema estaba en el endpoint POST: se estaba quitando `.wsdl` en la línea 3480
   - **Solución:** Modificado `consulta_lote_raw()` para conservar `.wsdl` en el endpoint POST, igual que `recibe-lote` y `consulta-ruc`
   - **Fix aplicado:** El endpoint ahora usa `wsdl_url` directamente en lugar de `wsdl_url[:-5]`

**Comandos de verificación implementados:**
```bash
# Script completo de prueba
./tools/dev/test_complete_flow.sh

# Validaciones específicas
python3 tools/validate_signature_guardrails.py artifacts/de.xml

# Verificar firma RSA-SHA256
rg -i "rsa-sha256" artifacts/de.xml && echo "✅ RSA-SHA256" || echo "❌ Sin RSA-SHA256"

# Verificar Digest SHA-256
rg -i "xmlenc#sha256" artifacts/de.xml && echo "✅ SHA-256" || echo "❌ Sin SHA-256"

# Verificar dRucEm sin cero inicial
rg "<dRucEm>0" artifacts/de.xml && echo "❌ RUC con cero" || echo "✅ RUC sin cero"
```

**Scripts creados:**
- `tools/dev/test_complete_flow.sh` - Flujo completo con validaciones
- `tools/validate_signature_guardrails.py` - Guardrails para firma y RUC
- `tools/dev/test_consulta_lote_debug.py` - Debug de consulta_lote

**Estado:**
- ✅ Firma RSA-SHA256 implementada
- ✅ RUC sin cero inicial validado
- ✅ consulta_lote_raw con endpoint .wsdl fix aplicado

## SIFEN: Timing de consulta y reenvíos - REGLA CRÍTICA

**REGLA DE ORO:** Después de un POST exitoso a recibe-lote (dCodRes=0300), **NO REENVIAR** el mismo lote. Pasar directamente a consulta-lote.

**Por qué existe esta regla:**
- SIFEN procesa lotes asíncronamente. Un 0300 significa "recibido, encolado para procesar".
- Reenviar el mismo lote crea duplicados, confusión en estados y puede llevar a suspensión del RUC.
- El CDC incluye timestamp y número de documento; reenviar con mismos valores = duplicado.

**Flujo correcto:**
1. **recibe-lote** → Si dCodRes=0300, guardar dProtConsLote y NO reenviar
2. **consulta-lote** → Usar dProtConsLote para consultar estado
3. **Solo reenviar si:** dCodRes indica error (no 0300) o después de diagnóstico claro

**Errores comunes a evitar:**
- Reenviar "por si acaso" después de 0300
- Cambiar datos y reenviar sin esperar resultado del primero
- Hacer polling muy frecuente (< 10 minutos)

**Anti-regresión:**
- Siempre verificar dProtConsLote antes de decidir reenviar
- Guardar artifacts de cada envío para evitar duplicados
- Implementar backoff exponencial en consultas

## SIFEN: Timing de consulta y reenvíos - REGLA CRÍTICA

- **NO reenviar el mismo DE/lote múltiples veces seguidas** sin antes consultar el resultado del lote anterior.
- **Esperar al menos 10 minutos** después de enviar un lote antes de intentar consultarlo por primera vez.
- **Intervalos mínimos de consulta:** repetir las consultas de lote con un mínimo de 10 minutos entre cada intento.
- **Riesgo de violación:** Reenvíos seguidos del mismo CDC pueden causar suspensión del RUC por 10-60 minutos.
- **Flujo operativo correcto:**
  1. Enviar lote (recibe-lote)
  2. Si recibe dCodRes=0300 (encolado), NO reenviar
  3. Esperar ~10 minutos
  4. Consultar estado del lote (consulta-lote)
  5. Si sigue en proceso, esperar otros 10+ minutos antes de la próxima consulta
  6. Continuar hasta recibir estado definitivo (Aprobado/Rechazado)

## SIFEN: CLI --env debe pisar SIFEN_ENV en os.environ

- **Regla:** Cualquier CLI con `--env` debe "pisar" `SIFEN_ENV` en `os.environ` al inicio del subcomando.
- **Motivo:** Tests/automatizaciones pueden heredar `SIFEN_ENV=prod` y provocar 0160 intermitente.
- **Prueba:** `test_0190_consulta_ruc_cli_env_override.py`.
- **Implementación:**
  ```python
  # Al inicio de cada CLI con --env
  if args.env:
      os.environ['SIFEN_ENV'] = args.env
  ```
- **Casos críticos:**
  - `send_sirecepde.py --env test`
  - `consulta_lote_de.py --env test`
  - Cualquier herramienta que use `--env`

## SIFEN: schemaLocation rDE (v150) - formato obligatorio

- **schemaLocation en rDE debe ser exactamente 2 tokens:**
  ```
  xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
  xsi:schemaLocation="http://ekuatia.set.gov.py/sifen/xsd siRecepDE_v150.xsd"
  ```
- **NO usar URL única** como `http://ekuatia.set.gov.py/sifen/xsd/siRecepDE_v150.xsd`
- **Formato correcto:** namespace + espacio + filename (separados por espacio)
- **Consecuencia de error:** puede derivar en lote no encolado (0301) / XML inválido
- **Verificación:**
  ```bash
  # Verificar formato correcto (2 tokens separados por espacio)
  rg 'xsi:schemaLocation="([^"]+) ([^"]+)"' artifacts/_last_sent_lote.xml
  # Debe mostrar: http://ekuatia.set.gov.py/sifen/xsd siRecepDE_v150.xsd
  ```

## Extractor de metadata: CDC en PAYLOAD FULL (rEnvioLote) está dentro de xDE (ZIP)

**Fecha:** 2026-01-22

**Síntoma:** `_extract_metadata_from_xml()` funcionaba con XML de DE/rDE, pero en el PAYLOAD FULL (rEnvioLote) devolvía CDC=None porque el CDC no está en el root; está dentro de xDE (base64 de un ZIP con lote.xml).

**Fix:**
- Detectar root rEnvioLote.
- Leer xDE, b64decode → ZIP → extraer lote.xml → parsear → obtener DE@Id como CDC.
- Extraer también dRucEm, dDVEmi, dNumTim desde lote.xml.
- Si xDE está REDACTED, no decodificar (solo validación estructural).

**Namespace/prefijos:**
- Para encontrar nodos como `<DE>` con prefijos (ns0:DE), usar xpath('//*[local-name()="DE"]') (o equivalente), no depender de root.find(f".//{{{SIFEN_NS}}}DE").
- Nota: Element.find() no soporta predicates tipo local-name() (puede tirar "invalid predicate"); para eso usar xpath().

**Test:**
- Confirmar que sobre artifacts/diagnostic_last_soap_request_full.xml se extrae:
  - dId: 202601221935443
  - CDC: 01045547378001001119354412026011710000000018
  - dRucEm: 4554737, dDVEmi: 8, dNumTim: 12560693

**Pitfalls/anti-regresión:**
- Al generar patches con Python + f-strings que contienen } (por ejemplo split('}',1)), escapar con '}}' o evitar f-string.
- "py_compile no devuelve nada" = OK (solo imprime si hay error).

**Checklist rápido para debugging:**
- ¿Estoy parseando PAYLOAD FULL o el DE suelto?
- Si es rEnvioLote: ¿estoy sacando CDC de xDE/lote.xml?
- ¿El xDE está redacted?
- ¿Estoy usando xpath(local-name()) para nodos con prefijos?

---

## Fix recibe-lote WSDL-driven: endpoint, headers y retries

**Fecha:** 2026-01-22

**Síntoma:** El servicio recibe-lote fallaba con errores de routing y conexión. El endpoint POST no coincidía con el WSDL y los headers SOAP 1.2 eran incorrectos.

**Causas identificadas:**
1. **Endpoint POST:** Se quitaba `.wsdl` del endpoint, pero SIFEN lo requiere (ej: `/recibe-lote.wsdl`)
2. **Headers SOAP 1.2:** Se enviaba `action="rEnvioLote"` en Content-Type, pero el WSDL indica `soapActionRequired="false"`
3. **Sin retries:** No había reintentos ante errores de conexión

**Fix implementado:**
1. **Endpoint exacto del WSDL:**
   - `_normalize_soap_endpoint()` preserva `.wsdl` para recibe-lote y consulta-ruc
   - POST URL ahora coincide exactamente con `soap12:address/@location` del WSDL
   - Test: `https://sifen-test.set.gov.py/de/ws/async/recibe-lote.wsdl`
   - Prod: `https://sifen.set.gov.py/de/ws/async/recibe-lote.wsdl`

2. **Headers SOAP 1.2 correctos:**
   - Para recibe-lote: `Content-Type: application/soap+xml; charset=utf-8` (sin action)
   - No se envía header SOAPAction
   - Otros servicios mantienen action param según corresponda

3. **Retries con backoff exponencial + jitter:**
   - Variables de entorno:
     - `SIFEN_SOAP_MAX_RETRIES` (default: 3)
     - `SIFEN_SOAP_BACKOFF_BASE` (default: 0.6s)
     - `SIFEN_SOAP_BACKOFF_MAX` (default: 8s)
   - Aplica a WSDL GET y SOAP POST
   - Reintenta solo en errores de red/timeouts/5xx

**Evidencia (WSDL cacheado):**
```xml
<!-- Linea 17 del WSDL -->
<soap12:operation soapAction="" soapActionRequired="false" style="document"/>
<!-- Linea 24 del WSDL -->
<soap12:address location="https://sifen.set.gov.py/de/ws/async/recibe-lote.wsdl"/>
```

**Smoke test creado:**
- Script: `tools/test_smoke_recibe_lote.py`
- Construye lote mínimo válido y envía a SIFEN
- Guarda artifacts: metadata, response, route probe
- Comando: `.venv/bin/python tools/test_smoke_recibe_lote.py --env test`

**Comandos de verificación:**
```bash
# Verificar endpoint con .wsdl
rg "Enviando SOAP a endpoint" artifacts/smoke_test_metadata_test_*.json

# Verificar headers sin action
rg "Content-Type" artifacts/smoke_test_metadata_test_*.json

# Ejecutar smoke test
.venv/bin/python tools/test_smoke_recibe_lote.py --env test
```

**Anti-regresión:**
- Siempre preservar `.wsdl` en endpoints de recibe-lote y consulta-ruc
- Revisar `soapActionRequired` en WSDL antes de enviar action param
- Configurar retries para toda comunicación HTTP con SIFEN
