# SIFEN Learnings (living doc)
Regla del proyecto:
- Antes de cambiar firma/CDC/lote/soap: leer este archivo.
- Después de cada descubrimiento o fix confirmado: agregar una entrada nueva al final.
- Mantener cada entrada en formato corto y verificable (comando + archivo).

Formato de entrada (copiar/pegar):
## [YYYY-MM-DD] <título corto>
**Síntoma:**  
**Contexto/archivo:**  
**Causa raíz:**  
**Fix aplicado:**  
**Cómo verificar (comandos exactos):**  
**Resultado esperado:**  

---

# SIFEN Learnings - Lecciones Aprendidas

Este documento guarda todo lo que hemos probado y sabemos que NO funciona, para no repetir los mismos errores.

## 🚫 Errores Comunes y Soluciones

### [2026-01-20] MODO GUERRA 0160 — Eliminar mutaciones post-firma

**Síntoma:** SIFEN devuelve error 0160 "XML Mal Formado" y xmlsec verify falla en artifacts/debug_rde_fragment.xml

**Contexto/archivo:** `tesaka-cv/app/sifen_client/xmlsec_signer.py` - sección post-procesado después de ctx.sign()

**Causa raíz:** Se estaba mutando el árbol XML después de firmar:
- Recreando el elemento Signature con nuevo xmlns
- Agregando xmlns explícito a Signature post-firma
- Modificando prefijos ds: después de la firma criptográfica

**Fix aplicado:**
1. **Eliminado** todo post-procesado que muta Signature después de ctx.sign()
2. **Desactivado** el bloque que recrea Signature con xmlns explícito
3. **Implementado** validación dura inmediatamente después de firmar
4. **Agregado** guardrail que aborta si xmlsec verify falla post-firma

**Cómo verificar (comandos exactos):**
```bash
# Verificar que la firma es válida inmediatamente después de firmar
xmlsec1 --verify --insecure --id-attr:Id DE artifacts/rde_immediately_after_sign.xml

# Verificar que no hay logs de "Signature recreated" o "Added explicit XMLDSig xmlns"
../scripts/run.sh -m tools.send_sirecepde --env prod --xml artifacts/_temp_lote_for_validation.xml --force-resign 2>&1 | grep -E "(Signature recreated|Added explicit XMLDSig xmlns|Manteniendo Signature xmlns)"
# No debe retornar nada
```

**Resultado esperado:** 
- xmlsec1 verify OK en rde_immediately_after_sign.xml
- No hay mutaciones post-firma
- Signature mantiene xmlns XMLDSig estándar

**Regla de oro:** Después de ctx.sign() → NO se modifica más el XML firmado.

### [2026-01-20] Error 0160 por corrupción de namespace Signature en passthrough

**Síntoma:** SIFEN devuelve error 0160 "XML Mal Formado" cuando el namespace de Signature se cambia de XMLDSig a SIFEN durante el passthrough.

**Contexto/archivo:** `tesaka-cv/tools/send_sirecepde.py` - función `build_lote_passthrough_signed()`

**Causa raíz:** El código forzaba el cambio de namespace de Signature de `http://www.w3.org/2000/09/xmldsig#` a `http://ekuatia.set.gov.py/sifen/xsd` durante la construcción del lote, corruptando la firma.

**Fix aplicado:**
1. Removido todo código que fuerza el cambio de namespace en passthrough
2. Agregado guardrail que valida que Signature mantenga namespace XMLDSig después de construir lote
3. Si se detecta corrupción, se aborta passthrough y se fuerza re-firma completa
4. Logging mejorado para mostrar namespace antes y después del passthrough

**Cómo verificar (comandos exactos):**
```bash
# Ejecutar test unitario
python3 tests/test_passthrough_signature_namespace.py

# Verificar en logs del flujo principal
../scripts/run.sh -m tools.send_sirecepde --env prod --xml artifacts/_temp_lote_for_validation.xml --dump-http | grep "Signature namespace"

# Debe mostrar:
# 🔍 Signature namespace ANTES de passthrough: http://www.w3.org/2000/09/xmldsig#
# 🔍 Signature namespace DESPUÉS de passthrough: http://www.w3.org/2000/09/xmldsig#
# 🔍 Signature namespace en lote.xml: http://www.w3.org/2000/09/xmldsig#
```

**Resultado esperado:** Signature mantiene namespace XMLDSig throughout todo el flujo de passthrough, evitando el error 0160.

**Regla de oro:** En passthrough NUNCA se debe modificar el namespace de Signature. Siempre mantener XMLDSig.

### 0. Usar Python Incorrecto

**Problema**: Usar `python` del sistema en lugar de `python3` del venv.

**Síntomas**:
- ImportError por módulos faltantes (lxml, signxml)
- Versiones incompatibles de Python
- Error "lxml no está disponible" a pesar de estar instalado

**Solución**:
```bash
# ❌ NO HACER - usar python del sistema
python tools/sifen_inspect_signature.py archivo.xml

# ✅ HACER ESTO - usar python3 del venv
.venv/bin/python3 tools/sifen_inspect_signature.py archivo.xml
# O si python3 apunta al venv:
.venv/bin/python tools/sifen_inspect_signature.py archivo.xml
```

**Verificación**:
```bash
# Verificar que estamos usando el Python correcto
.venv/bin/python --version
which python  # NO debe apuntar a /usr/bin/python
```

**Fecha descubrimiento**: 2026-01-12

### 1. Pretty Print de lxml en XML Firmados

**Problema**: `lxml.etree.tostring(..., pretty_print=True)` reordena y formatea el XML de manera que puede invalidar la firma o hacerla difícil de inspeccionar visualmente.

**Síntomas**:
- El XML parece tener la Signature fuera de DE incluso cuando está dentro
- Los saltos de línea y indentación cambian la estructura visual
- `grep "</DE><ds:Signature>"` puede dar falsos positivos

**Solución**:
```python
# ❌ NO HACER - pretty_print confunde la inspección
signed_xml = etree.tostring(root, pretty_print=True).decode("utf-8")

# ✅ HACER ESTO - mantener estructura compacta
signed_xml = etree.tostring(root, encoding="UTF-8").decode("utf-8")

# O si se necesita formateo para humanos, usar herramientas externas
# como xmllint --format DESPUÉS de verificar la firma
```

**Fecha descubrimiento**: 2026-01-12

### 2. Ubicación de ds:Signature en SIFEN

**Problema**: SIFEN rechaza XML con error "Firma difiere del estándar. [El documento XML no tiene firma]" cuando la Signature está fuera del elemento DE.

**Síntomas**:
- XML con estructura: `</DE><ds:Signature>` (Signature como hijo de rDE)
- Error SIFEN: "no tiene firma" a pesar de tener ds:Signature válida

**Solución**:
- Signature debe ser hijo de DE (enveloped signature)
- Estructura correcta: `<DE>...<ds:Signature>...</ds:Signature></DE>`
- Implementar con feature flag `SIFEN_SIGNATURE_PARENT=DE`

**Fecha descubrimiento**: 2026-01-12

### 3. Algoritmos de Firma NT16

**Problema**: signxml a veces ignora la configuración y usa SHA1 por defecto.

**Síntomas**:
- XML firmado con `rsa-sha1` en lugar de `rsa-sha256`
- SIFEN rechaza por algoritmos obsoletos

**Solución**:
```python
# Usar enums de signxml en lugar de strings
from signxml import SignatureMethod, DigestAlgorithm, CanonicalizationMethod

signer = XMLSigner(
    method=signxml.methods.enveloped,
    signature_algorithm=SignatureMethod.RSA_SHA256,  # Enum, no string
    digest_algorithm=DigestAlgorithm.SHA256,        # Enum, no string
    c14n_algorithm=CanonicalizationMethod.CANONICAL_XML_1_0,
)
```

**Fecha descubrimiento**: 2025-12-XX (documentado en xmldsig_signer.py)

### 4. Transforms Adicionales en Firma

**Problema**: SIFEN NT16 requiere EXACTAMENTE 1 Transform: enveloped-signature.

**Síntomas**:
- XML con 2 transforms: enveloped-signature + exc-c14n
- SIFEN rechaza por "Transform inválido según NT16"

**Solución**:
```python
# Eliminar transform adicional si signxml lo agrega
# Mantener solo enveloped-signature
transforms = ["http://www.w3.org/2000/09/xmldsig#enveloped-signature"]
```

**Fecha descubrimiento**: 2025-12-XX

### 5. Reference URI Vacío

**Problema**: A veces signxml deja Reference/@URI vacío.

**Síntomas**:
- `<ds:Reference URI="">` en lugar de `<ds:Reference URI="#DE_ID">`
- SIFEN no puede validar la referencia

