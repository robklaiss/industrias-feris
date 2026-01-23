# Generador de Facturas Electrónicas SIFEN

Este sistema permite generar facturas electrónicas SIFEN basadas en el modelo proporcionado, manteniendo la estructura exacta requerida por la SET.

## Archivos Creados

### 1. Template (`templates/factura_template.xml`)
Plantilla Jinja2 con la estructura exacta de la factura SIFEN. Incluye:
- Todos los campos requeridos por el XSD v150
- Placeholders para datos dinámicos
- Estructura para múltiples items, pagos y actividades económicas

### 2. Generador (`tools/generar_factura.py`)
Módulo principal que contiene:
- `generar_factura()`: Función para generar XML a partir de datos
- `datos_ejemplo()`: Datos de ejemplo basados en la factura modelo

### 3. Ejemplo (`examples/ejemplo_factura.py`)
Script completo que muestra:
- Cómo usar el generador con datos personalizados
- Cálculo automático de totales
- Generación de CDC

## Uso Básico

### Generar factura con datos de ejemplo:
```bash
cd tesaka-cv
python3 tools/generar_factura.py
```

### Generar factura con datos personalizados:
```bash
cd tesaka-cv
python3 examples/ejemplo_factura.py
```

## Estructura de Datos

### Datos Requeridos

#### Emisor
```python
{
    "dRucEm": "4009031",        # RUC del emisor
    "dDVEmi": "0",              # Dígito verificador
    "dNomEmi": "NOMBRE EMISOR", # Razón social
    "dDirEmi": "DIRECCIÓN",     # Dirección
    "cDepEmi": "12",            # Código departamento
    "dDesDepEmi": "CENTRAL",    # Nombre departamento
    "cCiuEmi": "165",           # Código ciudad
    "dDesCiuEmi": "VILLA ELISA",# Nombre ciudad
    "dTelEmi": "(021) 123456",  # Teléfono
    "dEmailE": "email@emisor.com", # Email
    "gActEco": [                # Actividades económicas
        {"cActEco": "47211", "dDesActEco": "Descripción actividad"}
    ]
}
```

#### Receptor
```python
{
    "dRucRec": "7524653",       # RUC receptor
    "dDVRec": "8",              # Dígito verificador
    "dNomRec": "NOMBRE CLIENTE", # Razón social
    "dEmailRec": "email@cliente.com", # Email
    # Campos opcionales para persona natural
    "dDirRec": "Dirección",
    "cDepRec": "12",
    "dDesDepRec": "CENTRAL",
    "cCiuRec": "165",
    "dDesCiuRec": "VILLA ELISA",
    "dTelRec": "(021) 654321"
}
```

#### Items
```python
{
    "dDesProSer": "DESCRIPCIÓN DEL PRODUCTO", # Descripción
    "cUniMed": "77",              # Código unidad medida
    "dDesUniMed": "UNI",          # Nombre unidad medida
    "dCantProSer": "5",           # Cantidad
    "dPUniProSer": "26000",       # Precio unitario
    "dTotBruOpeItem": "130000",   # Total bruto
    "dDescItem": "0",             # Descuento
    "dTotOpeItem": "130000",      # Total operación
    # Datos de IVA
    "iAfecIVA": "1",              # 1=Gravado, 2=Exento
    "dDesAfecIVA": "Gravado IVA",
    "dPropIVA": "100",            # Proporción IVA
    "dTasaIVA": "5",              # Tasa IVA (5, 10)
    "dBasGravIVA": "123810",      # Base gravada
    "dLiqIVAItem": "6190",        # Líquido IVA
    "dBasExe": "0"                # Base exenta
}
```

#### Pagos
```python
{
    "iTiPago": "1",               # 1=Efectivo, 2=Cheque, etc.
    "dDesTiPag": "Efectivo",      # Descripción forma pago
    "dMonTiPag": "250000",        # Monto
    "cMoneTiPag": "PYG",          # Moneda
    "dDMoneTiPag": "Guaraní"      # Nombre moneda
}
```

## Campos Importantes

### CDC (Código de Identificación)
El CDC debe seguir el formato: `0104{RUC}{DV}001001{NroDoc}{Fecha}{CodSeg}`

### dCodSeg (Código de Seguridad)
- 9 dígitos numéricos
- Debe ser único para cada factura

### Fechas
Formato: `YYYY-MM-DDTHH:MM:SS`
Ejemplo: `2026-01-19T11:57:10`

## Consideraciones

1. **Firma Digital**: El XML generado debe ser firmado digitalmente antes de enviar a SIFEN
2. **Validación**: El XML debe validarse contra el XSD v150
3. **Timbrado**: Usa tus datos reales de timbrado
4. **Cálculos**: Verifica que los cálculos de IVA sean correctos

## Próximos Pasos

1. Integrar con el sistema de firma existente
2. Conectar con el envío a SIFEN
3. Agregar validaciones adicionales
4. Implementar generación automática de CDC

## Ejemplo de XML Generado

```xml
<?xml version="1.0" encoding="UTF-8" standalone="no"?>
<rDE xmlns="http://ekuatia.set.gov.py/sifen/xsd" xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance" xsi:schemaLocation="http://ekuatia.set.gov.py/sifen/xsd siRecepDE_Ekuatiai_v150.xsd">
    <dVerFor>150</dVerFor>
<DE Id="01040090310001001000011912026011911890577982">
    <dDVId>2</dDVId>
    <dFecFirma>2026-01-19T11:57:10</dFecFirma>
    <!-- ... resto del XML ... -->
</DE>
</rDE>
```

## Dependencias

- Python 3.7+
- Jinja2: `pip install Jinja2`

## Soporte

Para dudas o consultas, revisa la documentación en `docs/` o los ejemplos en `examples/`.
