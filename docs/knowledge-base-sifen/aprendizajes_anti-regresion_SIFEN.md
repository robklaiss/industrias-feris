# Aprendizajes y Anti-regresión — SIFEN

> **Propósito:** Documentar aprendizajes clave del proyecto para evitar regresiones y servir como guía rápida de diagnóstico.
> **Formato:** Cada entrada contiene: Síntoma → Causa → Solución → Comandos de verificación.

---

## Error 0160 (XML Mal Formado) — Digest mismatch por modificar XML después de firmar

### Síntoma
- SIFEN responde HTTP 400 con dCodRes=0160 "XML Mal Formado" aunque XSD local valide.

### Causa raíz
- El XML rDE/lote se modificaba (ensure/sanitize, QR, microsegundos, rDE@Id, etc.) DESPUÉS de firmar, rompiendo Digest/Signature (canonicalización) → 0160.

### Fix implementado en tools/send_sirecepde.py
- Se aplica "Final Signature Step" DESPUÉS de sanitizar y ANTES de rebuild ZIP.
- Se extrae rDE del XML saneado y se firma con la función existente sign_de_with_p12.
- Se reemplaza el rDE por la versión firmada final.
- Se construye el ZIP/base64 (xDE) desde xml_signed_final (post-sanitize + post-final-sign).
- Se guardó un artefacto de debug: _final_signed.xml.