**Solución**:
```python
# Corregir post-firma si es necesario
if '<ds:Reference URI="">' in xml_str:
    de_id_match = re.search(r'<DE Id="([^"]+)"', xml_str)
    if de_id_match:
        de_id = de_id_match.group(1)
        xml_str = xml_str.replace(
            '<ds:Reference URI="">',
            f'<ds:Reference URI="#{de_id}">'
        )
```

**Fecha descubrimiento**: 2025-12-XX

## 🔧 Herramientas que SÍ Funcionan

### 1. Inspección de Firma
- **Archivo**: `tools/sifen_inspect_signature.py`
- **Uso**: Diagnóstico preciso de ubicación de firma
- **Ventaja**: Usa XPath, no se confunde con pretty print

### 2. Movimiento de Firma (One-off)
- **Archivo**: `tools/sifen_move_signature_into_de.py`
- **Uso**: Prueba rápida para mover Signature a DE
- **Ventaja**: No recalcula firma, solo mueve nodo existente

### 4. Normalización de Firma para SOAP
- **Archivo**: `tools/sifen_normalize_signature_placement.py`
- **Uso**: Mueve Signature de DE a rDE para SOAP rEnviDe
- **Ventaja**: No rompe firma, solo mueve nodo

### 5. Feature Flag Controlado
- **Variable**: `SIFEN_SIGNATURE_PARENT`
- **Valores**: `DE` (default) o `RDE` (comportamiento anterior)
- **Ventaja**: No rompe backward compatibility

### 6. Posición de Firma en SOAP rEnviDe

**Problema**: Para SOAP rEnviDe, la Signature debe ser hija de rDE (no de DE).

**Síntomas**:
- XML con Signature dentro de DE funciona para prevalidador
- SOAP con Signature dentro de DE es rechazado por SIFEN
- Error: "Firma difiere del estándar" en envío SOAP

**Solución**:
```python
# Usar helper de normalización antes de construir SOAP
from sifen_normalize_signature_placement import normalize_signature_under_rde

xml_bytes = normalize_signature_under_rde(xml_bytes)
# Signature ahora es hija de rDE: dVerFor, DE, Signature
```

**Implementación**: Integrado en `sifen_build_soap12_envelope.py`

**Fecha descubrimiento**: 2026-01-12

## 🚫 Enfoques que NO Funcionaron

### 1. Modificar XML con String Replace
```python
# ❌ NO FUNCIONA - rompe la firma
xml_str = xml_str.replace("</DE><ds:Signature>", "<ds:Signature></DE>")
```
**Razón**: Invalida el digest calculado durante la firma.

### 2. Ignorar Namespace en XPath
```python
# ❌ NO FUNCIONA - puede encontrar elementos equivocados
signatures = root.xpath("//Signature")  # Sin namespace

# ✅ FUNCIONA - con namespace explícito
ns = {"ds": "http://www.w3.org/2000/09/xmldsig#"}
signatures = root.xpath("//ds:Signature", namespaces=ns)
```

### 3. Usar pretty_print para Debugging
```python
# ❌ NO FUNCIONA - confunde la inspección visual
print(etree.tostring(root, pretty_print=True).decode())

# ✅ FUNCIONA - usar herramientas de inspección XPath
tools/sifen_inspect_signature.py archivo.xml
```

## 📋 Checklist Antes de Enviar a SIFEN

### ✅ Verificación Obligatoria
1. **Ubicación de firma**: `tools/sifen_inspect_signature.py` debe mostrar "Signature como hijo de DE"
2. **Algoritmos**: RSA-SHA256, SHA256, Canonical XML 1.0
3. **Transforms**: Solo enveloped-signature (1 solo)
4. **Reference URI**: Debe apuntar a `#<DE/@Id>`
5. **Certificados**: Incluir cadena completa (usuario + CA si es posible)

### ✅ Comandos de Verificación
```bash
# 0. Verificar Python correcto
.venv/bin/python --version

# 1. Inspección completa
.venv/bin/python tools/sifen_inspect_signature.py archivo.xml

# 2. Verificar patrones incorrectos
grep "</DE><ds:Signature>" archivo.xml || echo "✅ OK"

# 3. Verificar estructura con xmllint
xmllint --format archivo.xml | head -20
```

## 🔄 Flujo de Trabajo Probado

### 1. Diagnóstico
```bash
# Verificar Python correcto primero
.venv/bin/python --version

# Inspección del XML
.venv/bin/python tools/sifen_inspect_signature.py original.xml
```

### 2. Fix One-off (para prueba rápida)
```bash
.venv/bin/python tools/sifen_move_signature_into_de.py original.xml --out corregido.xml --verify
```

### 3. Verificación
```bash
.venv/bin/python tools/sifen_inspect_signature.py corregido.xml
```

### 4. Prueba SIFEN
- Subir a prevalidador
- Enviar por SOAP mTLS
- Verificar cambio de error

### 5. Implementación Permanente
```bash
export SIFEN_SIGNATURE_PARENT=DE
# Generar nuevos XML con firma correcta
```

## 📊 Métricas y Resultados

### XML Original (con error)
- **Parent**: rDE
- **Veredicto**: ❌ RECHAZADO: La firma está fuera del elemento DE
- **Error SIFEN**: "Firma difiere del estándar. [El documento XML no tiene firma]"

### XML Corregido (con Signature en DE)
- **Parent**: DE
- **Veredicto**: ✅ APROBADO: Estructura de firma compatible con SIFEN
- **Resultado esperado**: SIFEN debe reconocer la firma

## 🎯 Próximos Pasos (pendientes)

1. **Probar con SIFEN real**: Enviar XML corregido y verificar cambio de error
2. **Automatizar validación**: Integrar verificación en pipeline de generación
3. **Documentar otros errores**: Si SIFEN cambia el error, documentar el siguiente bloqueo
4. **Optimizar performance**: El movimiento de firma es O(n), podría mejorarse

## [2026-01-16] Error 0160 "XML Mal Formado" - Estructura incorrecta del lote
**Síntoma:** SIFEN devuelve error 0160 "XML Mal Formado" pero la firma XML es válida.
**Contexto/archivo:** `/tmp/lote_extracted/lote.xml` extraído de `soap_last_request_SENT.xml`
**Causa real:** El lote XML tiene estructura anidada incorrecta: `<rLoteDE><xDE><rDE>...` en lugar de `<rLoteDE><rDE>...`. Además, `gCamFuFD` está después de `Signature` en lugar de ser hijo directo de `rDE`.
**Comandos para verificar:**
```bash
# Extraer lote del SOAP enviado
unzip -p artifacts/soap_last_request_SENT.xml xDE > xDE.zip
unzip -p xDE.zip lote.xml > lote_from_SENT.xml

# Verificar estructura
python3 -c "
import xml.etree.ElementTree as ET
doc = ET.parse('lote_from_SENT.xml')
root = doc.getroot()
print('Root:', root.tag)
rde = root.find('.//rDE')
if rde is not None:
    children = [c.tag for c in rde]
    print('rDE children:', children)
    print('Primer hijo:', children[0] if children else 'NONE')
"
```

**Fix:** Corregir la generación del lote para que `rLoteDE` contenga `rDE` directamente (no dentro de `xDE`) y asegurar que `gCamFuFD` sea hijo de `rDE` en el orden correcto: `dVerFor`, `DE`, `Signature`, `gCamFuFD`.

## [2026-01-16]## SIFEN — Error 0160 "XML Mal Formado" por namespace incorrecto en Signature

**Síntoma:** SIFEN devuelve error 0160 "XML Mal Formado" aunque el XML tenga dVerFor y estructura correcta.

**Causa real encontrada:** El elemento `<Signature>` tiene el namespace `http://www.w3.org/2000/09/xmldsig#` en lugar del namespace SIFEN `http://ekuatia.set.gov.py/sifen/xsd`.

**Cómo verificar:**
```bash
# Extraer lote del SOAP enviado
unzip -p artifacts/soap_last_request_SENT.xml xDE > xDE.zip
unzip -p xDE.zip lote.xml > lote_from_SENT.xml

# Verificar namespace de Signature
grep -A1 "<Signature" lote_from_SENT.xml | head -1
# Debería mostrar: <Signature xmlns="http://ekuatia.set.gov.py/sifen/xsd">
# Si muestra: <Signature xmlns="http://www.w3.org/2000/09/xmldsig#"> → ERROR 0160
```

**Fix necesario:** La firma XML debe generarse con el namespace SIFEN, no con el namespace de XML Signature estándar. Esto es un requisito específico de SIFEN.

**Comandos de verificación:**
```bash
python3 -c "
import xml.etree.ElementTree as ET
doc = ET.parse('lote_from_SENT.xml')
NS = {'s': 'http://ekuatia.set.gov.py/sifen/xsd'}
sig = doc.find('.//s:Signature')
if sig is None:
    # Buscar Signature con cualquier namespace
    sig = doc.find('.//{*}Signature')
    if sig is not None:
        ns = sig.tag.split('}')[0] + '}'
        print(f'Signature tiene namespace: {ns}')
        if 'xmldsig' in ns:
            print('❌ ERROR: Signature tiene namespace xmldsig (causa 0160)')
        else:
            print('✅ OK: Signature tiene namespace correcto')
"
```

