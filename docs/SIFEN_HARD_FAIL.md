OBJETIVO: Generar los “2 XML de muestra” que pide SIFEN para el ticket/habilitación, usando NUESTRO codebase y dejando ambos archivos listos (XML + firma + QR) y validados en el Prevalidador.

REQUISITOS:
- No inventar estructura: usar los scripts existentes del repo.
- Cada XML debe pasar: ✅ XML y Firma Válidos (Prevalidador).
- Los 2 XML deben ser distintos (casos diferentes) y representativos.
- Firma y QR coherentes (usar wrapper para recalcular QR).
- No exponer secretos (CSC, credenciales). Usar env-file de test.
- Guardar outputs con nombres claros y una carpeta de entrega.

CASOS A GENERAR (2 XML):
A) FACTURA CONTADO (IVA 10%) – 2 ítems – receptor contribuyente (RUC)
B) FACTURA CRÉDITO (IVA 10%) – 1 ítem – receptor NO contribuyente (CI)  (si el schema/flujo lo soporta; si no, usar receptor contribuyente pero con condición crédito)

PASOS (hacer en este orden):
1) Preparar carpeta de entrega:
   mkdir -p ~/Desktop/sifen_entrega_xml

2) Elegir ambiente de TEST y cargar secretos desde archivo:
   - Usar: --env test y --env-file .env.test (o el que exista)
   - Confirmar que SIFEN_IDCSC_TEST y SIFEN_CSC_TEST están presentes.

3) Para cada caso (A y B):
   3.1) Crear/actualizar el JSON de entrada del DE con datos del caso.
        - Guardar como:
          data/case_A.json
          data/case_B.json
        - Usar datos reales del emisor (RUC/timbrado/establecimiento/punto) del sistema.
        - Cambiar SOLO lo necesario para diferenciar:
          - condición: contado vs crédito
          - cantidad de ítems / totales
          - receptor (RUC vs CI si aplica)
   3.2) Generar XML final (firmado + QR recalculado) usando el wrapper:
        ./tools/make_de_wrapper.sh \
          --env test \
          --env-file .env.test \
          --gen '.venv/bin/python tools/generar_prevalidador.py --json data/case_A.json --out /tmp/sifen_de.xml' \
          --sign 'echo "YA FIRMA EL GENERADOR"' \
          --out '~/Desktop/sifen_entrega_xml/DE_CASE_A_signed.xml'

        Repetir para CASE_B (cambiando json y nombre de salida).

   3.3) Verificación local automática:
        - grep de los tags clave para que quede evidencia:
          grep -n "<cCondOpe>" -n ~/Desktop/sifen_entrega_xml/DE_CASE_*.xml
          grep -n "<dCarQR>" ~/Desktop/sifen_entrega_xml/DE_CASE_*.xml
        - Confirmar que los dos CDC/Id (atributo DE Id="...") son distintos.

4) Validación en Prevalidador:
   - Subir ambos XML y confirmar que ambos dan “XML y Firma Válidos”.
   - Guardar capturas (screenshot) en:
     ~/Desktop/sifen_entrega_xml/prevalidador_case_A.png
     ~/Desktop/sifen_entrega_xml/prevalidador_case_B.png

ENTREGABLES FINALES:
- ~/Desktop/sifen_entrega_xml/DE_CASE_A_signed.xml
- ~/Desktop/sifen_entrega_xml/DE_CASE_B_signed.xml
- Capturas del prevalidador (png) para adjuntar al ticket.

NOTAS IMPORTANTES:
- El QR debe ser generado DESPUÉS de la firma (wrapper ya lo hace).
- Si el case_B con CI no aplica a nuestro iNatRec/iTiContRec, entonces hacer crédito con receptor RUC igualmente, pero manteniendo “crédito” como diferencia.

SALIDA ESPERADA:
- Un listado final de archivos generados + confirmación de que ambos pasaron el prevalidador.# SIFEN v150 - Hard Fail para Firmas Reales

## Objetivo Crítico

**DEJAR DE GENERAR XML "FIRMADO" CON VALORES DUMMY_*.**
Si no se puede firmar con la clave privada real, el script debe ABORTAR (exit != 0).

## Cambios Implementados

### 1. Eliminados Archivos con Dummy

Se eliminaron los siguientes archivos que generaban valores `dummy_*`:
- `tesaka-cv/tools/generate_test_xml_v2.py` ❌ ELIMINADO
- `tools/create_dummy_xml.py` ❌ ELIMINADO

### 2. Builder con Hard Fail

**Archivo**: `tools/sifen_build_artifacts_real.py`

