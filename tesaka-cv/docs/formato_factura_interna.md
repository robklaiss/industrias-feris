# Formato de Factura Interna

Este documento describe el formato JSON de entrada para el convertidor de facturas internas a formato Tesaka de importación.

## Estructura General

La factura interna es un objeto JSON con los siguientes campos principales:

```json
{
  "issue_date": "2024-01-15",
  "issue_datetime": "2024-01-15 10:30:00",
  "buyer": { ... },
  "transaction": { ... },
  "items": [ ... ],
  "retention": { ... }
}
```

## Campos

### issue_date (string, requerido)
- Formato: `YYYY-MM-DD`
- Fecha de emisión de la factura
- Se mapea a `atributos.fechaCreacion` en el formato Tesaka

### issue_datetime (string, opcional)
- Formato: `YYYY-MM-DD HH:mm:SS`
- Fecha y hora de emisión de la factura
- Si está presente, se mapea a `atributos.fechaHoraCreacion` en el formato Tesaka

### buyer (objeto, requerido)
Información del comprador/informado. Campos:

- **situacion** (string, requerido): Valores permitidos:
  - `CONTRIBUYENTE`
  - `NO_CONTRIBUYENTE`
  - `NO_RESIDENTE`

- **nombre** (string, requerido): Nombre del comprador

- **ruc** (string, opcional): RUC del contribuyente. Requerido si `situacion = CONTRIBUYENTE`

- **dv** (string, opcional): Dígito verificador. Requerido si `situacion = CONTRIBUYENTE`

- **tipoIdentificacion** (string, opcional): Tipo de identificación. Requerido si `situacion ≠ CONTRIBUYENTE`

- **identificacion** (string, opcional): Número de identificación. Requerido si `situacion ≠ CONTRIBUYENTE`

- **correoElectronico** (string, opcional): Correo electrónico. Requerido si `situacion ≠ CONTRIBUYENTE`

- **pais** (string, opcional): País. Requerido si `situacion = NO_RESIDENTE`

- **tieneRepresentante** (boolean, opcional): Indica si tiene representante. Requerido si `situacion = NO_RESIDENTE`

- **tieneBeneficiario** (boolean, opcional): Indica si tiene beneficiario. Requerido si `situacion = NO_RESIDENTE`

- **representante** (objeto, opcional): Datos del representante (si `tieneRepresentante = true`):
  - `tipoIdentificacion` (string, requerido)
  - `identificacion` (string, requerido)
  - `nombre` (string, requerido)

- **beneficiario** (objeto, opcional): Datos del beneficiario (si `tieneBeneficiario = true`):
  - `tipoIdentificacion` (string, requerido)
  - `identificacion` (string, requerido)
  - `nombre` (string, requerido)

- **domicilio** (string, opcional): Domicilio del comprador

- **direccion** (string, opcional): Dirección del comprador

- **telefono** (string, opcional): Teléfono del comprador

### transaction (objeto, requerido)
Información de la transacción:

- **condicionCompra** (string, requerido): `CONTADO` | `CREDITO`

- **cuotas** (integer, opcional): Número de cuotas. Requerido si `condicionCompra = CREDITO`

- **tipoComprobante** (integer, requerido): Valores permitidos: `1`, `5`, `11`, `17`, `18`, `19`, `20`

- **numeroComprobanteVenta** (string, requerido): Formato `999-999-9[9..]`
  - Nota: Debe ser string (no number) y debe preservar ceros a la izquierda (ej: '001-001-00000001').

- **numeroTimbrado** (string, requerido): 8 dígitos o `"0"` para casos especiales

- **fecha** (string, opcional): Fecha de la transacción en formato `YYYY-MM-DD`. Si no se proporciona, se usa `issue_date`

### items (array, requerido)
Lista de ítems de la factura. Cada ítem contiene:

- **cantidad** (number, requerido): Cantidad (máximo 2 decimales)

- **tasaAplica** (integer, requerido): Valores permitidos: `0`, `5`, `10`

- **precioUnitario** (number, requerido): Precio unitario (máximo 2 decimales si moneda extranjera)

- **descripcion** (string, requerido): Descripción del ítem (máximo 300 caracteres)

### retention (objeto, requerido)
Información de retención:

- **fecha** (string, requerido): Formato `YYYY-MM-DD`

- **moneda** (string, requerido): Valores permitidos: `EUR`, `PYG`, `USD`, `BRL`

- **tipoCambio** (integer, opcional): Tipo de cambio (entero positivo). Requerido si `moneda ≠ PYG`

- **retencionRenta** (boolean, requerido): Indica si hay retención de renta

- **conceptoRenta** (string, opcional): Concepto de renta. Requerido si `retencionRenta = true`

- **retencionIva** (boolean, requerido): Indica si hay retención de IVA

- **conceptoIva** (string, opcional): Concepto de IVA. Requerido si `retencionIva = true`

- **rentaPorcentaje** (number, requerido): Valores permitidos: `0`, `0.4`, `0.5`, `1`, `1.5`, `2`, `2.4`, `3`, `4.5`, `8`, `10`, `15`, `20`, `30`

- **ivaPorcentaje5** (number, requerido): Valores permitidos: `0`, `0.90909`, `10`, `30`, `50`, `70`, `100`

- **ivaPorcentaje10** (number, requerido): Valores permitidos: `0`, `0.90909`, `30`, `50`, `70`, `100`

- **rentaCabezasBase** (number, requerido): Base de renta por cabezas (puede ser 0)

- **rentaCabezasCantidad** (number, requerido): Cantidad de renta por cabezas (puede ser 0)

- **rentaToneladasBase** (number, requerido): Base de renta por toneladas (puede ser 0)

- **rentaToneladasCantidad** (number, requerido): Cantidad de renta por toneladas (puede ser 0)

## Conversión a Formato Tesaka

El convertidor mapea los campos de la factura interna al formato Tesaka de importación:

- `issue_date` → `atributos.fechaCreacion`
- `issue_datetime` → `atributos.fechaHoraCreacion` (si existe)
- `buyer` → `informado`
- `transaction` → `transaccion` (con `fecha` usando `transaction.fecha` o `issue_date` como fallback)
- `items` → `detalle`
- `retention` → `retencion`

El resultado es un array con un único comprobante que es validado contra el schema de importación antes de ser escrito.

