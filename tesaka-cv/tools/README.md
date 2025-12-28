# Herramientas de Desarrollo SIFEN

Este directorio contiene herramientas para trabajar con documentos electrónicos SIFEN.

## Descargar Esquemas XSD Oficiales

Descarga los esquemas XSD oficiales desde el portal de SIFEN:

```bash
python -m tools.download_xsd
```

Esto descargará los XSD en el directorio `schemas_sifen/`.

**Fuente**: https://ekuatia.set.gov.py/sifen/xsd/

## Validar XML contra XSD

Valida un archivo XML contra el esquema XSD oficial:

### Validación automática (detecta schema según elemento raíz)

```bash
# Validación básica (estructura + XSD)
# Auto-detecta el schema según el elemento raíz del XML:
# - rEnviDe => usa WS_SiRecepDE_v150.xsd (siRecepDE)
# - rDE => usa siRecepDE_v150.xsd
# - DE => usa DE_v150.xsd
python -m tools.validate_xml archivo.xml

# También prevalidar con servicio SIFEN
python -m tools.validate_xml archivo.xml --prevalidate
```

### Validación manual (especificar schema)

```bash
# Validar DE crudo
python -m tools.validate_xsd --schema de archivo_de.xml

# Validar siRecepDE (rEnviDe)
python -m tools.validate_xsd --schema sirecepde archivo_sirecepde.xml

# Especificar XSD manualmente
python -m tools.validate_xml archivo.xml --xsd schemas_sifen/WS_SiRecepDE_v150.xsd

# Especificar directorio de XSD
python -m tools.validate_xml archivo.xml --xsd-dir /ruta/a/schemas_sifen
```

## Ejecutar Herramientas desde el Repo Raíz

Para evitar problemas de `ModuleNotFound: tools`, usa el script `run_tools` en el repo raíz:

```bash
# Desde el repo raíz
./run_tools smoketest --input examples/de_input.json
./run_tools oracle_compare --input examples/de_input.json
./run_tools validate_xml artifacts/test.xml
```

El script `run_tools` detecta automáticamente el venv (`.venv/bin/python`) o usa el Python del sistema.

O desde cualquier directorio usando path absoluto:

```bash
/path/to/repo/run_tools smoketest --input tesaka-cv/examples/de_input.json
```

## Smoke Test End-to-End

Comando único que ejecuta todo el flujo de validación:

```bash
./run_tools smoketest --input examples/de_input.json
```

### Flujo del Smoke Test

1. **Genera DE Python** → `smoke_python_de.xml`
2. **Valida estructura XML** → Verifica XML bien formado
3. **Valida XSD v150** → Valida contra `DE_v150.xsd`
4. **Genera DE Node (si disponible)** → `smoke_node_de.xml` usando xmlgen
5. **Valida XSD DE Node** → Valida contra `DE_v150.xsd`
6. **Genera siRecepDE** → `smoke_sirecepde.xml` desde DE Python
7. **Valida estructura siRecepDE** → Verifica XML bien formado
8. **Valida XSD WS** → Valida contra `WS_SiRecepDE_v150.xsd`
9. **Compara Python vs Node** → Genera diff en `smoke_diff.txt`
10. **Resumen final** → Estado por etapa (OK/FAIL/SKIPPED)

### Artifacts Generados

Todos los artifacts se guardan en `artifacts/`:
- `smoke_python_de.xml` - DE generado con nuestra implementación Python
- `smoke_node_de.xml` - DE generado con xmlgen (solo si Node está disponible)
- `smoke_sirecepde.xml` - siRecepDE (envelope) generado
- `smoke_diff.txt` - Comparación entre DE Python y Node

### Manejo de Errores

- **Exit code 0**: Todo lo disponible pasó (SKIPPED está OK)
- **Exit code 1**: Alguna etapa falló (FAIL)
- **SKIPPED**: Normal si Node/xmlgen no está instalado (no es un error)

### Ejemplo de Salida

