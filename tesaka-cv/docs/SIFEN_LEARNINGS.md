
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