### Guardrails agregados
- A: DE@Id == Reference URI (#Id)
- B: log de SHA256 del XML final
- C: validar ZIP: 1 rDE directo, 0 xDE, Signature presente.

### Nota menor
- Fix del warning regex (usar raw string/escape correcto) para remover microsegundos.

### Regla anti-regresión
**Si el XML cambia después de firmar, hay que re-firmar. El ZIP/xDE debe construirse desde el XML final firmado, nunca desde uno pre-fix.**

### Checklist rápido antes de enviar
- rDE@Id presente y coincide con DE@Id
- Reference URI = #DE@Id
- ZIP contiene lote.xml con rLoteDE→rDE (no xDE) y Signature dentro de rDE

### Comandos de verificación
```bash
# Verificar que no hay rDE con Id
rg -n "<rDE\\b[^>]*\\bId=" -S artifacts/_last_sent_lote.xml artifacts/_stage_10_lote_serialized.xml || true

# Verificar que no hay microsegundos
rg -n "T\\d\\d:\\d\\d:\\d\\d\\." -S artifacts/_last_sent_lote.xml artifacts/_stage_10_lote_serialized.xml || true

# Verificar QR con dFeEmiDE sin microsegundos
rg -n "<dCarQR>.*dFeEmiDE=" -S artifacts/_last_sent_lote.xml | head -n 1
```

---

## Error 0160 "XML Mal Formado" — dVerFor missing

### Síntoma
- SIFEN devuelve error 0160 "XML Mal Formado" pero la firma XML es válida y el SOAP está bien formado.

### Causa real
- El elemento `<dVerFor>150</dVerFor>` no está presente como primer hijo de `<rDE>` en el lote XML enviado a SIFEN.

### Fix aplicado
1. Modificado `_ensure_signature_on_rde` para agregar dVerFor si falta
2. Modificado `build_r_envio_lote_xml` para verificar y agregar dVerFor al ZIP existente
3. Agregado debug output para verificar presencia de dVerFor en cada paso

### Comandos de verificación
```bash
# Extraer lote del SOAP enviado
unzip -p artifacts/soap_last_request_SENT.xml xDE > xDE.zip
unzip -p xDE.zip lote.xml > lote_from_SENT.xml

# Verificar estructura
python3 -c "
import xml.etree.ElementTree as ET
doc = ET.parse('lote_from_SENT.xml')
root = doc.getroot()
NS = {'s': 'http://ekuatia.set.gov.py/sifen/xsd'}
rde = root.find('.//s:rDE', NS)
if rde is not None:
    children = [c.tag.split('}')[-1] for c in rde]
    print('rDE children:', children)
    print('Primer hijo:', children[0] if children else 'NONE')
    dver = rde.find('.//s:dVerFor', NS)
    print('dVerFor encontrado:', dver is not None)
    if dver is not None:
        print('dVerFor value:', dver.text)
"
```

---

## Error 0160 "XML Mal Formado" — Fix "false negative" gCamFuFD validation

### Síntoma
- `validate_gcamfufd_singleton_before_send()` fallaba con "gCamFuFD count=0, esperado=1"
- Pero el XML era válido - gCamFuFD está intencionalmente omitido (Hipótesis 3: puede estar causando 0160)

### Causa real
- La validación era demasiado estricta y exigía siempre 1 gCamFuFD
- El xmlsec_signer.py tiene gCamFuFD comentado (líneas 902-923) por hipótesis de que causa error 0160
- La validación no era namespace-agnostic

### Implementación
1. Se modificó `validate_gcamfufd_singleton_before_send()` para:
   - Usar búsqueda namespace-agnostic (localname)
   - Permitir 0 gCamFuFD (intencionalmente omitido)
   - Si existe, validar que sea singleton y esté en posición correcta
2. Se crearon tests en `tests/test_gcamfufd_validation_namespace.py`

### Comandos de verificación
```bash
# Tests
cd /Users/robinklaiss/Dev/industrias-feris-facturacion-electronica-simplificado
python3 -m pytest -q tests/test_gcamfufd_validation_namespace.py -vv

# Comando que antes fallaba
cd tesaka-cv
export SIFEN_SKIP_RUC_GATE=1
../scripts/run.sh -m tools.send_sirecepde --env prod --xml artifacts/_temp_lote_for_validation.xml --force-resign --dump-http
```

---

## Fix error "too many values to unpack" en re-firma

### Síntoma
Al ejecutar `--force-resign` con `build_and_sign_lote_from_xml`, fallaba con:
```
ValueError: too many values to unpack (expected 3)
```

### Causa real
La función `build_and_sign_lote_from_xml` retorna un tuple de 4 elementos cuando `return_debug=True`:
- `(zip_base64, lote_xml_bytes, zip_bytes, lote_did)`
- Pero los callers esperaban solo 3 elementos

### Implementación
1. Se creó helper `_normalize_build_and_sign_result()` que maneja:
   - str (return_debug=False)
   - tuple[3] (build_lote_passthrough_signed)
   - tuple[4] (build_and_sign_lote_from_xml)
   - tuple[5+] (error)
   - dict con keys estándar

2. Se actualizaron todos los callers en `send_sirecepde_lote()` para usar el helper

3. Se agregaron tests anti-regresión:
   - `tests/test_build_and_sign_return_shape.py`
   - `tests/test_sign_key_path_static.py`

### Comandos de verificación
```bash
cd tesaka-cv
python3 -m pytest -q tests/test_build_and_sign_return_shape.py -vv
python3 -m pytest -q tests/test_sign_key_path_static.py -vv

export SIFEN_SKIP_RUC_GATE=1
../scripts/run.sh -m tools.send_sirecepde --env prod --xml artifacts/_temp_lote_for_validation.xml --force-resign --dump-http
```

---

## Fix QR URL missing "?" causing 0160 hypothesis

### Síntoma
- SIFEN devuelve error 0160 "XML Mal Formado"
- Hipótesis fuerte: El QR dCarQR está mal formado porque falta el "?" luego de /qr

### Causa real encontrada
- En nuestro XML enviado, el QR dCarQR tenía: `https://ekuatia.set.gov.py/consultas/qrnVersion=150`
- El XML de ejemplo oficial tiene: `https://ekuatia.set.gov.py/consultas-test/qr?nVersion=150`
- Faltaba el signo "?" entre "/qr" y "nVersion"

### Implementación del fix
1. Archivo: `app/sifen_client/xmlsec_signer.py`
   - Línea 366: Cambiado de `qr_url = f"{qr_base}{url_params}&cHashQR={qr_hash}"` 
   - A: `qr_url = f"{qr_base}?{url_params}&cHashQR={qr_hash}"`
   - Esto agrega el "?" que faltaba entre la base URL y los parámetros

2. Creado test anti-regresión: `tests/test_qr_url_format.py`
   - Verifica que el QR siempre contenga "?nVersion="
   - Verifica que NO contenga "/qrnVersion=" (sin "?")
   - Testea ambos ambientes (test y prod)

### Comandos de verificación
```bash
# Ver QR en XML firmado
grep -o 'dCarQR>[^<]*' artifacts/_stage_12_from_zip.xml | head -1

# Correr tests
../scripts/run.sh -m pytest -q tests/test_qr_url_format.py -vv
```

---

## Fix final 0160 — Sanitize en el último punto (xml_para_payload) — rDE Id + microsegundos + QR

### Síntoma
- artifacts/_stage_10_lote_serialized.xml contiene `<rDE Id="rDE...">` (prohibido)
- artifacts/_last_sent_lote.xml contiene microsegundos en dFecFirma y dFeEmiDE
- El QR incluye dFeEmiDE con microsegundos, generando URL incorrecta

### Causa real
El XML no se saneaba justo antes del envío, permitiendo:
1. rDE con atributo Id (prohibido por SIFEN)
2. Campos de datetime con microsegundos (T..:..:..XXXXXX)
3. QR generado con datetime sucio

### Implementación
1. Se creó `sanitize_lote_payload()` en `tools/send_sirecepde.py`:
   - Elimina atributo Id de rDE (namespace-agnóstico)
   - Elimina microsegundos de dFecFirma y dFeEmiDE (regex \.\d{1,6})
   - Regenera QR con datos saneados usando build_qr_dcarqr()
   - Guardrails que verifican que el saneamiento fue exitoso

2. Se integró en el flujo justo después de definir xml_para_payload:
   - xml_para_payload = sanitize_lote_payload(xml_para_payload)
   - Guarda debug si falla (artifacts/debug_sanitize_failed_*.xml)

3. Se actualizó para guardar xml saneado como:
   - artifacts/_last_sent_lote.xml (para validación XSD)
   - artifacts/_stage_12_from_zip.xml (para debug)

### Comandos de verificación
```bash
# Verificar que no hay rDE con Id
rg -n "<rDE\\b[^>]*\\bId=" -S artifacts/_last_sent_lote.xml artifacts/_stage_10_lote_serialized.xml || true

# Verificar que no hay microsegundos
rg -n "T\\d\\d:\\d\\d:\\d\\d\\." -S artifacts/_last_sent_lote.xml artifacts/_stage_10_lote_serialized.xml || true

# Verificar QR con dFeEmiDE sin microsegundos
rg -n "<dCarQR>.*dFeEmiDE=" -S artifacts/_last_sent_lote.xml | head -n 1
```

---

## [2026-01-17] Fix definitivo error 0160 + regla RUC sin DV + validaciones XML v150

### 1) Bugfix 0160 (XML mal formado)
- Se resolvió el error 0160 restaurando un commit estable de `tools/send_sirecepde.py` y re-aplicando correctamente el fix de "rebuilt ZIP".
- Regla anti-regresión: ante cambios de empaquetado/zip/envelope, correr un "smoke send" que verifique que SIFEN ya no devuelve 0160.

### 2) Bugfix 0160 en consulta_ruc por manejo de RUC
- Causa: si el usuario provee un RUC sin DV (ej: "4554737"), el código NO debe truncar dígitos (no convertirlo en 6 dígitos).
- Regla: aceptar ambos formatos:
  - "4554737" (sin DV) → usar tal cual como RUC (sin DV)
  - "4554737-8" (con DV) → extraer DV correctamente, y derivar RUC sin DV cuando el WS lo requiera.
- Nota de dominio: guías DNIT/Marangatu y formularios indican "RUC sin dígito verificador (DV)" para estos trámites.

### 3) Checklist XML correcto (v150)
- `<rLoteDE>` sin prefijos
- `<rDE>` sin prefijos
- `<dVerFor>150</dVerFor>` como primer hijo de `<rDE>` 
- `<Signature>` sin prefijos
- Regla anti-regresión: añadir un test/validador que falle si aparece un namespace/prefijo inesperado en esos nodos.

### 4) Estado actual esperado
- `consulta_ruc` devuelve 0502 "RUC encontrado" cuando el request está bien.
- Si `dRUCFactElec='N'`, el bloqueo ya no es técnico: requiere habilitar el RUC como facturador electrónico en Marangatu/SIFEN.

### Cómo detectar rápido si es técnico vs administrativo
- 0160 → casi siempre estructura XML/namespace/firma/envelope
- 0502 + dRUCFactElec=N → habilitación administrativa pendiente

### INVARIANTES (anti-regresión)
- INVARIANT-0160-XML: si aparece 0160, revisar namespaces/prefijos y orden de `<dVerFor>` antes de tocar lógica de negocio.
- INVARIANT-RUC: RUC sin DV nunca se trunca; si viene con DV, extraer DV; si viene sin DV, usar tal cual.
- INVARIANT-V150-NO-PREFIX: `<rLoteDE>`, `<rDE>`, `<Signature>` deben ir sin prefijos.
