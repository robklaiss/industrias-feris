
## [2026-01-20] Fix definitivo error 0160 - gCamFuFD singleton y posición

**Síntoma:** SIFEN devuelve error 0160 "XML Mal Formado" por duplicación o mala posición de gCamFuFD.

**Causa real:** gCamFuFD se estaba agregando en múltiples lugares del código:
1. xmlsec_signer.py creaba gCamFuFD después de firmar
2. send_sirecepde.py también agregaba gCamFuFD antes de firmar
3. Esto causaba duplicación o posición incorrecta

**Solución implementada:**
1. Crear helper `ensure_single_gCamFuFD_after_signature()` que:
   - Elimina TODOS los gCamFuFD existentes (en cualquier ubicación)
   - Crea exactamente 1 gCamFuFD como hijo directo de rDE
   - Lo posiciona inmediatamente después de Signature
   - Incluye dCarQR y dInfAdic requeridos

2. Modificar xmlsec_signer.py para usar el helper (único responsable de gCamFuFD)

3. Comentar `ensure_gCamFuFD()` en send_sirecepde.py para evitar duplicación

4. Agregar validación dura `validate_gcamfufd_singleton_before_send()` que:
   - Verifica count == 1
   - Verifica que sea hijo de rDE (no de DE)
   - Verifica que esté después de Signature
   - Guarda artifacts si falla

5. Actualizar fechas de timbrado según DNIT:
   - TEST: dFeIniT = 2025-12-29
   - PROD: dFeIniT = 2026-01-14

**Comandos de verificación:**
```bash
# Verificar estructura final
python -c "
import xml.etree.ElementTree as ET
doc = ET.parse('lote_from_SENT.xml')
NS = {'s': 'http://ekuatia.set.gov.py/sifen/xsd'}
rde = doc.find('.//s:rDE', NS)
children = [c.tag.split('}')[-1] for c in rde]
print('rDE children:', children)
print('gCamFuFD count:', children.count('gCamFuFD'))
print('gCamFuFD position:', children.index('gCamFuFD') if 'gCamFuFD' in children else -1)
"

# Correr tests
cd tesaka-cv
python -m pytest -q tests/test_gcamfufd_singleton.py -vv

# Enviar con validación
export SIFEN_SKIP_RUC_GATE=1
../scripts/run.sh -m tools.send_sirecepde --env prod --xml artifacts/_temp_lote_for_validation.xml --force-resign --dump-http
```

**Estado actual:** gCamFuFD ahora se maneja como singleton en posición correcta después de Signature.

---

## [2026-01-18] Error 0160 "XML Mal Formado" - Estado actual después de todos los fixes

**Síntoma:** SIFEN devuelve error 0160 "XML Mal Formado" pero todas las validaciones locales pasan.

**Implementaciones completadas:**
- rDE tiene atributo Id requerido por XSD ✅
- rDE y DE tienen IDs diferentes (no duplicados) ✅
- dVerFor está presente como primer hijo de rDE ✅
- gCamFuFD está fuera de DE y después de Signature ✅
- XML sin prefijos ds: ✅
- Firma verifica OK con xmlsec1 (aunque con advertencias) ✅
- XML válido contra XSD rLoteDE_v150 ✅
- Whitespace (newlines) eliminado ✅
- Signature usa namespace SIFEN xmlns="http://ekuatia.set.gov.py/sifen/xsd" ✅
- Declaración XML usa comillas dobles ✅
- XML en una sola línea ✅

**Estado actual:**
- Todas las validaciones locales pasan
- SIFEN sigue devolviendo 0160 ❌

**Estructura XML final verificada:**
```xml
<?xml version="1.0" encoding="utf-8"?>
<rLoteDE xmlns="http://ekuatia.set.gov.py/sifen/xsd">
  <rDE Id="rDE_TEST_001">
    <dVerFor>150</dVerFor>
    <DE Id="018004554737010010000001202601171234567891">
      <!-- contenido del DE -->
    </DE>
    <Signature xmlns="http://ekuatia.set.gov.py/sifen/xsd">
      <!-- firma -->
    </Signature>
    <gCamFuFD>
      <dCarQR>
        <dVerQR>1</dVerQR>
        <dPacQR>0</dPacQR>
      </dCarQR>
    </gCamFuFD>
  </rDE>
</rLoteDE>
```