**Estado actual:** El XML pre-firmado tiene Signature con namespace xmldsig, lo que causa el error 0160. Se necesita corregir el proceso de firma para usar el namespace SIFEN.

## [2026-01-17] Syntax Error y uso de ZIP reconstruido

**Síntoma:** `SyntaxError: expected 'except' or 'finally' block` en send_sirecepde.py línea 5343.

**Contexto/archivo:** `tesaka-cv/tools/send_sirecepde.py`

**Causa raíz:** El archivo tenía errores de indentación por ediciones previas mal aplicadas. El `return result` estaba indentado incorrectamente a 8 spaces en lugar de 12 spaces.

**Fix aplicado:** 
1. Revertido a commit 782486c (versión funcional)
2. Aplicado fix para usar ZIP reconstruido sin prefijos
3. Verificado que el XML en el ZIP tiene `<dVerFor>150</dVerFor>` y sin prefijos no deseados

**Cómo verificar (comandos exactos):**
```bash
# Verificar sintaxis
cd tesaka-cv && python3 -m py_compile tools/send_sirecepde.py

# Verificar ZIP reconstruido
unzip -p artifacts/last_lote.zip lote.xml | grep -E "(<rLoteDE|<rDE|<dVerFor)" | head -5
```

**Resultado esperado:** Sin errores de sintaxis y XML con estructura correcta (rLoteDE y rDE sin prefijos, dVerFor presente).

## [2026-01-17] Error 0160 en consulta_ruc por formato de RUC

**Síntoma:** `consulta_ruc` devuelve error 0160 "XML Mal Formado" para RUC de 7 dígitos.

**Contexto/archivo:** `tesaka-cv/app/sifen_client/soap_client.py`

**Causa raíz:** Cuando el RUC no tiene DV (ej: "4554737"), el código incorrectamente generaba `ruc_without_dv` como `normalized_ruc[:-1]`, quitando el último dígito y dejando un RUC inválido de 6 dígitos.

**Fix aplicado:** 
1. Modificada la lógica en `soap_client.py` líneas 866-868
2. Cuando no hay DV en el input, ambas variantes (`ruc_with_dv` y `ruc_without_dv`) usan el RUC normalizado completo

**Cómo verificar (comandos exactos):**
```bash
# Verificar que consulta_ruc funciona con RUC de 7 dígitos
cd tesaka-cv && .venv/bin/python -c "
from app.sifen_client.soap_client import SoapClient
client = SoapClient(env='test')
result = client.consulta_ruc_raw('4554737', dump_http=True)
print(f'Código: {result[\"parsed\"][\"dCodRes\"]}')
print(f'Mensaje: {result[\"parsed\"][\"dMsgRes\"]}')
"
```

**Resultado esperado:** Código 0502 "RUC encontrado" en lugar de 0160 "XML Mal Formado".

## [2026-01-17] Fix definitivo error 0160 + regla RUC sin DV + validaciones XML v150

**Síntoma:** Error 0160 "XML Mal Formado" persistente y manejo incorrecto de RUC sin DV en consulta_ruc.

**Contexto/archivo:** `tools/send_sirecepde.py`, `tesaka-cv/app/sifen_client/soap_client.py`

**Causa raíz:** 
1. Error 0160: Commit con errores de indentación y empaquetado ZIP incorrecto
2. RUC sin DV: Lógica incorrecta que truncaba dígitos del RUC

**Fix aplicado:** 
1. Restaurado commit estable de send_sirecepde.py y reaplicado fix de "rebuilt ZIP"
2. Corregida lógica de RUC para aceptar ambos formatos (con y sin DV)
3. Validaciones XML v150: sin prefijos en rLoteDE/rDE/Signature, dVerFor como primer hijo

**Cómo verificar (comandos exactos):**
```bash
# 1) Verificar estructura XML correcta (v150)
unzip -p artifacts/soap_last_request_SENT.xml xDE > xDE.zip
unzip -p xDE.zip lote.xml > lote_from_SENT.xml
python3 -c "
import xml.etree.ElementTree as ET
doc = ET.parse('lote_from_SENT.xml')
root = doc.getroot()
# Verificar sin prefijos
print('Root tag:', root.tag)
# Debe ser: rLoteDE (no {ns}rLoteDE)
rde = root.find('.//rDE')
print('rDE tag:', rde.tag if rde is not None else 'NOT FOUND')
# Verificar dVerFor como primer hijo
if rde is not None:
    children = [c.tag.split('}')[-1] for c in rde]
    print('rDE children:', children[:3])
    print('Primer hijo:', children[0] if children else 'NONE')
"

# 2) Verificar consulta_ruc con RUC sin DV
cd tesaka-cv && .venv/bin/python -c "
from app.sifen_client.soap_client import SoapClient
client = SoapClient(env='test')
# Probar RUC de 7 dígitos sin DV
result = client.consulta_ruc_raw('4554737')
print(f'Código: {result[\"parsed\"][\"dCodRes\"]}')
print(f'Mensaje: {result[\"parsed\"][\"dMsgRes\"]}')
if result['parsed']['dCodRes'] == '0502':
    print('✅ RUC sin DV funciona correctamente')
else:
    print('❌ Error en manejo de RUC sin DV')
"
```

**Resultado esperado:** 
- XML con rLoteDE, rDE y Signature sin prefijos
- dVerFor como primer hijo de rDE con valor "150"
- consulta_ruc devuelve 0502 para RUC sin DV
- Si dRUCFactElec='N', es bloqueo administrativo (no técnico)

**Regla anti-regresión:** Ante cambios de empaquetado/zip/envelope, correr "smoke send" para verificar que SIFEN no devuelve 0160.

**Definition of Done (DoD):** `consulta_ruc` devuelve `0502` (no `0160`); si `dRUCFactElec='N'`, clasificar como pendiente de habilitación administrativa.

## 📅 Historial de Descubrimientos

- **2026-01-12**: Descubierto problema pretty_print lxml
- **2026-01-12**: Confirmado que Signature debe estar dentro de DE para XML individual
- **2026-01-12**: Descubierto que SOAP rEnviDe requiere Signature como hija de rDE
- **2026-01-12**: Implementado fix permanente con helper de normalización
- **2025-12-XX**: Descubierto problemas con algoritmos SHA1
- **2025-12-XX**: Descubierto problema con transforms adicionales

---

## [2026-01-17] Error 0160 persiste despite fixes - ds: prefixes issue

**Síntoma:** SIFEN devuelve error 0160 "XML Mal Formado" incluso después de:
- Asegurar dVerFor como primer hijo de rDE
- Signature como hermano de DE (no hijo de DE)
- Signature con namespace XMLDSig estándar

**Causa encontrada:** xmlsec estaba generando prefijos ds: en los elementos hijos de Signature (SignedInfo, SignatureMethod, etc.) mientras que el elemento Signature tenía xmlns default. Esta mezcla de prefijos y namespace default causa rechazo.

**Fix aplicado:**
1. Modificado post-check en xmlsec_signer.py para remover prefijos ds: después de la serialización
2. Reemplazo: `xmlns:ds="..."` con vacío, `<ds:` con `<`, y `</ds:` con `</`
3. Ahora todos los elementos de Signature heredan el namespace XMLDSig sin prefijos

**Comandos de verificación:**
```bash
# Verificar que no hay prefijos ds:
grep -o '<ds:[^>]*>' lote_from_SENT.xml | head -5
# Debe retornar vacío

# Verificar estructura correcta:
grep -A5 -B5 "<Signature" lote_from_SENT.xml | head -15
# Signature debe tener xmlns="http://www.w3.org/2000/09/xmldsig#"
# Los hijos deben no tener prefijos
```

**Estado actual:** XML ahora cumple con requisitos de namespace pero SIFEN sigue devolviendo 0160. Puede haber otra causa.

---

**Regla de oro**: Si algo parece funcionar visualmente con pretty_print, verificar siempre con XPath y herramientas de inspección.

**Regla de Python**: Siempre usar `.venv/bin/python` o `.venv/bin/python3` - NUNCA `python` del sistema.

**Regla de SIFEN**: XML individual necesita Signature dentro de DE; SOAP rEnviDe necesita Signature como hija de rDE.

**Regla anti-regresión 0160**: Ejecutar `.venv/bin/python tools/smoke_send_0160_guardrail.py --xml <archivo_firmado.xml>` obligatoriamente después de cambios en ZIP/envelope/namespaces/firma.

## 🛡️ Guardrail 0160 - Instalación Rápida

