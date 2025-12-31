# Debug de lote.xml para siRecepLoteDE

## Problema

SIFEN responde HTTP 400 con `dCodRes=0160 "XML Mal Formado"` al llamar `siRecepLoteDE`.

## Herramientas de Debug

### 1. Extraer y analizar lote.xml del SOAP enviado

```bash
# Después de ejecutar send_sirecepde y obtener el error
python -m tools.debug_extract_lote_from_soap \
  --debug-file artifacts/soap_last_http_debug.txt \
  --output /tmp/lote_extracted.xml
```

Este script:
- Extrae el BASE64 de `<xDE>` del SOAP debug
- Decodifica y descomprime el ZIP
- Analiza `lote.xml`:
  - Tamaño, BOM, encoding
  - Root tag y namespace
  - Primeros 200 bytes
- Guarda `lote.xml` en `/tmp/lote_extracted.xml` para inspección

### 2. Validar lote.xml contra XSD

```bash
# Configurar directorio XSD
export SIFEN_XSD_DIR="rshk-jsifenlib/docs/set/ekuatia.set.gov.py/sifen/xsd"
export SIFEN_VALIDATE_XSD=1
export SIFEN_DEBUG_SOAP=1

# Ejecutar send_sirecepde (validará automáticamente)
python -m tools.send_sirecepde --env test --xml artifacts/sirecepde_rebuild.xml
```

La validación XSD:
- Extrae el `rDE` del XML completo (no valida el wrapper `rEnviDe`)
- Valida el `rDE` extraído contra `siRecepDE_v150.xsd` (o equivalente)
- Valida `lote.xml` (root `rLoteDE`) contra el XSD que declare `rLoteDE`
- Muestra hasta 30 errores numerados con línea/columna

## Estructura Esperada de lote.xml

Según la implementación de Roshka (rshk-jsifenlib):

```xml
<?xml version="1.0" encoding="UTF-8"?>
<rLoteDE xmlns="http://ekuatia.set.gov.py/sifen/xsd">
  <rDE>
    <dVerFor>150</dVerFor>
    <DE Id="...">...</DE>
    <Signature xmlns="http://www.w3.org/2000/09/xmldsig#">...</Signature>
    <gCamFuFD>...</gCamFuFD>
  </rDE>
</rLoteDE>
```

**Características importantes:**
- Root: `rLoteDE` con namespace SIFEN como default
- Contiene uno o más `rDE` como hijos directos
- Cada `rDE` debe tener el orden correcto: `dVerFor`, `DE`, `Signature`, `gCamFuFD`
- El ZIP debe contener exactamente un archivo llamado `lote.xml`
- Compresión: `ZIP_DEFLATED` (no `ZIP_STORED`)

## Checks de "XML Mal Formado"

### 1. Namespace correcto
- `rLoteDE` debe tener `xmlns="http://ekuatia.set.gov.py/sifen/xsd"` como default
- `rDE` debe heredar el namespace o declararlo explícitamente
- `Signature` debe usar `xmlns="http://www.w3.org/2000/09/xmldsig#"` (sin prefijo `ds:`)

### 2. Orden de hijos en rDE
- `dVerFor` (primero)
- `DE` (segundo)
- `Signature` (tercero)
- `gCamFuFD` (último)

### 3. Encoding y BOM
- XML declaration: `<?xml version="1.0" encoding="UTF-8"?>`
- Sin BOM (UTF-8 sin BOM)
- Sin caracteres fuera de UTF-8

### 4. Firma digital
- `Signature` debe conservarse intacta (no modificar después de firmar)
- Usar `deepcopy` al copiar `rDE` para no perder atributos/namespaces

### 5. ZIP
- Nombre del archivo: exactamente `lote.xml` (case-sensitive)
- Compresión: `ZIP_DEFLATED` (no `ZIP_STORED`)
- Un solo archivo en el ZIP

## Comandos de Verificación

### Verificar estructura del ZIP
```bash
# Extraer y listar contenido
python -m tools.debug_extract_lote_from_soap

# Ver contenido del lote.xml extraído
cat /tmp/lote_extracted.xml | head -50

# Verificar root y namespace
python3 << 'PY'
from lxml import etree
root = etree.parse("/tmp/lote_extracted.xml").getroot()
print(f"Root: {root.tag}")
print(f"Namespace: {root.nsmap}")
print(f"Children: {[c.tag for c in root]}")
PY
```

### Validar contra XSD local
```bash
# Si tienes el XSD de rLoteDE
export SIFEN_XSD_DIR="rshk-jsifenlib/docs/set/ekuatia.set.gov.py/sifen/xsd"
python3 << 'PY'
from pathlib import Path
from app.sifen_client.xsd_validator import validate_rde_and_lote

xsd_dir = Path("rshk-jsifenlib/docs/set/ekuatia.set.gov.py/sifen/xsd")
lote_bytes = Path("/tmp/lote_extracted.xml").read_bytes()

# Validar solo el lote (rDE no necesario aquí)
result = validate_rde_and_lote(
    rde_signed_bytes=b"<rDE/>",  # dummy
    lote_xml_bytes=lote_bytes,
    xsd_dir=xsd_dir
)

print(f"Lote OK: {result['lote_ok']}")
if result['lote_errors']:
    for err in result['lote_errors']:
        print(f"  - {err}")
PY
```

## Próximos Pasos

1. **Ejecutar debug_extract_lote_from_soap** después de un envío fallido
2. **Revisar el lote.xml extraído** para verificar estructura
3. **Validar contra XSD** si está disponible
4. **Comparar con implementación de Roshka** (código Java en `rshk-jsifenlib`)
5. **Ajustar build_lote_base64_from_single_xml** si hay diferencias

## Notas

- El XSD para `rLoteDE` puede no estar disponible como elemento global. En ese caso, la validación XSD del lote mostrará un warning pero no bloqueará el envío.
- La validación XSD del `rDE` (extraído) es más importante y debe pasar siempre.
- Si la validación XSD pasa pero SIFEN sigue rechazando, el problema puede estar en:
  - El contenido interno del `DE` (campos de negocio)
  - La firma digital (certificado, algoritmo, canonicalización)
  - El formato del ZIP (compresión, encoding)

