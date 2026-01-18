# Resumen de Intentos para Error 0160

## Estado Actual
- SIFEN devuelve error 0160 "XML Mal Formado"
- Todas las validaciones locales pasan (XSD, firma, estructura)
- El doble wrapper <rLoteDE> fue corregido exitosamente

## Cambios Probados

### 1. ✅ Doble Wrapper <rLoteDE>
- **Problema**: El XML tenía doble wrapper
- **Solución**: Modificar `build_xde_zip_bytes_from_lote_xml` para detectar wrapper existente
- **Estado**: CORREGIDO - El XML ahora tiene un solo wrapper

### 2. ✅ Estructura del XML
- dVerFor presente como primer hijo de rDE ✅
- rDE tiene atributo Id ✅
- rDE y DE tienen IDs diferentes ✅
- Sin prefijos ds: ✅

### 3. ❓ Namespace de Signature
- **Probado**: Cambiar xmlns de Signature a SIFEN
- **Resultado**: Sigue dando 0160

### 4. ❓ gCamFuFD
- **Probado**: Agregar gCamFuFD después de Signature
- **Resultado**: Sigue dando 0160

### 5. ❓ Formato del XML
- **Probado**: XML con y sin pretty print
- **Resultado**: Sigue dando 0160

### 6. ❓ SOAP Envelope
- **Probado**: Con y sin prefijos (xsd:)
- **Resultado**: Sigue dando 0160

## Análisis del XML Actual
```xml
<rLoteDE xmlns="http://ekuatia.set.gov.py/sifen/xsd">
  <rDE Id="rDE01800455473701001000000120260118113224123456789">
    <dVerFor>150</dVerFor>
    <DE Id="01800455473701001000000120260118113224123456789">
      <!-- contenido válido -->
    </DE>
    <Signature xmlns="http://www.w3.org/2000/09/xmldsig#">
      <!-- firma válida -->
    </Signature>
  </rDE>
</rLoteDE>
```

## Próximos Pasos Sugeridos
1. **Comparar byte-by-byte** con un XML exitoso de TIPS
2. **Verificar headers HTTP** exactos que envía TIPS
3. **Revisar orden de atributos** dentro de los elementos
4. **Verificar si hay elementos opcionales** faltantes
5. **Contactar a SIFEN** para obtener más detalles del error 0160

## Comandos Útiles
```bash
# Extraer y verificar XML del ZIP
unzip -p artifacts/soap_last_request_SENT.xml xDE > xDE.zip
unzip -p xDE.zip xml_file.xml > lote_actual.xml

# Verificar firma
xmlsec1 --verify --insecure --id-attr:Id DE lote_actual.xml

# Validar XSD
python3 -c "from lxml import etree; xsd = etree.XMLSchema(etree.parse('schemas_sifen/rLoteDE_v150.xsd')); xml = etree.parse('lote_actual.xml'); print('Válido XSD:', xsd.validate(xml))"
```