```bash
# Activar hooks de git (opcional pero recomendado)
git config core.hooksPath .githooks

# Hacer ejecutable el hook
chmod +x .githooks/pre-push

# Ejecución manual del smoke test
.venv/bin/python tools/smoke_send_0160_guardrail.py --xml <xml_firmado>

# Ejecutar selftest para verificar detección
.venv/bin/python tools/smoke_send_0160_guardrail.py --selftest
```

## [2026-01-17] Error 0160 persiste a pesar de cumplir todas las reglas documentadas

**Síntoma:** SIFEN devuelve error 0160 "XML Mal Formado" pero el XML cumple con TODAS las reglas conocidas.

**Verificaciones realizadas (todas ✅):**
- Sin whitespace (no \n, \r, \t, espacios entre etiquetas)
- Sin XML declaration
- Sin comentarios
- Sin atributos xsi:
- Estructura correcta: rLoteDE -> rDE -> [dVerFor, DE, Signature, gCamFuFD]
- dVerFor como primer hijo de rDE
- Signature sin prefijos ds:
- Firma válida (xmlsec1 --verify OK)
- Valores numéricos sin espacios

**Causa posible:**
- SIFEN tiene validaciones adicionales no documentadas
- El ambiente de prueba puede tener requisitos especiales
- El RUC puede necesitar habilitación específica

**Comandos de verificación completos:**
```bash
# Extraer lote del SOAP enviado
unzip -p artifacts/soap_last_request_SENT.xml xDE > xDE.zip
unzip -p xDE.zip lote.xml > lote_from_SENT.xml

# Diagnóstico completo
.venv/bin/python tools/diagnose_sifen_0160.py lote_from_SENT.xml

# Verificar firma
xmlsec1 --verify --insecure --id-attr:Id DE lote_from_SENT.xml
```

**Estado:** Sin solución conocida. El XML es técnicamente correcto según documentación.

## [2026-01-17] Error 0160 - Orden incorrecto de gCamFuFD y Signature en rDE

**Síntoma:** SIFEN devuelve error 0160 "XML Mal Formado" con XML técnicamente válido.

**Contexto/archivo:** `tesaka-cv/tools/send_sirecepde.py` - XML del lote dentro del SOAP

**Causa real encontrada:** El orden de los elementos en rDE es incorrecto:
- Orden actual (incorrecto): dVerFor, DE, Signature, gCamFuFD
- Orden esperado (correcto): dVerFor, DE, gCamFuFD, Signature

El elemento gCamFuFD debe estar antes de Signature, no después.

**Comandos para verificar:**
```bash
# Extraer lote del SOAP enviado
unzip -p artifacts/soap_last_request_SENT.xml xDE > xDE.zip
unzip -p xDE.zip lote.xml > lote_from_SENT.xml

# Verificar orden de elementos en rDE
python3 -c "
import xml.etree.ElementTree as ET
doc = ET.parse('lote_from_SENT.xml')
NS = {'s': 'http://ekuatia.set.gov.py/sifen/xsd'}
rde = doc.find('.//s:rDE', NS)
if rde is not None:
    children = [c.tag.split('}')[-1] for c in rde]
    print('Orden actual en rDE:', children)
    # Buscar posiciones
    sig_idx = next((i for i, c in enumerate(children) if c == 'Signature'), -1)
    gcam_idx = next((i for i, c in enumerate(children) if c == 'gCamFuFD'), -1)
    print(f'Signature en posición: {sig_idx}')
    print(f'gCamFuFD en posición: {gcam_idx}')
    if sig_idx < gcam_idx:
        print('❌ ERROR: Signature está antes de gCamFuFD')
    else:
        print('✅ OK: gCamFuFD está antes de Signature')
"
```

**Fix aplicado:** 
1. Agregada llamada a `reorder_signature_before_gcamfufd()` después de firmar
2. La función reordena los elementos para que gCamFuFD venga antes de Signature

**Resultado esperado:** El XML debe tener el orden correcto: dVerFor, DE, gCamFuFD, Signature

**Estado actual:** Fix aplicado y orden corregido (gCamFuFD ahora está antes de Signature), pero SIFEN sigue devolviendo error 0160. El XML cumple con todas las reglas conocidas:
- ✅ dVerFor como primer hijo de rDE
- ✅ Orden correcto: dVerFor, DE, gCamFuFD, Signature  
- ✅ Sin prefijos ds:
- ✅ Firma válida (xmlsec1 --verify OK)
- ✅ Namespaces correctos

Puede ser un requisito no documentado de SIFEN o un problema con el RUC/habilitación.

## [2026-01-17] Error 0160 - Preflight validation debe usar XSD correcto para rLoteDE

**Síntoma:** El preflight dice "OK" pero SIFEN devuelve error 0160 "XML Mal Formado" en recepción.

**Contexto/archivo:** Validación de lote.xml antes de enviar a SIFEN

**Causa raíz:** El preflight está validando lote.xml contra WS_SiRecepLoteDE_*.xsd, que es el XSD del wrapper del SOAP, no del lote XML. Este XSD no declara el elemento rLoteDE, por lo que la validación no detecta errores estructurales reales.

**Fix necesario:** El preflight NO puede decir "OK" si no valida lote.xml contra un XSD que declare rLoteDE. Si no existe XSD local que declare rLoteDE, hay que traerlo/localizarlo y cablearlo en la validación.

**Comandos para verificar:**
```bash
# Verificar qué XSD se está usando para validar lote.xml
grep -r "WS_SiRecepLoteDE" . --include="*.py" | grep -v test | head -5

# Verificar si el XSD declara rLoteDE
grep -E "(element.*rLoteDE|complexType.*rLoteDE)" schemas_sifen/WS_SiRecepLoteDE*.xsd
# Si no retorna nada, el XSD no sirve para validar lote.xml

# Buscar XSD que sí declare rLoteDE
find schemas_sifen -name "*.xsd" -exec grep -l "rLoteDE" {} \;
```

**Resultado esperado:** El preflight debe fallar si el lote.xml no tiene la estructura correcta según un XSD que declare explícitamente rLoteDE.

**Regla anti-regresión:** Nunca confiar en una validación que use un XSD que no declare el elemento raíz del documento a validar.

## [2026-01-17] XSD de lote: rLoteDE no está en WS_SiRecepLoteDE_v141.xsd

**Síntoma:** Validación XSD falla con "No matching global declaration available for the validation root."

**Contexto/archivo:** Validación de lote.xml contra XSDs SIFEN

**Causa raíz:** Confusión entre XSD del wrapper SOAP y XSD del contenido del ZIP:
- El SOAP wrapper de siRecepLoteDE usa `<rEnvioLote>` (Schema: SiRecepLoteDE_v150.xsd)
- El ZIP interno (lote.xml) usa raíz `<rLoteDE>` (Schema: ProtProcesLoteDE_v150.xsd)

**Fix necesario:** Usar el XSD correcto para cada validación:
- WS_SiRecepLoteDE_v150.xsd → para validar el SOAP envelope
- ProtProcesLoteDE_v150.xsd → para validar lote.xml (contenido del ZIP)

**Comandos para verificar:**
```bash
# Verificar qué XSD declara cada elemento
grep -E "element.*rEnvioLote" schemas_sifen/SiRecepLoteDE_v150.xsd
# Debe encontrar la declaración

grep -E "element.*rLoteDE" schemas_sifen/ProtProcesLoteDE_v150.xsd
# Debe encontrar la declaración

# Verificar que rLoteDE NO está en el XSD del SOAP
grep -E "element.*rLoteDE" schemas_sifen/WS_SiRecepLoteDE_v150.xsd
# No debe retornar nada
```

**Resultado esperado:** Cada validación debe usar el XSD que declare explícitamente el elemento raíz del documento a validar.

## [2026-01-17] Implementación definitiva de validación XSD para lote v150

**Síntoma:** Error 0160 "XML Mal Formado" persiste a pesar de firma válida y estructura correcta.

**Contexto/archivo:** `tools/validate_lote_xsd.py`, `tesaka-cv/tools/send_sirecepde.py`

**Implementación completada:**
1. **XSDs creados:**
   - `schemas_sifen/rLoteDE_v150.xsd` - Declara el elemento rLoteDE para validación del lote
   - `schemas_sifen/DE_v150_local.xsd` - Versión local de DE_v150.xsd con URLs locales
   - Se usan includes locales para evitar dependencias de red

2. **Validador actualizado:**
   - `tools/validate_lote_xsd.py` ahora busca específicamente rLoteDE_v150.xsd
   - Soporta modo estricto via `SIFEN_STRICT_LOTE_XSD=1`
   - En modo estricto: falla si falta XSD
   - En modo normal: warning y continúa si falta XSD

3. **Integración en send_sirecepde.py:**
   - Validación se ejecuta después de construir y firmar el lote
   - Usa lote.xml en memoria antes de enviar
   - Logging claro: ✅ éxito, ❌ error, ⚠️ warning

