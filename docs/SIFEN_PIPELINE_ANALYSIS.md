# Análisis del Pipeline XML en send_sirecepde

## Objetivo
Identificar el punto exacto donde el XML de entrada (que ya viene firmado) se vuelve a parsear/serializar/encapsular, causando que el fix/sanitizer no se aplique o se aplique tarde.

## Pipeline Mapeado (send_sirecepde.py)

### Etapa A: Lectura del XML input
- **Función**: `send_sirecepde()` (línea ~4700)
- **Código**: `xml_bytes = xml_path.read_bytes()`
- **Instrumentación**: Stage `01_input`

### Etapa B: Limpieza inicial
- **Función**: `build_and_sign_lote_from_xml()` (línea ~2876)
- **Código**: Remoción de xsi:schemaLocation con regex
- **Instrumentación**: Stage `02_clean_xsi`

### Etapa C: Parsing inicial
- **Función**: `build_and_sign_lote_from_xml()` (línea ~2913)
- **Código**: `xml_root = etree.fromstring(xml_bytes, parser=parser)`
- **Instrumentación**: Stage `03_parsed`
- **⚠️ Punto crítico**: Aquí lxml puede cambiar namespaces/prefixes

### Etapa D: Extracción/construcción rDE
- **Función**: `build_and_sign_lote_from_xml()` (línea ~2927)
- **Código**: Extraer rDE del XML parseado
- **Sin cambios en XML** (solo lectura)

### Etapa E: Firmado (si aplica)
- **Función**: `sign_de_with_p12()` en `xmlsec_signer.py`
- **Código**: Si el XML ya está firmado, NO re-firma
- **⚠️ Punto crítico**: Si no está firmado, aplica sanitizer aquí

### Etapa F: Construcción del lote
- **Función**: `build_and_sign_lote_from_xml()` (línea ~3560)
- **Código**: Serialización con `etree.tostring(lote_final, ...)`
- **Instrumentación**: Stage `10_lote_serialized`
- **⚠️ Punto crítico**: Primera serialización después del parsing

### Etapa G: Compresión ZIP
- **Función**: `build_and_sign_lote_from_xml()` (línea ~3684)
- **Código**: Crear ZIP con lote.xml
- **Instrumentación**: Stage `11_zip_created`

### Etapa H: Validación del ZIP
- **Función**: `build_and_sign_lote_from_xml()` (línea ~3712)
- **Código`: `lote_xml_from_zip = zf.read("lote.xml")`
- **Instrumentación**: Stage `12_from_zip`

### Etapa I: Construcción SOAP
- **Función**: `build_r_envio_lote_xml()` (línea ~4392)
- **Código**: `etree.tostring(rEnvioLote, ...)` 
- **Instrumentación**: Stage `13_soap_payload`

## Puntos Problemáticos Identificados

### 1. Parsing con lxml (Etapa C)
```python
xml_root = etree.fromstring(xml_bytes, parser=parser)
```
- lxml puede reordenar atributos
- Puede cambiar default namespace declarations
- Puede normalizar prefijos

### 2. Serialización del lote (Etapa F)
```python
lote_xml_bytes = etree.tostring(lote_final, ...)
```
- Aunque usa `pretty_print=False`, puede cambiar:
  - Orden de atributos
  - Namespace declarations
  - Encoding specifics

## Solución Propuesta: Evitar Re-serialización

Si el XML de entrada ya viene firmado:

### Opción 1: Preservar bytes originales
```python
# En build_and_sign_lote_from_xml()
if xml_already_signed:
    # NO parsear el XML firmado
    # Extraer rDE como bytes puros
    rde_bytes = extract_rde_raw_bytes(xml_bytes)
    # Usar bytes directamente en el ZIP
    zip_bytes = create_zip_with_rde_bytes(rde_bytes)
```

### Opción 2: Sanitizer ANTES de firmar
```python
# En sign_de_with_p12()
# Aplicar sanitizer al XML ANTES de la firma
xml_bytes = _sanitize_xmldsig_prefixes(xml_bytes)
xml_bytes = normalize_rde_before_sign(xml_bytes)
# Luego firmar
signed_bytes = xmlsec.sign_tree(key, tree)
```

## Comandos para Reproducir

```bash
# 1. Ejecutar con instrumentación
cd /Users/robinklaiss/Dev/industrias-feris-facturacion-electronica-simplificado
python test_pipeline_debug.py

# 2. Ver hashes generados
ls -la artifacts/_stage_*.xml

# 3. Comparar etapas donde cambia el hash
diff artifacts/_stage_01_input.xml artifacts/_stage_03_parsed.xml

# 4. Extraer lote del SOAP enviado (para verificación final)
unzip -p artifacts/soap_last_request_SENT.xml xDE > xDE.zip
unzip -p xDE.zip lote.xml > lote_from_SENT.xml

# 5. Verificar firma
xmlsec1 --verify --insecure --id-attr:Id DE lote_from_SENT.xml
```

## Archivos Clave a Modificar

1. **`send_sirecepde.py`**: Agregar instrumentación (ya hecho)
2. **`xmlsec_signer.py`**: Mover sanitizer antes de firmar
3. **`send_sirecepde.py`**: Detectar XML ya firmado y evitar re-parseo

## Recomendación

Implementar la Opción 1 (preservar bytes originales) cuando el XML ya viene firmado, ya que:
- No invalida la firma existente
- Evita cualquier transformación de lxml
- Mantiene exactamente los bytes que se enviaron originalmente