```
======================================================================
SMOKE TEST END-TO-END SIFEN
======================================================================
📄 Input: examples/de_input.json
📦 Artifacts: /path/to/artifacts

1️⃣  Generando DE con implementación Python...
   ✅ Generado: smoke_python_de.xml

2️⃣  Validando estructura XML (DE Python)...
   ✅ XML bien formado

3️⃣  Validando XSD v150 (DE Python)...
   ✅ Válido según DE_v150.xsd

4️⃣  Generando DE con xmlgen (Node.js)...
   ⏭️  SKIPPED: Node/xmlgen no disponible
      Instalar: cd tesaka-cv/tools/node && npm install

...

======================================================================
RESUMEN SMOKE TEST
======================================================================

Estado por etapa:
  ✅ DE Python generado: OK
  ✅ Estructura XML (DE Python): OK
  ✅ XSD v150 (DE Python): OK
  ⏭️ DE Node generado: SKIPPED
  ✅ siRecepDE generado: OK
  ✅ XSD WS (siRecepDE): OK

📊 Totales: OK=6, FAIL=0, SKIPPED=3

✅ SMOKE TEST COMPLETADO
```

## Oráculo de Validación (Oracle Compare)

El sistema de oráculo compara nuestra implementación Python con `facturacionelectronicapy-xmlgen` (Node.js) para validar que ambos generen XMLs compatibles.

### Instalación

1. **Instalar dependencias Node para xmlgen:**
   ```bash
   cd tesaka-cv/tools/node
   npm install
   ```
   
   Esto instalará `facturacionelectronicapy-xmlgen` desde GitHub.

2. **Verificar que Node.js está instalado:**
   ```bash
   node --version  # Debe ser v14+
   ```
   
   Si Node.js no está instalado:
   - macOS: `brew install node`
   - Linux: Ver instrucciones oficiales de Node.js
   - Windows: Descargar desde nodejs.org

### Troubleshooting

**Error: "El paquete facturacionelectronicapy-xmlgen no está instalado"**
- Ejecuta: `cd tesaka-cv/tools/node && npm install`

**Error: "node no está instalado o no está en PATH"**
- Instala Node.js v14+ desde nodejs.org o con tu gestor de paquetes

**Error: "ModuleNotFound: tools"**
- Usa `./run_tools` desde el repo raíz, o ejecuta desde `tesaka-cv/`:
  ```bash
  cd tesaka-cv
  python -m tools.oracle_compare --input examples/de_input.json
  ```

**Error: "generateXMLDE no está disponible"**
- El módulo puede tener una estructura de export diferente
- Revisa el README de `facturacionelectronicapy-xmlgen` para la forma correcta de importar
- Verifica que el paquete está actualizado: `cd tesaka-cv/tools/node && npm update`

### Uso del Oráculo

Desde el repo raíz (recomendado):
```bash
./run_tools oracle_compare --input tesaka-cv/examples/de_input.json
```

O desde `tesaka-cv/`:
```bash
cd tesaka-cv
python -m tools.oracle_compare --input examples/de_input.json
```

Opciones:
```bash
# Modo estricto (falla si hay diferencias)
./run_tools oracle_compare --input tesaka-cv/examples/de_input.json --strict

# Omitir xmlgen (solo validar nuestra implementación)
./run_tools oracle_compare --input tesaka-cv/examples/de_input.json --skip-xmlgen

# Especificar directorio de artifacts
./run_tools oracle_compare --input tesaka-cv/examples/de_input.json --artifacts-dir artifacts/
```

### Flujo del Oráculo

1. **Genera DE con nuestra implementación Python** → `artifacts/oracle_python_de_*.xml`
2. **Valida contra XSD v150 (DE_v150.xsd)** → Verifica que pasa validación
3. **Mapea input a formato xmlgen** → Crea `params.json`, `data.json`, `options.json` temporales en artifacts
4. **Genera DE con xmlgen (Node.js)** → Usa `tools/node/xmlgen_runner.cjs` → `artifacts/oracle_xmlgen_de_*.xml`
5. **Valida xmlgen DE contra XSD v150 (DE_v150.xsd)** → Verifica compatibilidad
6. **Compara campos clave** → Extrae y compara campos importantes
7. **Genera reporte de diferencias** → `artifacts/oracle_diff_*.txt` (siempre se genera, incluso si son iguales)

### Campos Requeridos por xmlgen

El paquete `facturacionelectronicapy-xmlgen` requiere campos específicos en `params` y `data`:

