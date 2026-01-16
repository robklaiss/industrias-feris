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

## 📅 Historial de Descubrimientos

- **2026-01-12**: Descubierto problema pretty_print lxml
- **2026-01-12**: Confirmado que Signature debe estar dentro de DE para XML individual
- **2026-01-12**: Implementadas herramientas de diagnóstico y fix
- **2026-01-12**: Descubierto que SOAP rEnviDe requiere Signature como hija de rDE
- **2026-01-12**: Implementado fix permanente con helper de normalización
- **2025-12-XX**: Descubierto problemas con algoritmos SHA1
- **2025-12-XX**: Descubierto problema con transforms adicionales

---

**Regla de oro**: Si algo parece funcionar visualmente con pretty_print, verificar siempre con XPath y herramientas de inspección.

**Regla de Python**: Siempre usar `.venv/bin/python` o `.venv/bin/python3` - NUNCA `python` del sistema.

**Regla de SIFEN**: XML individual necesita Signature dentro de DE; SOAP rEnviDe necesita Signature como hija de rDE.
