# SIFEN Signature Placement

Este documento explica cómo usar las herramientas creadas para diagnosticar y arreglar el problema de la ubicación de la firma XMLDSig en SIFEN.

## Problema

SIFEN rechaza los XML con el error:
```
Firma difiere del estándar. [El documento XML no tiene firma]
```

El XML actual muestra `</DE><ds:Signature>`, o sea la Signature está FUERA del elemento DE. SIFEN espera que Signature esté DENTRO de DE (enveloped signature).

## Herramientas Creadas

### 1. Herramienta de Inspección

**Archivo**: `tools/sifen_inspect_signature.py`

Analiza un XML firmado y muestra información detallada sobre la ubicación de la firma.

```bash
# Inspeccionar XML firmado actual
.venv/bin/python tools/sifen_inspect_signature.py ~/Desktop/sifen_de_firmado_test.xml
```

**Salida esperada**:
```
📄 INSPECCIÓN DE FIRMA SIFEN
📁 Archivo: /Users/user/Desktop/sifen_de_firmado_test.xml
🏗️  Elemento raíz: rDE
📋 Estructura XML: dVerFor → DE → Signature

🔍 ELEMENTO DE:
   ✅ Encontrado: Sí
   🆔 ID: TESTDE001

✍️  FIRMA DIGITAL:
   ✅ Encontrada: Sí
   👆 Parent: rDE
   📍 Ubicación: Signature como hijo de rDE (fuera de DE)
   🔗 Reference URI: #TESTDE001
   ✅ Coincide con DE/@Id: Sí

🎯 VEREDICTO SIFEN:
   ❌ RECHAZADO: La firma está fuera del elemento DE
   💡 SIFEN espera: Signature como hijo de DE (enveloped signature)
```

### 2. Herramienta para Mover Firma

**Archivo**: `tools/sifen_move_signature_into_de.py`

Mueve la firma de rDE a dentro del elemento DE (fix one-off).

```bash
# Mover firma dentro de DE
.venv/bin/python tools/sifen_move_signature_into_de.py \
    ~/Desktop/sifen_de_firmado_test.xml \
    --out ~/Desktop/sifen_de_firmado_sig_in_de.xml \
    --verify
```

**Salida esperada**:
```
📄 Procesando: /Users/user/Desktop/sifen_de_firmado_test.xml
🏗️  Elemento raíz: rDE
📍 Ubicación actual: Signature como hijo de rDE
📋 Elemento DE encontrado (Id: TESTDE001)
🔄 Moviendo Signature a DE...
✅ Signature movida exitosamente
💾 Guardado: /Users/user/Desktop/sifen_de_firmado_sig_in_de.xml

🔍 Verificando colocación de la firma...
✅ Verificación exitosa: Signature está dentro de DE

📊 Resumen:
   📁 Entrada: /Users/user/Desktop/sifen_de_firmado_test.xml
   📁 Salida: /Users/user/Desktop/sifen_de_firmado_sig_in_de.xml
   📏 Tamaño: 15420 caracteres
   ✅ Signature está dentro de DE
```

### 3. Feature Flag en el Firmador

**Archivo**: `tesaka-cv/app/sifen_client/xmldsig_signer.py`

Se agregó un feature flag para controlar la ubicación de la firma:

```bash
# Comportamiento nuevo (default): Signature dentro de DE
export SIFEN_SIGNATURE_PARENT=DE

# Comportamiento original: Signature fuera de DE (en rDE)
export SIFEN_SIGNATURE_PARENT=RDE
```

**Ejemplo de uso**:

```bash
# Generar XML firmado con Signature dentro de DE
export SIFEN_SIGNATURE_PARENT=DE
.venv/bin/python tools/generate_signed_de_to_desktop.py --out ~/Desktop/sifen_de_firmado_parent_de.xml

# Generar XML firmado con Signature fuera de DE (comportamiento anterior)
export SIFEN_SIGNATURE_PARENT=RDE
.venv/bin/python tools/generate_signed_de_to_desktop.py --out ~/Desktop/sifen_de_firmado_parent_rde.xml
```

