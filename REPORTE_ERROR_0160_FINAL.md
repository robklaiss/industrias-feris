# Reporte: Investigación Error 0160 "XML Mal Formado" de SIFEN

## Fecha
2026-01-18

## Objetivo
Identificar y corregir la causa del error 0160 "XML Mal Formado" devuelto por SIFEN al enviar documentos electrónicos.

## Hallazgos Principales

### 1. Diferencias Estructurales Encontradas

Al comparar nuestro XML generado con el ejemplo oficial de SIFEN (`docs/sifen-oficial/Extructura xml_DE-1.xml`), se identificaron las siguientes diferencias críticas:

#### a) Secciones faltantes en el DE:
- **gOpeCom**: Sección de información de operación comercial dentro de `gDatGralOpe`
- **gCamFE**: Campos específicos de facturación electrónica dentro de `gDtipDE`
- **gCamCond**: Condiciones de operación dentro de `gDtipDE`

#### b) Ubicación de gCamFuFD:
- En nuestros intentos anteriores, `gCamFuFD` no estaba presente
- Según el ejemplo oficial, debe estar como hijo directo de `rDE` (no de `DE`)
- Debe ubicarse después del elemento `Signature`

### 2. Estructura Correcta Implementada

```xml
<rLoteDE xmlns="http://ekuatia.set.gov.py/sifen/xsd">
  <rDE Id="rDE...">
    <dVerFor>150</dVerFor>
    <DE Id="...">
      <gDatGralOpe>
        <gOpeCom>  <!-- ESTE FALTABA -->
          <iTipTra>1</iTipTra>
          <dDesTipTra>Venta de mercadería</dDesTipTra>
          <!-- ... -->
        </gOpeCom>
        <!-- ... -->
      </gDatGralOpe>
      <gDtipDE>
        <gCamFE>  <!-- ESTE FALTABA -->
          <iIndPres>1</iIndPres>
          <dDesIndPres>Operación presencial</dDesIndPres>
        </gCamFE>
        <gCamCond>  <!-- ESTE FALTABA -->
          <iCondOpe>2</iCondOpe>
          <dDCondOpe>Crédito</dDCondOpe>
          <!-- ... -->
        </gCamCond>
        <!-- ... -->
      </gDtipDE>
      <!-- ... -->
    </DE>
    <Signature xmlns="http://www.w3.org/2000/09/xmldsig#">
      <!-- ... -->
    </Signature>
    <gCamFuFD>  <!-- ESTE FALTABA Y DEBE ESTAR AQUÍ -->
      <dDesTrib>10</dDesTrib>
    </gCamFuFD>
  </rDE>
</rLoteDE>
```

### 3. Validaciones Realizadas

Todas las validaciones locales pasan correctamente:
- ✅ XML válido contra XSD `rLoteDE_v150.xsd`
- ✅ Firma XML verificada con xmlsec1
- ✅ Estructura completa con todas las secciones requeridas
- ✅ Orden correcto de elementos: dVerFor, DE, Signature, gCamFuFD
- ✅ IDs únicos para rDE y DE
- ✅ Sin prefijos ds: en la firma
- ✅ Sin whitespace (newlines, tabs)

### 4. Resultado de Pruebas

A pesar de implementar todas las correcciones estructurales, SIFEN continúa devolviendo:
```
<dCodRes>0160</dCodRes>
<dMsgRes>XML Mal Formado.</dMsgRes>
```

### 5. Comandos de Verificación Utilizados

```bash
# Verificar estructura completa
python3 -c "
import lxml.etree as ET
doc = ET.parse('lote.xml')
ns = {'s': 'http://ekuatia.set.gov.py/sifen/xsd'}
rde = doc.find('.//s:rDE', ns)
print('rDE children:', [c.tag.split('}')[-1] for c in rde])
print('rDE Id:', rde.get('Id'))
de = rde.find('.//s:DE', ns)
print('DE Id:', de.get('Id'))
print('Ids diferentes:', rde.get('Id') != de.get('Id'))
print('dVerFor primero:', rde[0].tag.split('}')[-1] == 'dVerFor')
print('gCamFuFD presente:', 'gCamFuFD' in [c.tag.split('}')[-1] for c in rde])
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

## Conclusiones

1. **Se identificaron y corrigieron las diferencias estructurales** entre nuestro XML y el ejemplo oficial de SIFEN.
2. **Todas las validaciones locales pasan**, incluyendo XSD y firma digital.
3. **El error 0160 persiste**, lo que sugiere que SIFEN puede tener requisitos no documentados o validaciones adicionales no evidentes en los XSD públicos.

## Próximos Pasos Recomendados

1. **Contactar soporte SIFEN** para obtener detalles específicos sobre qué causa el error 0160.
2. **Solicitar acceso a logs detallados** del lado de SIFEN que puedan indicar exactamente qué elemento está causando el rechazo.
3. **Considerar la posibilidad** de que existan requisitos no públicos para el ambiente de producción.
4. **Verificar si el certificado digital** utilizado cumple con todos los requisitos para producción.

## Archivos de Referencia

- XML generado con estructura completa: `lote_con_gcamfufd.xml`
- Ejemplo oficial SIFEN: `docs/sifen-oficial/Extructura xml_DE-1.xml`
- Script generador con correcciones: `tesaka-cv/tools/generar_de_con_gcamfufd.py`
- Último XML enviado: `artifacts/last_lote_from_payload.xml`

## Reglas Anti-regresión

- Siempre incluir `gOpeCom` dentro de `gDatGralOpe`
- Siempre incluir `gCamFE` y `gCamCond` dentro de `gDtipDE`
- Siempre incluir `gCamFuFD` como hijo de `rDE` después de `Signature`
- Mantener el orden: dVerFor, DE, Signature, gCamFuFD