**params.establecimientos** (requerido - array no vacío):
```json
{
  "establecimientos": [
    {
      "codigo": "001",           // Requerido: código del establecimiento
      "denominacion": "Nombre",  // Requerido: nombre del establecimiento
      "ciudad": "1",             // Requerido: código numérico de ciudad válido según SIFEN
      "distrito": "1",           // Requerido: código numérico de distrito válido según SIFEN
      "departamento": "1",       // Requerido: código numérico de departamento válido según SIFEN
      "telefono": "021123456"    // Opcional: teléfono (6-15 caracteres)
    }
  ]
}
```

⚠️ **Importante**: Los códigos de `ciudad`, `distrito` y `departamento` deben ser códigos válidos según las constantes de SIFEN. El mapeo automático usa valores por defecto que pueden no ser válidos para todas las localidades. Si necesitas usar códigos específicos, asegúrate de que coincidan con los códigos oficiales de SIFEN.

**params.actividadesEconomicas** (requerido - array no vacío):
```json
{
  "actividadesEconomicas": ["47110"]  // Códigos de actividad económica SIFEN
}
```

**data.establecimiento** (requerido):
- Debe ser un string que coincida **exactamente** con `params.establecimientos[].codigo`
- Ejemplo: si `establecimientos[0].codigo = "001"`, entonces `data.establecimiento = "001"`

**data.cliente** (requerido):
```json
{
  "cliente": {
    "contribuyente": true,          // boolean: si el cliente es contribuyente
    "tipoOperacion": 1,             // 1=B2B, 2=B2C, 3=B2G, 4=B2F
    "razonSocial": "Nombre",        // Requerido
    "pais": "PRY",                  // Requerido: código ISO (PRY = Paraguay)
    "ruc": "80012345-7",            // Requerido si contribuyente=true (formato: RUC-DV)
    "tipoContribuyente": 1          // Requerido si contribuyente=true (1=Nacional)
  }
}
```

**data.factura** (requerido para tipoDocumento=1):
```json
{
  "factura": {
    "tipoTransaccion": 1,           // 1 = Venta de mercadería
    "presencia": 1                   // 1=Operación presencial, 2=Electrónica, etc.
  }
}
```

**data.condicion** (requerido):
```json
{
  "condicion": {
    "tipo": 1,                      // 1=Contado, 2=Crédito
    "entregas": [                   // Requerido cuando tipo=1 (Contado)
      {
        "tipo": 1,                  // 1=Efectivo
        "descripcion": "Efectivo",
        "moneda": "PYG"
      }
    ]
  }
}
```

**data.items[].iva** y **data.items[].ivaProporcion**:
- `iva`: Debe ser la **tasa** de IVA (0, 5, o 10), NO el monto calculado
- `ivaProporcion`: Debe ser 100 cuando `ivaTipo=1` (gravado), 0 cuando `ivaTipo=2` o `3` (exonerado/exento)

El mapeo automático en `map_input_to_xmlgen_format()` genera estos campos con valores por defecto si no están presentes en el input JSON.

### Artifacts Generados

Al ejecutar el oráculo, se generan los siguientes archivos en `artifacts/`:

- `oracle_python_de_<timestamp>.xml` - DE generado con nuestra implementación Python
- `oracle_xmlgen_de_<timestamp>.xml` - DE generado con xmlgen (Node.js)
- `oracle_diff_<timestamp>.txt` - Reporte de comparación y diferencias
- `xmlgen_params_<timestamp>.json` - Parámetros temporales para xmlgen
- `xmlgen_data_<timestamp>.json` - Datos temporales para xmlgen
- `xmlgen_options_<timestamp>.json` - Opciones temporales para xmlgen

### Campos Comparados

- Elemento raíz y namespaces
- `dFecEmi`, `dHorEmi` (fecha/hora emisión)
- `dRucEm`, `dDVEm` (RUC emisor y DV)
- `dRucRec`, `dDVRec` (RUC receptor y DV)
- `Id` (CDC)
- Cantidad de ítems
- Totales: `dTotGralOpe`, `dIVA10`, `dIVA5`, `dTotalGs`

### Formato de Input JSON

El oráculo usa un formato común `de_input.json`:

```json
{
  "buyer": {
    "ruc": "80012345",
    "dv": "7",
    "nombre": "Empresa Ejemplo S.A."
  },
  "transaction": {
    "numeroTimbrado": "12345678",
    "numeroComprobanteVenta": "001-001-00000001",
    "tipoComprobante": 1
  },
  "items": [
    {
      "cantidad": 10.5,
      "precioUnitario": 1000.0,
      "descripcion": "Producto",
      "tasaAplica": 10
    }
  ]
}
```

