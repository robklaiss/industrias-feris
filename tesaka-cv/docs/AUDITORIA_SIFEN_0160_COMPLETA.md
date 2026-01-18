# SIFEN 0160 - Auditoría Completa con Evidencia Final

## 1. WSDL Excerpt - SOAP Action

**Archivo:** `/Users/robinklaiss/Dev/industrias-feris-facturacion-electronica-simplificado/rshk-jsifenlib/docs/set/test/v150/wsdl/async/recibe-lote.wsdl`

```xml
Line 17: <soap12:operation soapAction="" soapActionRequired="false" style="document"/>
```

**Análisis:** El WSDL especifica `soapAction=""` vacío y `soapActionRequired="false"`, lo que significa que para SOAP 1.2, el action debe ir en el Content-Type header.

## 2. Código Aplicado - Diff

```diff
--- a/app/sifen_client/soap_client.py
+++ b/app/sifen_client/soap_client.py
@@ -1613,9 +1613,9 @@ class SoapClient:
         # 3) Headers - SOAP 1.2 requiere application/soap+xml
-        # Action debe ser la URI completa del namespace según SOAP 1.2
-        SOAP_ACTION = "siRecepLoteDE"
+        # Action debe ser la URI completa del namespace según SOAP 1.2
+        SOAP_ACTION = "http://ekuatia.set.gov.py/sifen/xsd/siRecepLoteDE"
         headers = {
             "Accept": "application/xml, text/xml, */*",
-            "Content-Type": f'application/soap+xml; charset=utf-8; action="{SOAP_ACTION}"',
+            "Content-Type": f'application/soap+xml; charset=utf-8; action="{SOAP_ACTION}"',
             "Connection": "close",
         }
```

## 3. Request/Response SIFEN

### Headers HTTP enviados:
```
Accept: application/xml, text/xml, */*
Connection: close
Content-Type: application/soap+xml; charset=utf-8; action="http://ekuatia.set.gov.py/sifen/xsd/siRecepLoteDE"
```

### SOAP Envelope (primeras 30 líneas):
```xml
<?xml version="1.0" encoding="UTF-8"?>
<soap:Envelope xmlns:soap="http://www.w3.org/2003/05/soap-envelope" xmlns:xsd="http://ekuatia.set.gov.py/sifen/xsd">
<soap:Header/>
<soap:Body>
<xsd:rEnvioLote>
<xsd:dId>202601172053097</xsd:dId>
<xsd:xDE>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</xsd:xDE></xsd:rEnvioLote></soap:Body></soap:Envelope>
```

### Respuesta SIFEN:
``` respuesta SIFEN:
```xml
<?xml version="1.0" encoding="UTF-8"?>
<env:Envelope xmlns:env="http://www.w3.org/2003/05/soap-envelope">
<env:Header/>
<env:Body>
<ns2:rRetEnviDe xmlns:ns2="http://ekuatia.set.gov.py/sifen/xsd">
<ns2:rProtDe>
<ns2:dFecProc>2026-01-17T20:53:09-03:00</ns2:dFecProc>
<ns2:dEstRes>Rechazado</ns2:dEstRes>
<ns2:gResProc>
<ns2:dCodRes>0160</ns2:dCodRes>
<ns2:dMsgRes>XML Mal Formado.</ns2:dMsgRes>
</ns2:gResProc>
</ns2:rProtDe>
</ns2:rRetEnviDe>
</env:Body>
</env:Envelope>
```

## 4. Análisis de Integridad ZIP Final

### Extracción y validación del xDE:
```bash
✅ xDE extraído: 5280 caracteres
✅ Base64 decodificado: 3960 bytes
✅ lote.xml extraído: 7425 bytes
✅ SHA256 de lote.xml: 074d297ba7bd3179df33adc6a6ebdcd4e5ae6c545534950774764e88b6cf2a7d
✅ Validación XSD: VÁLIDO
❌ Verificación firma: ERROR (falló al encontrar Signature)
```

### XML final (estructura verificada):
```xml
<?xml version="1.0" encoding="UTF-8"?>
<rLoteDE xmlns="http://ekuatia.set.gov.py/sifen/xsd">
<rDE Id="rDE01800123458001001000000112026010911234567891">
  <dVerFor>150</dVerFor>
  <DE Id="01800123458001001000000112026010911234567891">
    <!-- contenido del DE -->
  </DE>
  <Signature xmlns="http://ekuatia.set.gov.py/sifen/xsd">
    <!-- firma -->
  </Signature>
