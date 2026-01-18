# Fix SOAP Action URI para error 0160

## Cambio aplicado
Se corrigió el SOAP action en el Content-Type header para usar la URI completa del namespace SIFEN en lugar de solo el nombre de la operación.

## Archivos modificados
1. `app/sifen_client/soap_client.py`:
   - Línea 1615: Se cambió `action="siRecepLoteDE"` por `action="http://ekuatia.set.gov.py/sifen/xsd/siRecepLoteDE"`
   - Línea 1359: Se cambió `action="siConsDE"` por `action="http://ekuatia.set.gov.py/sifen/xsd/siConsDE"`
   - Línea 156: Se actualizó el valor por defecto para usar la URI completa

## Justificación
Según SOAP 1.2 specification y las mejores prácticas de SIFEN, el action en el Content-Type debe ser una URI única que identifique la operación, no solo el nombre local. Esto ayuda al servidor a enrutar correctamente la petición SOAP.

## Resultado esperado
- El Content-Type header ahora muestra: `application/soap+xml; charset=utf-8; action="http://ekuatia.set.gov.py/sifen/xsd/siRecepLoteDE"`
- Esto debería resolver el error 0160 "XML Mal Formado" si era causado por un action incorrecto
- SIFEN debería procesar el lote y devolver un código diferente a 0160 (ej: 0300 si el lote es recibido correctamente)

## Comando para verificar
```bash
cd /Users/robinklaiss/Dev/industrias-feris-facturacion-electronica-simplificado/tesaka-cv
python3 test_soap_action.py
```