Ver `examples/de_input.json` para formato completo.

## Requisitos

- Python 3.8+
- `lxml` (ya incluido en requirements.txt)
- `requests` (para descargar XSD)
- **Para oráculo:** Node.js 14+ y npm (para xmlgen)

## Enviar XML siRecepDE al Servicio SOAP de SIFEN

Envía un XML siRecepDE (rEnviDe) al servicio SOAP de Recepción de SIFEN:

```bash
# Enviar archivo específico a ambiente de pruebas
python -m tools.send_sirecepde --env test --xml artifacts/sirecepde_20251226_233653.xml

# Enviar el archivo más reciente
python -m tools.send_sirecepde --env test --xml latest

# Enviar a producción
python -m tools.send_sirecepde --env prod --xml latest
```

### Configuración de Certificados mTLS

El servicio SIFEN requiere autenticación mTLS (mutual TLS) con certificados cliente.

#### Opción 1: Certificados PEM (recomendado)

Configura en tu `.env`:

```bash
SIFEN_CERT_PEM=/ruta/a/cert.pem
SIFEN_KEY_PEM=/ruta/a/key.pem
SIFEN_CA_BUNDLE=/ruta/a/ca-bundle.pem  # Opcional
```

#### Opción 2: Convertir P12 a PEM en macOS

Si tienes un certificado `.p12`, conviértelo a PEM:

```bash
# Extraer certificado (sin clave privada)
openssl pkcs12 -in certificado.p12 -out cert.pem -clcerts -nokeys -password pass:TU_PASSWORD

# Extraer clave privada (sin certificado)
openssl pkcs12 -in certificado.p12 -out key.pem -nocerts -nodes -password pass:TU_PASSWORD

# (Opcional) Extraer certificados CA
openssl pkcs12 -in certificado.p12 -out ca-bundle.pem -cacerts -nokeys -password pass:TU_PASSWORD
```

Luego configura en `.env`:

```bash
SIFEN_CERT_PEM=/ruta/completa/cert.pem
SIFEN_KEY_PEM=/ruta/completa/key.pem
SIFEN_CA_BUNDLE=/ruta/completa/ca-bundle.pem
```

### WSDL

El CLI usa los siguientes WSDL oficiales:

- **Test**: `https://sifen-test.set.gov.py/de/ws/recepcion/DERecepcion.wsdl`
- **Prod**: `https://sifen.set.gov.py/de/ws/recepcion/DERecepcion.wsdl`

Puedes sobrescribirlos con variables de entorno:
- `SIFEN_WSDL_RECEPCION_TEST`
- `SIFEN_WSDL_RECEPCION_PROD`

### Respuestas

Las respuestas del servicio se guardan automáticamente en `artifacts/response_*.json` para auditoría.

## Flujo Completo de Validación

### 1. Descargar XSDs

```bash
python -m tools.download_xsd
```

### 2. Generar DE y siRecepDE

```bash
# Generar DE crudo
python -m tools.build_de --output artifacts/de_test.xml

# Generar siRecepDE (wrapper de recepción)
python -m tools.build_sirecepde --de artifacts/de_test.xml --output artifacts/sirecepde_test.xml
```

### 3. Validar XSD

```bash
# Validación automática
python -m tools.validate_xml artifacts/de_test.xml
python -m tools.validate_xml artifacts/sirecepde_test.xml

# Validación manual
python -m tools.validate_xsd --schema de artifacts/de_test.xml
python -m tools.validate_xsd --schema sirecepde artifacts/sirecepde_test.xml
```

### 4. Oráculo de Validación

```bash
# Comparar con xmlgen
python -m tools.oracle_compare --input examples/de_input.json
```

### 5. Enviar a SIFEN (requiere certificados)

```bash
python -m tools.send_sirecepde --env test --xml artifacts/sirecepde_test.xml
```

## Notas

- Los XSD deben descargarse primero antes de validar
- El validador intenta resolver imports/includes automáticamente
- Si el Prevalidador devuelve HTML (aplicación web), se informa que requiere uso manual
- El envío SOAP requiere certificados mTLS configurados correctamente
- El oráculo requiere Node.js y xmlgen instalado (opcional pero recomendado)

