# Resumen de Requisitos - Comprobantes Virtuales Tesaka

## Estructura General

Ambos formatos (Importación y Exportación) tienen como raíz un **ARRAY** de comprobantes.

---

## IMPORTACIÓN

### Estructura Base
- **Raíz**: Array de comprobantes
- Cada comprobante contiene: `atributos`, `informado`, `transaccion`, `detalle`, `retencion`

### Campos Principales

#### 1. Atributos
- `fechaCreacion` (string, requerido): Formato YYYY-MM-DD
- `fechaHoraCreacion` (string, opcional): Formato YYYY-MM-DD HH:mm:SS

#### 2. Informado (Objeto requerido)
- `situacion` (string, requerido): Valores permitidos:
  - `CONTRIBUYENTE`
  - `NO_CONTRIBUYENTE`
  - `NO_RESIDENTE`
- `nombre` (string, requerido): Siempre requerido
- `domicilio` (string, opcional)
- `direccion` (string, opcional)
- `telefono` (string, opcional)

**Reglas condicionales según `situacion`:**

**Si `situacion = CONTRIBUYENTE`:**
- `ruc` (string, requerido)
- `dv` (string, requerido)

**Si `situacion ≠ CONTRIBUYENTE`:**
- `tipoIdentificacion` (string, requerido)
- `identificacion` (string, requerido)
- `correoElectronico` (string, requerido)

**Si `situacion = NO_RESIDENTE`:**
- `pais` (string, requerido)
- `tieneRepresentante` (boolean, requerido)
- `tieneBeneficiario` (boolean, requerido)
- Si `tieneRepresentante = true`: objeto `representante` con:
  - `tipoIdentificacion` (string, requerido)
  - `identificacion` (string, requerido)
  - `nombre` (string, requerido)
- Si `tieneBeneficiario = true`: objeto `beneficiario` con:
  - `tipoIdentificacion` (string, requerido)
  - `identificacion` (string, requerido)
  - `nombre` (string, requerido)

**Valores especiales:**
- `INNOMINADO_COOPERATIVA`: `identificacion = "44444402"`, `nombre = "SOCIOS INNOMINADOS (COOPERATIVAS)"`
- `INNOMINADOS_JUEGOS_DE_AZAR`: `identificacion = "44444403"`, `nombre = "BENEFICIARIOS INNOMINADOS (JUEGOS AZAR)"`

#### 3. Transacción (Objeto requerido)
- `condicionCompra` (string, requerido): `CONTADO` | `CREDITO`
- `cuotas` (integer, requerido si `condicionCompra = CREDITO`)
- `tipoComprobante` (integer, requerido): Valores permitidos: `1`, `5`, `11`, `17`, `18`, `19`, `20`
- `numeroComprobanteVenta` (string, requerido): Patrón `999-999-9[9..]` (con excepciones descritas en el documento)
- `numeroTimbrado` (string, requerido): 8 dígitos
  - Para `NO_CONTRIBUYENTE` o `NO_RESIDENTE`:
    - Debe ser `"0"` si `tipoComprobante = 1` o `11`
    - Debe ser `"0"` si `tipoComprobante` está en `{17, 18, 19, 20}`
- `fecha` (string, requerido): Formato YYYY-MM-DD

#### 4. Detalle (Array requerido)
Cada ítem del array contiene:
- `cantidad` (number, requerido): Máximo 2 decimales
- `tasaAplica` (integer, requerido): Valores permitidos: `0`, `5`, `10`
- `precioUnitario` (number, requerido): Máximo 2 decimales si moneda extranjera
- `descripcion` (string, requerido): Máximo 300 caracteres

#### 5. Retención (Objeto requerido)
- `fecha` (string, requerido): Formato YYYY-MM-DD
- `moneda` (string, requerido): Valores permitidos: `EUR`, `PYG`, `USD`, `BRL`
- `tipoCambio` (integer, requerido si `moneda ≠ PYG`): Debe ser entero positivo sin decimales
- `retencionRenta` (boolean, requerido)
- `conceptoRenta` (string, requerido si `retencionRenta = true`)
- `retencionIva` (boolean, requerido)
- `conceptoIva` (string, requerido si `retencionIva = true`)
- `rentaPorcentaje` (number, requerido): Valores permitidos: `0`, `0.4`, `0.5`, `1`, `1.5`, `2`, `2.4`, `3`, `4.5`, `8`, `10`, `15`, `20`, `30`
- `ivaPorcentaje5` (number, requerido): Valores permitidos: `0`, `0.90909`, `10`, `30`, `50`, `70`, `100`
- `ivaPorcentaje10` (number, requerido): Valores permitidos: `0`, `0.90909`, `30`, `50`, `70`, `100`
- `rentaCabezasBase` (number, requerido): Puede ser 0
- `rentaCabezasCantidad` (number, requerido): Puede ser 0
- `rentaToneladasBase` (number, requerido): Puede ser 0
- `rentaToneladasCantidad` (number, requerido): Puede ser 0

