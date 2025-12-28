# Notas sobre Estructura XSD SIFEN V150

## Estructura de rDE (Root Element)

El elemento raíz `rDE` debe tener este orden:

1. `dVerFor` (requerido) - Versión del formato (150)
2. `DE` (requerido) - Documento Electrónico con atributo `Id` (CDC)
3. `ds:Signature` (requerido) - Firma digital XML
4. `gCamFuFD` (requerido) - Campos fuera de la firma digital

## Estructura de DE (tDE complexType)

El elemento `DE` debe tener:

**Atributos:**
- `Id` (requerido) - CDC (Código de Control) - tipo `tCDC`

**Elementos (en orden):**
1. `dDVId` (requerido) - Digito verificador del Id
2. `dFecFirma` (requerido) - Fecha y hora de firma
3. `dSisFact` (requerido) - Sistema de facturación (1 o 2)
4. `gOpeDE` (requerido) - Campos de operación
5. `gTimb` (requerido) - Datos del timbrado
6. `gDatGralOpe` (requerido) - Datos generales de la operación
7. `gDtipDE` (requerido) - Datos específicos del tipo de DE
8. `gTotSub` (opcional) - Totales y subtotales
9. `gCamGen` (opcional) - Campos generales (items)
10. `gCamDEAsoc` (opcional, max 99) - Documentos asociados

## Problema Actual

El XML generado actualmente usa `dg` en lugar de la estructura correcta `tDE`. 

La estructura `dg` (datos generales) ya no existe en la versión 150 del XSD. Los datos que estaban en `dg` ahora están en `gDatGralOpe` y `gDtipDE`.

## Próximos Pasos

1. Actualizar generador XML para usar estructura `tDE` correcta
2. Generar CDC (Código de Control) válido
3. Incluir todos los campos requeridos según el XSD