</rDE>
</rLoteDE>
```

## 5. Cambios Aplicados al Passthrough

Se modificó `build_lote_passthrough_signed()` para:

1. **Remover xsi:schemaLocation** que causa error 0160
2. **Agregar atributo Id** a rDE si falta (requerido por XSD)
3. - **Corregir namespace de Signature** para usar xmlns SIFEN

### Código modificado:
```python
# Remover schemaLocation
rde_str = re.sub(r'\s*xsi:schemaLocation="[^"]*"', '', rde_str, flags=re.DOTALL)

# Agregar Id a rDE si falta
if 'Id' not in rde_elem.attrib:
    rde_id = f"rDE{de_elem.get('Id')}"
    rde_elem.set('Id', rde_id)

# Corregir namespace de Signature
lote_str = lote_str.replace(
    '<Signature xmlns="http://www.w3.org/2000/09/xmldsig#">',
    '<Signature xmlns="http://ekuatia.set.gov.py/sifen/xsd">'
)
```

## 6. Estado Actual de la Investigación

### ✅ Corregido:
- SOAP action con URI completa
- rDE con atributo Id
- xsi:schemaLocation removido
- dVerFor como primer hijo
- XML válido contra XSD

### ❌ Problemas persistentes:
- La firma digital se invalida al modificar el XML después de firmado
- SIFEN sigue devolviendo 0160

## 7. Conclusión

El error 0160 persiste porque cualquier modificación al XML después de firmado invalida la firma. Las soluciones implementadas (agregar Id, remover schemaLocation, cambiar namespace) son necesarias pero deben aplicarse ANTES de firmar el XML.

**Recomendación:** Usar el flujo normal de firma (`build_and_sign_lote_from_xml`) en lugar del passthrough para poder aplicar todas las correcciones antes de la firma.

### Comandos de verificación finales:
```bash
# Extraer y verificar lote enviado
unzip -p artifacts/soap_last_request_SENT.xml xDE > xDE.zip
unzip -p xDE.zip lote.xml > lote_final.xml

# Validar XSD
python3 -c "
from lxml import etree
xsd = etree.XMLSchema(etree.parse('schemas_sifen/rLoteDE_v150.xsd'))
xml = etree.parse('lote_final.xml')
print('Válido XSD:', xsd.validate(xml))
"

# Verificar firma
xmlsec1 --verify --insecure --id-attr:Id DE lote_final.xml
```

## 8. Actualización - Investigación de IDs duplicados

### Evidencia de IDs en XML original y final:
```bash
# XML original (_debug_lote_xml_final_sent.xml):
<rDE xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance" xsi:schemaLocation="...">
<DE Id="01800123458001001000000112026010911234567891">

# XML final enviado (lote_latest.xml):
<rDE Id="rDE01800123458001001000000112026010911234567891">
<DE Id="01800123458001001000000112026010911234567891">
```

### Verificación de duplicación:
```bash
grep -n 'Id="' artifacts/_debug_lote_xml_final_sent.xml | head -n 20
# Output: Solo DE tiene Id, rDE no tiene Id

grep -n 'Id="' lote_latest.xml | head -n 20  
# Output: rDE tiene Id="rDE0180...", DE tiene Id="0180..."
# Resultado: ✅ IDs son DIFERENTES
```

### Estado actual de la implementación:
- ✅ rDE Id agregado correctamente: "rDE" + DE@Id
- ✅ IDs son únicos y diferentes
- ✅ xsi:schemaLocation removido
- ✅ Signature namespace cambiado a SIFEN
- ✅ dVerFor presente como primer hijo
- ❌ Firma local falla (posiblemente por cambio de namespace)
- ❌ SIFEN sigue devolviendo 0160

### Último test ejecutado:
```bash
SIFEN_SKIP_RUC_GATE=1 SIFEN_EMISOR_RUC="4554737-8" python3 -m tools.send_sirecepde --env test --xml "artifacts/_debug_lote_xml_final_sent.xml" --dump-http

# Respuesta SIFEN:
<dCodRes>0160</dCodRes>
<dMsgRes>XML Mal Formado.</dMsgRes>
<dEstRes>Rechazado</dEstRes>
```

### Conclusión final:
El error 0160 persiste a pesar de:
1. IDs únicos en rDE y DE
2. XML válido contra XSD
3. Todos los elementos requeridos presentes
4. Namespace SOAP correcto

El problema parece estar relacionado con la modificación del XML después de firmado. Aunque las correcciones son necesarias (agregar Id a rDE, remover schemaLocation), cambiar el namespace de Signature invalida la firma. SIFEN podría estar rechazando el XML porque:
- La firma no coincide con el XML modificado
- SIFEN podría requerir el namespace XMLDSig estándar en Signature

**Recomendación final:** Aplicar todas las correcciones ANTES de firmar el XML usando el flujo normal en lugar del passthrough.