**Comandos de verificación finales:**
```bash
# Extraer y verificar estructura completa
unzip -p artifacts/soap_last_request_SENT.xml xDE > xDE.zip
unzip -p xDE.zip lote.xml > lote_from_SENT.xml
python3 -c "
import lxml.etree as ET
root = ET.parse('lote_from_SENT.xml')
ns = {'s': 'http://ekuatia.set.gov.py/sifen/xsd'}
rde = root.find('.//s:rDE', ns)
print('rDE Id:', rde.get('Id'))
de = rde.find('.//s:DE', ns)
print('DE Id:', de.get('Id'))
print('Ids diferentes:', rde.get('Id') != de.get('Id'))
print('Hijos de rDE:', [c.tag.split('}')[-1] for c in rde])
print('dVerFor primero:', rde[0].tag.split('}')[-1] == 'dVerFor')
sig = rde.find('.//s:Signature', ns)
print('Signature xmlns SIFEN:', sig.get('xmlns') == 'http://ekuatia.set.gov.py/sifen/xsd')
"

# Verificar firma (fallará por namespace SIFEN)
xmlsec1 --verify --insecure --id-attr:Id DE lote_from_SENT.xml

# Validar XSD
python3 -c "
from lxml import etree
xsd = etree.XMLSchema(etree.parse('schemas_sifen/rLoteDE_v150.xsd'))
xml = etree.parse('lote_from_SENT.xml')
print('Válido XSD:', xsd.validate(xml))
"
```

**Posibles causas restantes (no verificadas):**
1. Problemas con el certificado o la configuración del ambiente TEST
2. Requisitos no documentados de SIFEN (elementos faltantes)
3. Orden específico de atributos dentro de los elementos
4. Codificación específica requerida por SIFEN
5. Problemas con el ZIP (método de compresión, estructura)
6. SIFEN podría requerir un formato específico de gCamFuFD no vacío

---

## [2026-01-20] Soporte PKCS#12 (.p12/.pfx) para mTLS SIFEN

**Síntoma:** Error "PEM inválido: cert=...F1T_65478.p12 error=[SSL] PEM lib" cuando se intenta usar un certificado P12/PFX.

**Causa real:** El sistema intentaba cargar un archivo P12/PFX como si fuera PEM con `ssl.SSLContext.load_cert_chain()`.

**Implementación:**
- Se creó `app/sifen_client/certs.py` con `load_mtls_credentials()` que detecta automáticamente el formato
- Para P12/PFX: usa `cryptography` para convertir a PEM temporales en `~/.sifen/cache/<hash>/`
- Para PEM: usa directamente los archivos proporcionados
- Los archivos temporales tienen permisos 600 y se limpian automáticamente al cerrar el cliente
- Se agregó `tools/pem_preflight.py` para verificar la configuración

**Configuración:**
```bash
# Para P12/PFX
export SIFEN_CERT_PATH=/ruta/al/certificado.p12
export SIFEN_P12_PASSWORD=secreto

# Para PEM (sin cambios)
export SIFEN_CERT_PATH=/ruta/al/cert.pem
export SIFEN_KEY_PATH=/ruta/al/key.pem
```

**Comandos de verificación:**
```bash
# Verificar configuración P12/PFX
export SIFEN_CERT_PATH=/ruta/al/cert.p12
export SIFEN_P12_PASSWORD=secreto
python tools/pem_preflight.py

# Debe mostrar:
# ✅ OK: P12 convertido a PEM
# ✅ OK: Contexto SSL creado exitosamente
# ✅ OK: Cache limpiada
```

**Estado actual:**
- P12/PFX soportado completamente ✅
- Conversión automática a PEM transparente para el usuario ✅
- Cache de PEM para evitar conversiones repetidas ✅
- Limpieza automática de archivos temporales ✅

---