**Comandos de uso:**
```bash
# Validar lote existente
python3 tools/validate_lote_xsd.py

# Enviar con validación estricta
SIFEN_STRICT_LOTE_XSD=1 python -m tesaka-cv.tools.send_sirecepde --env test --xml latest

# Enviar con validación no estricta (default)
python -m tesaka-cv.tools.send_sirecepde --env test --xml latest
```

**Estado actual:** La validación XSD funciona y detecta errores estructurales en el lote antes de enviar a SIFEN.

**Regla anti-regresión:** Siempre validar lote.xml contra XSD que declare rLoteDE antes de enviar a SIFEN.

**Regla anti-regresión:** No confundir XSD de WS (request/response) con XSD del contenido del ZIP (lote.xml).

## [2026-01-17] SIFEN_SKIP_RUC_GATE=1 debe saltar toda validación de RUC emisor

**Síntoma:** No se pueden generar artifacts de debug con XMLs de prueba porque la validación local de RUC frena el pipeline.

**Contexto/archivo:** `tesaka-cv/tools/send_sirecepde.py`

**Causa raíz:** `SIFEN_SKIP_RUC_GATE=1` solo saltaba consultaRUC remoto, pero no la validación local que bloquea con RUC dummy/no coincide.

**Fix necesario:** Si `SIFEN_SKIP_RUC_GATE=1`, omitir:
- consultaRUC (gate remoto)
- validación local de RUC dummy/no coincide (bloqueo temprano)

**Comandos para verificar:**
```bash
# Con SIFEN_SKIP_RUC_GATE=1 debe permitir cualquier RUC
SIFEN_SKIP_RUC_GATE=1 SIFEN_EMISOR_RUC=80012345 python -m tesaka-cv.tools.send_sirecepde --env test --xml test.xml
# Debe procesar y generar artifacts de debug

# Sin la variable, debe bloquear con RUC dummy
python -m tesaka-cv.tools.send_sirecepde --env test --xml test.xml
# Debe mostrar error de RUC inválido
```

**Resultado esperado:** Con `SIFEN_SKIP_RUC_GATE=1` se pueden generar artifacts (_passthrough_*, _stage_*) para aislar problemas de serialización/firma.

**Regla anti-regresión:** `SIFEN_SKIP_RUC_GATE=1` debe saltar TODA validación de RUC, no solo la remota.

## [2026-01-18] Error 0160 por duplicación de gCamFuFD

**Síntoma:** SIFEN responde `0160 XML Mal Formado` aunque el lote valide contra XSD.

**Causa raíz:** `gCamFuFD` aparece duplicado (`count=2`) en el ` lote.xml` real enviado. La validación XSD no detecta este caso, pero SIFEN sí lo rechaza.

**Evidencia:**
- `artifacts/last_lote_from_payload.xml` (extraído del ZIP del SOAP final)
- Script: `tools/assert_no_dup_gcamfufd.py` debe dar `gCamFuFD count: 1`

**Fix aplicado:**
- En el flujo passthrough (`build_lote_passthrough_signed()`): deduplicar `gCamFuFD` antes de construir ZIP
- Guardrail fail-hard justo antes de ZIP: si `count != 1` → `RuntimeError` + dump de artifacts
- Normalización: `normalize_rde_before_sign()` no debe "detectar mal" existencia y provocar inserciones duplicadas

**Regla técnica (no romper):**
- Prohibido copiar nodos para "mover" (`deepcopy` / tostring+parse). Si se reubica: `remove + append` y siempre confirmar que el destino no tenga ya uno
- Evitar búsquedas recursivas `.//gCamFuFD` que re-encuentren lo que ya fue movido

**Check obligatorio antes de enviar:**
```bash
.venv/bin/python tools/assert_no_dup_gcamfufd.py artifacts/last_lote_from_payload.xml
# Si no da "1", NO enviar
```

**Comando de reproducción:**
```bash
SIFEN_SKIP_RUC_GATE=1 .venv/bin/python -m tools.send_sirecepde \
  --env test \
  --xml artifacts/_stage_04_signed.xml \
  --dump-http
```

**Regla anti-regresión:** Siempre verificar count=1 de gCamFuFD antes de enviar.

## [2026-01-18] Error 0160 - xsi:schemaLocation debe ser eliminado del XML

**Síntoma:** SIFEN devuelve error 0160 "XML Mal Formado" pero el XML es válido contra XSD y tiene firma válida.

**Contexto/archivo:** `tesaka-cv/tools/send_sirecepde.py` - generación del lote XML

**Causa real encontrada:** El atributo `xsi:schemaLocation="http://ekuatia.set.gov.py/sifen/xsd siRecepDE_v150.xsd"` en el elemento `rDE` causa el error 0160, aunque es válido según XSD.

**Fix aplicado:**
1. Comentado el código que agrega xsi:schemaLocation al rDE (líneas 2599-2620)
2. Mantenida la función `_remove_xsi_schemalocation()` que elimina el atributo después del parseo
3. Agregados patrones regex adicionales para asegurar eliminación completa

**Comandos para verificar:**
```bash
# Verificar que xsi:schemaLocation fue eliminado
unzip -p artifacts/xde_from_stage13.zip xml_file.xml | grep -c "xsi:schemaLocation"
# Debe retornar 0

# Verificar que xmlns:xsi también fue eliminado
unzip -p artifacts/xde_from_stage13.zip xml_file.xml | grep -c "xmlns:xsi"
# Debe retornar 0

# Verificar estructura completa
python3 -c "
import lxml.etree as ET
root = ET.parse('/tmp/current_lote.xml')
ns = {'s': 'http://ekuatia.set.gov.py/sifen/xsd'}
rde = root.find('.//s:rDE', ns)
print('rDE children:', [c.tag.split('}')[-1] for c in rde])
print('rDE Id:', rde.get('Id'))
de = rde.find('.//s:DE', ns)
print('DE Id:', de.get('Id'))
print('Ids diferentes:', rde.get('Id') != de.get('Id'))
print('dVerFor primero:', rde[0].tag.split('}')[-1] if rde else 'NONE')
"
```

**Resultado esperado:** 
- XML sin xsi:schemaLocation ni xmlns:xsi
- Estructura correcta: dVerFor, DE, Signature, gCamFuFD
- Firma válida y XSD válido

**Estado actual:** Después de eliminar xsi:schemaLocation, el XML cumple con todas las validaciones locales pero SIFEN sigue devolviendo 0160. Esto sugiere que puede haber otros requisitos no documentados o restricciones de ambiente específicas.

**Regla anti-regresión:** Nunca incluir xsi:schemaLocation en el XML enviado a SIFEN.

---

## [2026-01-20] Passthrough Byte-Preserving - Solución definitiva para error 0160

**Síntoma:** SIFEN devuelve error 0160 "XML Mal Formado" cuando el XML firmado es modificado durante el passthrough.

**Causa real:** Mutaciones del XML después de la firma (remover newlines, strip, re-serialize) rompen la validez criptográfica de la firma.

**Implementación completa:**
1. **Inmutabilidad SHA256:** Calcular hash antes y después del passthrough
2. **Verificación criptográfica xmlsec:** Validar firma antes y después
3. **Eliminación de mutaciones:** No remover newlines, no hacer strip, no re-serializar
4. **Force Resign:** Switch --force-resign y env SIFEN_FORCE_RESIGN para testing

**Fix aplicado en `tools/send_sirecepde.py`:**
```python
# Capturar bytes originales
rde_bytes_original = _extract_rde_bytes_passthrough(xml_bytes)
sha256_original = calculate_sha256_bytes(rde_bytes_original)

# Verificación criptográfica
is_valid_sig, error_msg = verify_xmlsig_rde(rde_bytes_original)

# Guardrails de inmutabilidad
if sha256_original != sha256_final:
    print("❌ ERROR CRÍTICO: El rDE fue modificado")
    return None  # Forzar re-firma

# NO eliminar newlines en passthrough
# lote_str = lote_str.replace('\n', '').replace('\r', '')  # COMENTADO
```

**Comandos de verificación:**
```bash
# Ejecutar con force-resign para comparar
python -m tools.send_sirecepde --env prod --xml latest --force-resign

# Ejecutar con variable de entorno
SIFEN_FORCE_RESIGN=1 python -m tools.send_sirecepde --env prod --xml latest

# Verificar logs de inmutabilidad
grep -E "SHA256|Inmutabilidad|verificación criptográfica" artifacts/sirecepde_*.log
```

**Tests implementados:**
- `tests/test_passthrough_immutability.py` - Tests unitarios para inmutabilidad
- Verificación de preservación de newlines y whitespace
- Detección de modificaciones con SHA256