Validaciones implementadas:
```python
def validate_no_dummy_values(xml_path: Path) -> None:
    """Valida que no haya valores dummy_* en el XML firmado"""
    content = xml_path.read_text(encoding='utf-8')
    
    dummy_values = [
        'dummy_digest_value',
        'dummy_signature_value',
        'dummy_certificate'
    ]
    
    for dummy in dummy_values:
        if dummy in content:
            print(f"❌ ERROR: Se encontró valor dummy: {dummy}")
            sys.exit(2)  # HARD FAIL
```

### 3. Verificador Criptográfico

**Archivo**: `tools/sifen_signature_crypto_verify.py`

Valida que la firma sea real:
- DigestValue > 20 caracteres
- SignatureValue > 200 caracteres  
- X509Certificate empieza con "MI"
- Opcional: verificación con xmlsec1

### 4. Test de Firma Real

**Archivo**: `tools/test_real_signature.py`

Intenta firmar con certificado real:
- Si el certificado es inválido: ❌ HARD FAIL (exit 2)
- Si el certificado es válido: ✅ XML con firma real

## Flujo de Ejecución

### Opción 1: Test Rápido
```bash
export SIFEN_CERT_PATH="/path/to/cert.p12"
export SIFEN_CERT_PASS="password"
.venv/bin/python tools/test_real_signature.py
```

### Opción 2: Builder Completo
```bash
export SIFEN_CERT_PATH="/path/to/cert.p12"
export SIFEN_CERT_PASS="password"
export SIFEN_CSC="ABCD0000000000000000000000000000"
.venv/bin/python tools/sifen_build_artifacts_real.py
```

### Opción 3: Verificación Post-Firma
```bash
.venv/bin/python tools/sifen_signature_crypto_verify.py ~/Desktop/sifen_de_firmado_test.xml
```

## Comportamiento Esperado

### ✅ Si el certificado es VÁLIDO:
```
=== TEST DE FIRMA REAL SIFEN v150 ===
📋 Certificado: /path/to/cert.p12
🔐 Intentando firmar XML de prueba...
✅ XML firmado guardado: /tmp/test_signed.xml
🔍 Verificando firma...
✅ FIRMA REAL EXITOSA
   El certificado y clave son válidos
✅ Copiado a: ~/Desktop/sifen_de_firmado_test.xml
```

### ❌ Si el certificado es INVÁLIDO:
```
=== TEST DE FIRMA REAL SIFEN v150 ===
📋 Certificado: /path/to/cert.p12
🔐 Intentando firmar XML de prueba...
❌ ERROR: No se pudo firmar el XML
   Detalles: Error al convertir certificado P12: Contraseña incorrecta
🔧 Posibles soluciones:
   1. Verificar que el certificado P12 sea válido
   2. Verificar la contraseña del certificado
   3. Verificar que el certificado tenga clave privada
```
**Exit code: 2** (HARD FAIL)

### ❌ Si se genera XML con dummy_*:
```
❌ ERROR: Se encontró valor dummy: dummy_digest_value
   El XML no está firmado correctamente
```
**Exit code: 2** (HARD FAIL)

## Validaciones del Firmador

El firmador `app/sifen_client/xmldsig_signer.py` ya estaba configurado para:
- ✅ Cargar P12/PFX real con password
- ✅ Extraer PrivateKey real (no mock)
- ✅ Calcular DigestValue SHA256 real del Reference
- ✅ Generar SignatureValue RSA-SHA256 real
- ✅ Insertar KeyInfo con el CERT LEAF real (base64 empieza con 'MI')

## Resultado Final

**El archivo `~/Desktop/sifen_de_firmado_test.xml` NUNCA MÁS contendrá `dummy_*`.**

Si no hay clave/certificado correcto, el build falla explícitamente con exit 2.

## Comandos de Verificación

```bash
# Verificar que no hay dummy
XML=~/Desktop/sifen_de_firmado_test.xml
grep -nE "dummy_(digest|signature|certificate)" "$XML" && echo "❌ NO está firmado" || echo "✅ No hay dummy_*"

# Verificar tamaños de firma real
python - <<'PY'
from lxml import etree
p = "$XML"
doc = etree.parse(p)
ns = {"ds":"http://www.w3.org/2000/09/xmldsig#"}
dv = doc.xpath("string(//ds:DigestValue)", namespaces=ns).strip()
sv = doc.xpath("string(//ds:SignatureValue)", namespaces=ns).strip()
xc = doc.xpath("string(//ds:X509Certificate)", namespaces=ns).strip()
print("DigestValue len:", len(dv))
print("SignatureValue len:", len(sv))
print("X509Certificate starts with MI:", xc.startswith("MI"))
ok = (len(dv) > 20 and len(sv) > 200 and xc.startswith("MI"))
print("✅ Firma real" if ok else "❌ Placeholder")
PY
```

## Status

✅ **IMPLEMENTACIÓN COMPLETA - HARD FAILS ACTIVOS**