---

## EXPORTACIÓN

### Estructura Base
- **Raíz**: Array de comprobantes
- Cada comprobante contiene: `datos`, `estado`, `recepcion`

### Campos Principales

#### 1. Datos (Objeto)
Contiene los mismos campos de importación pero agrupados en un objeto `datos`:
- `atributos`: Incluye `fechaCreacion`, `fechaHoraCreacion` (opcional), `uuid` (string), `version` (string)
- `id` (string)
- `informante` (objeto): Incluye campos como:
  - `domicilioEmision` (string)
  - `telefono` (string)
  - `nombreFantasia` (string)
  - `codigoEstablecimiento` (string)
  - `timbradoFactura` (string)
  - `puntoExpedicionFactura` (string)
  - `inicioVigenciaFactura` (string)
  - `timbradoComprobante` (string)
  - `puntoExpedicionComprobante` (string)
  - `inicioVigenciaComprobante` (string)
  - Y otros campos según especificación
- `informado`
- `transaccion`
- `detalle`
- `totales` (objeto con campos calculados):
  - `valorTotalExento` (number)
  - `valorTotalAl5` (number)
  - `valorTotalAl10` (number)
  - `valorTotal` (number)
  - `impuestoTotalExento` (number)
  - `impuestoTotalAl5` (number)
  - `impuestoTotalAl10` (number)
  - `impuestoTotal` (number)
- `retencion` (objeto): Incluye campos de entrada más campos calculados:
  - Campos calculados: `ivaBase5`, `ivaBase10`, `ivaTotal5`, `ivaTotal10`, `rentaBase`, `rentaTotal`, `retencionTotal`, `retencionIvaTotal`, `retencionRentaTotal`, `rentaCabezasTotal`, `rentaToneladasTotal`
  - Campos "Nombre": `monedaNombre` (string), `conceptoRentaNombre` (string), `conceptoIvaNombre` (string)

#### 2. Estado (String)
- Ejemplo: `"enviado"`
- Indica el estado del comprobante

#### 3. Recepción (Objeto)
Campos de respuesta del sistema según especificación:
- `fechaProceso` (string)
- `numeroComprobante` (string)
- `numeroControl` (string)
- `cadenaControl` (string)
- `recepcionCorrecta` (boolean)
- `mensajeRecepcion` (string)
- `procesamientoCorrecto` (boolean)
- `mensajeProcesamiento` (string)
- `hash` (string)
- Campos adicionales que pueden aparecer en ejemplos:
  - `codigoProcesamiento` (string)
  - `numero` (string)
  - `fechaRecepcion` (string)

### Enums y Tablas de Referencia

#### Monedas
- `PYG`
- `EUR`
- `USD`
- `BRL`

#### Tipos de Comprobante
- `1`
- `5`
- `11`
- `17`
- `18`
- `19`
- `20`

---

## Diferencias Clave: Importación vs Exportación

1. **Estructura**:
   - **Importación**: Campos directamente en la raíz del comprobante
   - **Exportación**: Campos agrupados en objeto `datos`, más `estado` y `recepcion`

2. **Campos Calculados**:
   - **Importación**: No incluye totales ni retención calculada
   - **Exportación**: 
     - `totales` incluye: valorTotalExento, valorTotalAl5, valorTotalAl10, valorTotal, impuestoTotalExento, impuestoTotalAl5, impuestoTotalAl10, impuestoTotal
     - `retencion` incluye campos calculados: ivaBase5, ivaBase10, ivaTotal5, ivaTotal10, rentaBase, rentaTotal, retencionTotal, retencionIvaTotal, retencionRentaTotal, rentaCabezasTotal, rentaToneladasTotal, y campos "Nombre": monedaNombre, conceptoRentaNombre, conceptoIvaNombre

3. **Campos Adicionales**:
   - **Exportación**: Incluye `id`, `informante`, `estado`, `recepcion` (información de respuesta del sistema)

4. **Validación**:
   - **Importación**: Valida datos de entrada antes de enviar
   - **Exportación**: Valida estructura de respuesta recibida del sistema