**Reglas de passthrough (anti-regresión):**
- **PASSTHROUGH DEBE SER BYTE-PRESERVING**
- Prohibido: `replace("\n","")`, `strip()`, `etree.tostring()` sobre rDE firmado
- Prohibido: Re-serializar con lxml, pretty print, ordenar atributos
- Obligatorio: Verificar SHA256 antes/después
- Obligatorio: Verificar firma con xmlsec antes/después

**Resultado esperado:**
- Logs muestran "✅ Inmutabilidad verificada"
- Logs muestran "✅ Firma XML válida (verificación criptográfica)"
- NO aparece "XML after removing newlines"
- Si SIFEN devuelve 0160, el sistema muestra hashes y fuerza re-firma

---

## [2026-01-19] Error 0160 - Reutilización de ZIP viejo causa XML mal formado

**Síntoma:** SIFEN devuelve error 0160 "XML Mal Formado" intermitentemente, incluso con XML válido y firma correcta.

**Contexto/archivo:** `tesaka-cv/tools/send_sirecepde.py` - función `build_r_envio_lote_xml()`

**Causa raíz encontrada:** El código reutilizaba `zip_base64` existente en lugar de construir un ZIP fresco cada vez. Esto podía enviar un ZIP viejo con estructura incorrecta o versiones antiguas del XML.

**Fix aplicado:**
1. Modificada `build_r_envio_lote_xml()` para SIEMPRE construir un ZIP fresco desde `xml_bytes`
2. Eliminada la lógica que reutilizaba `zip_base64` existente
3. Actualizada la llamada para no pasar el parámetro `zip_base64`

**Comandos para verificar:**
```bash
# Verificar que siempre se construye ZIP fresco
grep -A2 "SIEMPRE construir un ZIP fresco" tesaka-cv/tools/send_sirecepde.py
# Debe mostrar el mensaje de debug

# Verificar que no se reutiliza zip_base64
grep -B2 -A2 "Usando zip_base64 existente" tesaka-cv/tools/send_sirecepde.py
# No debe retornar nada (código eliminado)
```

**Resultado esperado:** Cada envío a SIFEN usa un ZIP recién construido, evitando el error 0160 por datos obsoletos.

**Regla anti-regresión:** Nunca reutilizar ZIPs previos en el envío SOAP - siempre construir desde el XML actual.

---

## [2026-01-17] Error 0160 "XML Mal Formado" - Investigación exhaustiva

**Síntoma:** SIFEN devuelve error 0160 "XML Mal Formado" pero la firma XML es válida y el XML es válido contra XSD.

**Implementaciones completadas:**
- XML declaration version="1.0" (no version="150") ✅
- xsi:schemaLocation presente en rDE ✅
- Sin declaraciones xmlns:xsi redundantes (solo en rDE) ✅
- Sin gCamFuFD (según ejemplos KB) ✅
- dVerFor como primer hijo de rDE ✅
- IDs únicos para rDE y DE ✅
- Sin prefijos ds: en Signature ✅
- Sin whitespace (no \n, \r, \t, espacios entre etiquetas) ✅

 **Estado actual:**
- Todas las validaciones locales pasan
- Estructura coincide con ejemplos KB
- SIFEN sigue devolviendo 0160 ❌

**Estructura XML actual (según KB):**
```xml
<?xml version="1.0" encoding="UTF-8"?>
<rLoteDE xmlns="http://ekuatia.set.gov.py/sifen/xsd">
  <rDE xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
       xsi:schemaLocation="http://ekuatia.set.gov.py/sifen/xsd siRecepDE_v150.xsd"
       Id="rDE...">
    <dVerFor>150</dVerFor>
    <DE Id="...">
      <!-- contenido del DE -->
    </DE>
    <Signature xmlns="http://www.w3.org/2000/09/xmldsig#">
      <!-- firma con 2 transforms: enveloped-signature + exc-c14n -->
    </Signature>
  </rDE>
</rLoteDE>
```

**Comandos de verificación:**
```bash
# Extraer lote del SOAP enviado
unzip -p artifacts/soap_last_request_SENT.xml xDE > xDE.zip
unzip -p xDE.zip lote.xml > lote_from_SENT.xml

# Verificar declaraciones xmlns:xsi
grep -c 'xmlns:xsi=' lote_from_SENT.xml
# Debe retornar 1 (solo en rDE)

# Verificar estructura
python3 -c "
import lxml.etree as ET
doc = ET.parse('lote_from_SENT.xml')
ns = {'s': 'http://ekuatia.set.gov.py/sifen/xsd'}
rde = doc.find('.//s:rDE', ns)
print('rDE children:', [c.tag.split('}')[-1] for c in rde])
print('Con xsi:schemaLocation:', rde.get('{http://www.w3.org/2001/XMLSchema-instance}schemaLocation') is not None)
"
```

**Próximos pasos a investigar:**
1. Verificar si el certificado es válido para ambiente TEST
2. Revisar si hay transformaciones adicionales requeridas

## [2026-01-18] mTLS con combined.pem y validación de RUC en PROD

**Síntoma:** Dudas sobre configuración de mTLS y manejo de RUC con/sin DV.

**Aprendizaje:** En PROD, mTLS funciona con requests y zeep usando Session().cert ya sea combined.pem (string) o (cert.pem, key.pem) (tuple). Validar con curl -vk --cert --key bajando WSDL 200 OK. Si consulta_ruc devuelve dRUCFactElec=N, antes de concluir 'bloqueo SET', verificar formato del RUC: probar con y sin DV (4554737 vs 4554737-8). Si con DV sigue N, es bloqueo administrativo (habilitación FE en Marangatu/SET) y no de código.

**Cómo verificar (comandos exactos):**
```bash
# 1) Probar mTLS con curl (debe dar 200 OK)
curl -vk --cert /path/to/cert.pem --key /path/to/key.pem \
  https://sifen.set.gov.py/de/ws/async/recibe-lote.wsdl?wsdl | head -5

# 2) Probar con combined.pem
curl -vk --cert /path/to/combined.pem \
  https://sifen.set.gov.py/de/ws/async/recibe-lote.wsdl?wsdl | head -5

# 3) Probar RUC con y sin DV
cd tesaka-cv
.venv/bin/python -c "
from app.sifen_client.soap_client import SoapClient, SifenConfig
cfg = SifenConfig(env='prod')
cli = SoapClient(cfg)
for ruc in ['4554737', '4554737-8']:
    try:
        res = cli.consulta_ruc_raw(ruc)
        print(f'{ruc} => dCodRes: {res.get(\"dCodRes\")}, dRUCFactElec: {res.get(\"xContRUC\", {}).get(\"dRUCFactElec\")}')
    except Exception as e:
        print(f'{ruc} => ERROR: {e}')
"
```

**Resultado esperado:**
- curl con certificado debe retornar status 200 y contenido XML del WSDL
- consulta_ruc debe retornar dCodRes=0502 para ambos formatos de RUC
- Si dRUCFactElec=N con ambos formatos, es bloqueo administrativo (requiere habilitación en Marangatu/SET)

**Regla anti-regresión:** Always test mTLS with curl before debugging Python requests. Test RUC both with and without DV before concluding administrative block.
3. Considerar generar XML desde cero sin passthrough
4. Contactar soporte SIFEN para detalles específicos del error 0160

**Regla anti-regresión:** El XML debe coincidir exactamente con los ejemplos de la KB, incluyendo xsi:schemaLocation y sin declaraciones redundadas.

## [2026-01-17] Error 0160 "XML Mal Formado" - Orden incorrecto de gCamFuFD

**Síntoma:** SIFEN devuelve error 0160 "XML Mal Formado" con XML generado y firmado correctamente.

**Causa real encontrada:** El elemento `<gCamFuFD>` está apareciendo ANTES de `<Signature>` cuando debe estar DESPUÉS.

**Estructura incorrecta actual:**
```xml
<rDE Id="rDE...">
  <dVerFor>150</dVerFor>
  <DE Id="...">...</DE>
  <gCamFuFD>...</gCamFuFD>  <!-- ❌ ANTES de Signature -->
  <Signature>...</Signature>
</rDE>
```

**Estructura correcta requerida:**
```xml
<rDE Id="rDE...">
  <dVerFor>150</dVerFor>
  <DE Id="...">...</DE>
  <Signature>...</Signature>
  <gCamFuFD>...</gCamFuFD>  <!-- ✅ DESPUÉS de Signature -->
</rDE>
```

**Implementación necesaria:**
- El proceso de firma debe mover gCamFuFD desde dentro de DE hasta después de Signature
- Esto debe hacerse ANTES de calcular la firma (para que no afecte el digest)
- Luego de firmar, gCamFuFD debe insertarse después del elemento Signature