### 4. Pruebas Automáticas

**Archivo**: `tests/test_signature_placement.py`

Pruebas unitarias para verificar el comportamiento del feature flag.

```bash
# Ejecutar pruebas
.venv/bin/python -m pytest tests/test_signature_placement.py -v
```

## Flujo de Trabajo Recomendado

### Paso 1: Diagnóstico

```bash
# Inspeccionar el XML actual
.venv/bin/python tools/sifen_inspect_signature.py ~/Desktop/sifen_de_firmado_test.xml
```

Verificar que el problema es efectivamente la ubicación de la firma.

### Paso 2: Prueba Rápida (One-off)

```bash
# Crear versión con firma dentro de DE
.venv/bin/python tools/sifen_move_signature_into_de.py \
    ~/Desktop/sifen_de_firmado_test.xml \
    --out ~/Desktop/sifen_de_firmado_sig_in_de.xml \
    --verify

# Verificar el resultado
.venv/bin/python tools/sifen_inspect_signature.py ~/Desktop/sifen_de_firmado_sig_in_de.xml
```

### Paso 3: Probar con SIFEN

1. Subir `sifen_de_firmado_sig_in_de.xml` al prevalidador SIFEN
2. Enviar por SOAP mTLS usando el script existente
3. Verificar si el error cambia de "no tiene firma" a otro

### Paso 4: Implementación Permanente

```bash
# Configurar el feature flag para producción
export SIFEN_SIGNATURE_PARENT=DE

# Generar nuevos XML firmados correctamente
.venv/bin/python tools/generate_signed_de_to_desktop.py --out ~/Desktop/factura_correcta.xml
```

## Comandos de Verificación

### Verificar patrón en XML

```bash
# Buscar firma fuera de DE (patón incorrecto)
grep -n "</DE><ds:Signature>" ~/Desktop/sifen_de_firmado_test.xml

# Buscar firma dentro de DE (patrón correcto)
grep -n "<ds:Signature>.*</DE>" ~/Desktop/sifen_de_firmado_sig_in_de.xml
```

### Comparar estructuras

```bash
# Inspeccionar ambos XML
.venv/bin/python tools/sifen_inspect_signature.py ~/Desktop/sifen_de_firmado_test.xml
.venv/bin/python tools/sifen_inspect_signature.py ~/Desktop/sifen_de_firmado_sig_in_de.xml
```

## Envío por SOAP mTLS

Usar el método existente (sin cambios):

```bash
# Enviar por SOAP mTLS (mismo comando que antes)
curl -X POST https://sifen-test.set.gov.py/de/ws/sync/recibe.wsdl \
  -H "Content-Type: application/soap+xml; charset=utf-8" \
  --cert cert.pem --key key.pem \
  -d @soap_request.xml
```

## Criterio de Éxito

- ✅ El prevalidador SIFEN deja de decir "no tiene firma"
- ✅ Si hay error, debe ser diferente (ej: digest inválido, referencia, etc.)
- ✅ Eso confirma que SIFEN reconoce la firma y pasamos al siguiente problema

## Troubleshooting

### Error: "lxml no está disponible"
```bash
.venv/bin/pip install lxml
```

### Error: "signxml no está disponible"
```bash
.venv/bin/pip install signxml
```

### Error: Certificado no encontrado
Verificar que el certificado P12 exista y la contraseña sea correcta.

### Error: XML inválido
Verificar que el XML de entrada esté bien formado y tenga la estructura esperada.

## Resumen de Cambios

1. **tools/sifen_inspect_signature.py**: Herramienta de diagnóstico
2. **tools/sifen_move_signature_into_de.py**: Fix one-off para mover firma
3. **xmldsig_signer.py**: Feature flag `SIFEN_SIGNATURE_PARENT` (default: DE)
4. **tests/test_signature_placement.py**: Pruebas automáticas
5. **docs/SIFEN_SIGNATURE_PLACEMENT.md**: Esta documentación

Todo implementado sin romper scripts existentes, con feature flags para compatibilidad backward.