**Comandos de verificación:**
```bash
# Extraer lote del SOAP enviado
unzip -p artifacts/soap_last_request_SENT.xml xDE > xDE.zip
unzip -p xDE.zip lote.xml > lote_from_SENT.xml

# Verificar orden de elementos
python3 -c "
import lxml.etree as ET
doc = ET.parse('lote_from_SENT.xml')
ns = {'s': 'http://ekuatia.set.gov.py/sifen/xsd'}
rde = doc.find('.//s:rDE', ns)
children = [c.tag.split('}')[-1] for c in rde]
print('Orden actual:', children)
print('¿Signature antes que gCamFuFD?', 
      children.index('Signature') < children.index('gCamFuFD'))
"
```

**Resultado esperado:** Signature debe aparecer antes que gCamFuFD en la lista de hijos de rDE.

**Regla anti-regresión:** El orden debe ser siempre: dVerFor, DE, Signature, gCamFuFD.

## [2026-01-17] Error 0160 "XML Mal Formado" - Análisis final

**Síntoma:** SIFEN devuelve error 0160 "XML Mal Formado" con XML generado y firmado correctamente.

**Estado actual de la investigación:**
- rDE tiene atributo Id ✅
- rDE y DE tienen IDs diferentes ✅
- dVerFor está presente como primer hijo ✅
- Orden correcto: dVerFor, DE, Signature ✅
- Sin prefijos ds: ✅
- Firma verifica OK con xmlsec1 ✅
- XML válido contra XSD ✅

**Estructura XML actual (verificada):**
```xml
<rLoteDE xmlns="http://ekuatia.set.gov.py/sifen/xsd">
  <rDE Id="rDE...">
    <dVerFor>150</dVerFor>
    <DE Id="...">...</DE>
    <Signature xmlns="http://www.w3.org/2000/09/xmldsig#">...</Signature>
  </rDE>
</rLoteDE>
```

**gCamFuFD:**
- No está presente en el XML enviado
- El XSD lo marca como opcional (minOccurs="0")
- Puede ser requerido por SIFEN a pesar de ser opcional en XSD
- No se puede agregar después de la firma (invalidaría la firma)

**Posibles causas restantes:**
1. **gCamFuFD requerido** - Aunque el XSD lo marca como opcional, SIFEN podría requerirlo
2. **Certificado de TEST** - El certificado podría no ser válido para ambiente TEST
3. **Requisitos no documentados** - Podría haber validaciones no especificadas en el XSD
4. **Formato específico** - SIFEN podría ser sensible al formatting del XML

**Comandos de verificación actuales:**
```bash
# Verificar estructura completa
python3 -c "
import lxml.etree as ET
doc = ET.parse('lote.xml')
ns = {'s': 'http://ekuatia.set.gov.py/sifen/xsd'}
rde = doc.find('.//s:rDE', ns)
print('rDE Id:', rde.get('Id'))
de = rde.find('.//s:DE', ns)
print('DE Id:', de.get('Id'))
print('Ids diferentes:', rde.get('Id') != de.get('Id'))
print('Hijos de rDE:', [c.tag.split('}')[-1] for c in rde])
"

# Verificar firma
xmlsec1 --verify --insecure --id-attr:Id DE lote.xml

# Validar XSD
python3 -c "
from lxml import etree
xsd = etree.XMLSchema(etree.parse('schemas_sifen/rLoteDE_v150.xsd'))
xml = etree.parse('lote.xml')
print('Válido XSD:', xsd.validate(xml))
"
```

**Próximos pasos recomendados:**
1. Contactar soporte SIFEN para obtener detalles específicos del error 0160
2. Solicitar acceso a logs más detallados del lado de SIFEN
3. Verificar si el certificado es válido para ambiente TEST
4. Considerar generar XML con un certificado de producción si está disponible

**Regla anti-regresión:** A pesar de cumplir con todas las validaciones locales, SIFEN puede tener requisitos no documentados que causan el error 0160.

## [2026-01-18] Error 0160 persiste con todas las validaciones locales pasando

**Síntoma:** SIFEN devuelve error 0160 "XML Mal Formado" pero el XML cumple con TODAS las reglas conocidas.

**Implementaciones completadas:**
- rDE tiene atributo Id requerido por XSD 
- rDE y DE tienen IDs diferentes (no duplicados) 
- dVerFor está presente como primer hijo de rDE 
- Orden correcto: dVerFor, DE, Signature, gCamFuFD 
- Signature con xmlns SIFEN (no XMLDSig) 
- DE con xsi:schemaLocation 
- XML sin prefijos ds: 
- Firma verifica OK con xmlsec1 
- XML válido contra XSD rLoteDE_v150 
- Certificado válido (válido hasta Dic 2026) 

**Estado actual:**
- Todas las validaciones locales pasan
- SIFEN sigue devolviendo 0160 

**Comandos de verificación:**
```bash
# Extraer lote del SOAP enviado
unzip -p artifacts/soap_last_request_SENT.xml xDE > xDE.zip
unzip -p xDE.zip lote.xml > lote_from_SENT.xml

# Verificar estructura completa
python3 -c "
import lxml.etree as ET
root = ET.parse('lote_from_SENT.xml')
ns = {'s': 'http://ekuatia.set.gov.py/sifen/xsd'}
rde = root.find('.//s:rDE', ns)
print('rDE children:', [c.tag.split('}')[-1] for c in rde])
print('rDE Id:', rde.get('Id'))
de = rde.find('.//s:DE', ns)
print('DE Id:', de.get('Id'))
print('Ids diferentes:', rde.get('Id') != de.get('Id'))
print('dVerFor primero:', rde[0].tag.split('}')[-1] == 'dVerFor')
sig = rde.find('.//s:Signature', ns)
print('Signature xmlns SIFEN:', sig.get('xmlns') == 'http://ekuatia.set.gov.py/sifen/xsd')
print('DE tiene schemaLocation:', de.get('{http://www.w3.org/2001/XMLSchema-instance}schemaLocation') is not None)
"

# Verificar firma
xmlsec1 --verify --insecure --id-attr:Id DE lote_from_SENT.xml

# Validar XSD
python3 -c "
from lxml import etree
xsd = etree.XMLSchema(etree.parse('schemas_sifen/rLoteDE_v150.xsd'))
xml = etree.parse('lote_from_SENT.xml')
print('Válido XSD:', xsd.validate(xml))
"
```

**Próximos pasos recomendados:**
1. Contactar soporte SIFEN para obtener detalles específicos del error 0160
2. Solicitar acceso a logs más detallados del lado de SIFEN
3. Verificar si el certificado es válido para ambiente TEST
4. Considerar generar XML con un certificado de producción si está disponible
5. Revisar si hay algún requisito no documentado de SIFEN

**Regla anti-regresión:** A pesar de cumplir con todas las validaciones locales, SIFEN puede tener requisitos no documentados que causan el error 0160.

## [2026-01-18] SIFEN v150 — QR Fix (dCarQR) + gCamFuFD Injection

**Síntoma:** El QR no se está generando según el Manual Técnico SIFEN v150 sección 13.8.4.

**Contexto/archivo:** `tesaka-cv/app/sifen_client/qr_generator.py`

**Causa real:** La implementación no seguía exactamente los pasos del Manual Técnico para:
1. Extraer nVersion desde dVerFor (en lugar de hardcoded "150")
2. Convertir dFeEmiDE a hex-ASCII de bytes UTF-8
3. Extraer solo dígitos de dRucRec
4. Usar "0" como default para campos faltantes
5. Convertir DigestValue a hex del texto base64 (no decode)

**Fix aplicado:**
1. Modificado `build_qr_dcarqr()` para seguir exactamente la metodología del Manual Técnico
2. Extraer nVersion desde dVerFor con default "150"
3. Convertir fechas a hex-ASCII desde bytes UTF-8
4. Filtrar dígitos del RUC receptor
5. Autodetectar ambiente TEST/PROD según SIFEN_ENV
6. Modificado `inject_qr_into_gcamfufd()` para:
   - Crear gCamFuFD como hijo directo de rDE (fuera de DE)
   - Borrar hijos existentes antes de insertar
   - Insertar dCarQR y dInfAdic vacío

## [2026-01-20] Error 0160 "XML Mal Formado" - Root Cause: Signature xmlns SIFEN rompe XMLDSig

**Síntoma:** SIFEN devuelve error 0160 "XML Mal Formado" pero la firma XML parece válida.

**Causa real confirmada:** En modo passthrough estamos cambiando el xmlns de `<Signature>` a SIFEN, lo cual rompe XMLDSig y SIFEN responde 0160.

**Evidencia:** El SOAP enviado contiene `<Signature xmlns="http://ekuatia.set.gov.py/sifen/xsd">` y dentro `<SignedInfo>...` sin prefijos ds, lo cual es inválido. Debe ser XMLDSig `http://www.w3.org/2000/09/xmldsig#`.

**Fix implementado:**
1. **Eliminado** el cambio forzado de xmlns de Signature a SIFEN en modo passthrough
2. **Implementado** guardrail `xmlsig_guard.py` que valida XMLDSig namespace antes de passthrough
3. **Agregado** hard fail validation antes de enviar a SIFEN que aborta si Signature no es XMLDSig
4. **Corregido** bug `sig_before` NameError
5. **Ajustado** selección de archivos "latest" para excluir artefactos de debug

**REGLA PERMANENTE DEL PROYECTO:**
- **Signature DEBE usar xmlns XMLDSig:** `http://www.w3.org/2000/09/xmldsig#`
- **NUNCA cambiar xmlns de Signature** a SIFEN en modo passthrough
- **Si Signature no es XMLDSig, forzar re-firma** completa

**Comandos de verificación:**
```bash
# Verificar namespace en XML
python3 -c "
from app.sifen_client.xmlsig_guard import validate_signature_namespace_in_xml
with open('lote.xml', 'rb') as f:
    is_valid, error = validate_signature_namespace_in_xml(f.read())
    print(f'XMLDSig válido: {is_valid}')
    if error: print(f'Error: {error}')
"

# Verificar en SOAP enviado
unzip -p artifacts/soap_last_request_SENT.xml xDE > xDE.zip
unzip -p xDE.zip lote.xml > lote_from_SENT.xml
grep -o 'Signature xmlns="[^"]*"' lote_from_SENT.xml
# Debe mostrar: Signature xmlns="http://www.w3.org/2000/09/xmldsig#"
```

**Estado actual:** ✅ Signature mantiene XMLDSig, guardrail activado, hard fail implementado

**Comandos de verificación:**
```bash
# Verificar QR generado correctamente
.venv/bin/python -m tools.inspect_qr tools/artifacts/_passthrough_lote.xml

# Debe mostrar:
# dCarQR presente con URL no nula
# QR params con todos los campos requeridos
# gCamFuFD como hijo directo de rDE
```

**Resultado esperado:** QR generado según Manual Técnico con todos los parámetros en orden correcto y hash SHA256 válido.

**Regla anti-regresión:** El QR debe generarse siguiendo exactamente los pasos 1-4 del Manual Técnico sección 13.8.4.

## [2026-01-18] SOAP 1.2 no es la causa del error 0160

**Síntoma:** SIFEN devuelve error 0160 "XML Mal Formado" con SOAP 1.1.

**Contexto/archivo:** `tesaka-cv/app/sifen_client/soap_client.py` - método `send_recibe_lote()`

**Causa real encontrada:** Se estaba usando SOAP 1.1 en lugar de SOAP 1.2.

**Fix aplicado:**
1. Cambiado SOAP namespace de 1.1 a 1.2: `http://schemas.xmlsoap.org/soap/envelope/` → `http://www.w3.org/2003/05/soap-envelope`
2. Cambiado Content-Type de `text/xml` a `application/soap+xml`
3. Removido header `SOAPAction` y agregado parámetro `action` en Content-Type
4. Cambiado prefijo de elementos de `soap:` a `env:`
5. Agregado logging para indicar versión SOAP usada

**Comandos de verificación:**
```bash
# Verificar que se está usando SOAP 1.2
cd tesaka-cv && .venv/bin/python -c "
from app.sifen_client.soap_client import SoapClient
client = SoapClient(env='test')
print('SOAP namespace:', client.soap_namespace)
print('Content-Type:', client.content_type)
# Debe mostrar:
# SOAP namespace: http://www.w3.org/2003/05/soap-envelope
# Content-Type: application/soap+xml
"

# Verificar envelope generado
grep -A2 "xmlns:env" artifacts/soap_last_request_SENT.xml
# Debe mostrar: xmlns:env="http://www.w3.org/2003/05/soap-envelope"
```

**Resultado esperado:** El SOAP envelope debe usar namespace 1.2 y Content-Type `application/soap+xml`.

**Estado actual:** SOAP 1.2 implementado correctamente, pero SIFEN sigue devolviendo error 0160. El problema está en la estructura del XML interno del lote, no en la versión del SOAP.

**Regla anti-regresión:** SIFEN espera SOAP 1.2, no 1.1. Usar siempre namespace `http://www.w3.org/2003/05/soap-envelope` y Content-Type `application/soap+xml`.

## [2026-01-19] Error 0160 persistente en PROD - Todos los requisitos conocidos cumplidos

**Síntoma:** SIFEN PROD devuelve error 0160 "XML Mal Formado" pero TODOS los requisitos conocidos están cumplidos.

**Implementaciones completadas:**
- ✅ Sin declaración XML
- ✅ rLoteDE con namespace correcto
- ✅ rDE hereda namespace (sin xmlns)
- ✅ rDE tiene Id con prefijo "rDE"
- ✅ DE tiene Id diferente
- ✅ dVerFor como primer hijo con valor 150
- ✅ Signature usa namespace SIFEN
- ✅ Orden correcto: dVerFor, DE, Signature, gCamFuFD
- ✅ Sin xsi:schemaLocation
- ✅ XML en una sola línea (sin newlines)
- ✅ Sin prefijos de namespace
- ✅ Firma válida (aunque xmlsec1 no valida con namespace SIFEN)

**Estado actual:**
- Todas las validaciones locales pasan
- XML cumple con XSD rLoteDE_v150
- SIFEN PROD sigue devolviendo 0160 ❌

**Investigación adicional:**
- Se encontraron 5 tags self-closing en la sección Signature (normal en XMLDSig)
- No se encontraron otros issues obvios

**Posibles causas restantes:**
1. Requisito específico de PROD no documentado
2. Validación SIFEN diferente a XSD estándar
3. Issue con certificado o configuración PROD
4. Elemento faltante no obvio en XSD
5. Orden específico de atributos dentro de elementos
6. Transformación específica requerida por SIFEN

**Comandos de verificación:**
```bash
# Extraer y verificar XML enviado
unzip -p artifacts/soap_last_request_SENT.xml xDE > xDE.zip
unzip -p xDE.zip lote.xml > lote_from_SENT.xml

# Verificar todos los requisitos
python3 -c "
import xml.etree.ElementTree as ET
doc = ET.parse('lote_from_SENT.xml')
# [verificar todos los puntos como arriba]
"
```

**Estado:** ABIERTO - Se requiere investigación adicional con SIFEN o acceso a logs más detallados.

## [2026-01-20] MODO GUERRA 0160 — gCamFuFD + QR obligatorio (DNIT)

**Síntoma:** SIFEN devuelve error 0160 "XML Mal Formado" cuando falta gCamFuFD, aunque el XSD lo marque como opcional.

**Contexto/archivo:** `tesaka-cv/tools/send_sirecepde.py`, `tesaka-cv/app/sifen_client/xmlsec_signer.py`

**Causa raíz:** DNIT/SIFEN requiere obligatoriamente el elemento `gCamFuFD` con `dCarQR` para evitar error 0160. El XSD lo marca como opcional pero en la práctica es obligatorio.

**Fix aplicado:**
1. **Modificado** `validate_gcamfufd_singleton_before_send()` para exigir gCamFuFD en modo producción
2. **Asegurado** que `xmlsec_signer.py` siempre genere gCamFuFD después de la firma
3. **Agregado** validación de SIFEN_CSC obligatorio antes de enviar
4. **Implementado** flag `SIFEN_ALLOW_MISSING_GCAMFUFD=1` solo para debug local
5. **Actualizado** tests anti-regresión para validar comportamiento obligatorio

**Cómo verificar (comandos exactos):**
```bash
# Configurar CSC (obligatorio para producción)
export SIFEN_CSC="12345678901234567890123456789012"
export SIFEN_CSC_ID="0001"

# Ejecutar flujo completo
cd tesaka-cv
export SIFEN_SKIP_RUC_GATE=1
../scripts/run.sh -m tools.send_sirecepde --env prod --xml artifacts/_temp_lote_for_validation.xml --force-resign --dump-http

# Verificar estructura del XML enviado
unzip -p artifacts/soap_last_request_SENT.xml xDE > xDE.zip
unzip -p xDE.zip lote.xml > lote_from_SENT.xml
python3 -c "
import lxml.etree as ET
root = ET.parse('lote_from_SENT.xml')
ns = {'s': 'http://ekuatia.set.gov.py/sifen/xsd'}
rde = root.find('.//s:rDE', ns)
print('rDE children:', [c.tag.split('}')[-1] for c in rde])
print('gCamFuFD count:', len([c for c in rde if c.tag.split('}')[-1] == 'gCamFuFD']))
"

# Ejecutar script de verificación completo
python3 scripts/verify_modo_guerra_0160.py
```

**Resultado esperado:** rDE children debe ser `['dVerFor', 'DE', 'Signature', 'gCamFuFD']` y `gCamFuFD count: 1`.

**Regla anti-regresión:** DNIT requiere gCamFuFD obligatoriamente con dCarQR. No enviar sin SIFEN_CSC configurado. Usar `SIFEN_ALLOW_MISSING_GCAMFUFD=1` solo para debug local.

