# Smoketest SIFEN con Firma Real

## Descripción

El smoketest genera y valida DEs con **firma criptográfica REAL** usando certificado P12.

**Características:**
- ✅ Firma con certificado P12 real (NO dummy)
- ✅ SignatureMethod: `rsa-sha256`
- ✅ DigestMethod: `sha256`
- ✅ Canonicalization: `xml-exc-c14n#`
- ✅ Transforms: `enveloped-signature` + `xml-exc-c14n#`
- ✅ Signature con default namespace (sin prefijo `ds:`)
- ✅ Validación criptográfica con `signxml`
- ✅ Validación de perfil SIFEN v150
- ✅ Generación de siRecepDE sin `xmlns:ds` en root

## Requisitos

### 1. Variables de Entorno

```bash
export SIFEN_CERT_PATH="/ruta/completa/al/certificado.p12"
export SIFEN_CERT_PASS="password_del_certificado"
export SIFEN_CSC="12345678"  # Código de Seguridad del Contribuyente
```

### 2. Certificado P12 Válido

El certificado debe:
- Estar en formato PKCS#12 (.p12)
- Contener clave privada y certificado
- Ser válido (no vencido)
- Tener contraseña correcta

## Uso

### Opción 1: Script Helper (Recomendado)

1. Editar `tools/run_smoketest_with_cert.sh`:
   ```bash
   export SIFEN_CERT_PATH="/Users/tu_usuario/.sifen/certs/MI_CERT.p12"
   export SIFEN_CERT_PASS="mi_password_real"
   export SIFEN_CSC="12345678"
   ```

2. Ejecutar:
   ```bash
   cd tesaka-cv
   ./tools/run_smoketest_with_cert.sh
   ```

### Opción 2: Manual

```bash
cd tesaka-cv

# Configurar variables
export SIFEN_CERT_PATH="/ruta/al/cert.p12"
export SIFEN_CERT_PASS="password"
export SIFEN_CSC="12345678"

# Ejecutar smoketest
.venv/bin/python tools/smoketest.py \
  --input tools/de_input.json \
  --artifacts-dir /tmp/sifen_smoketest_artifacts
```

## Flujo del Smoketest

1. **Generar DE Python**
   - Genera XML base con `build_de_xml()`
   - Remueve cualquier Signature dummy existente
   - Firma con certificado P12 real usando `xmldsig_signer.py`

2. **Validar Firma Criptográfica**
   - Ejecuta `sifen_signature_crypto_verify.py`
   - Verifica con `signxml` y certificado embebido
   - Hard fail si la firma es inválida

3. **Validar Perfil de Firma**
   - Ejecuta `sifen_signature_profile_check.py`
   - Verifica algoritmos (sha256, rsa-sha256, exc-c14n)
   - Verifica estructura (Reference URI, Transforms)
   - Hard fail si no cumple perfil SIFEN v150

4. **Validar Estructura XML**
   - Verifica que el XML esté bien formado
   - Sin errores de sintaxis

5. **Validar XSD v150**
   - Valida contra `DE_v150.xsd`
   - Verifica todos los campos requeridos

6. **Generar siRecepDE**
   - Envuelve el DE firmado en `rEnviDe`
   - **NO agrega `xmlns:ds` al root**
   - Preserva la firma intacta

7. **Validar siRecepDE**
   - Estructura XML bien formada
   - Válido según `WS_SiRecepDE_v150.xsd`

## Salidas

### Artifacts Generados

```
/tmp/sifen_smoketest_artifacts/
├── smoke_python_de.xml          # DE firmado con certificado real
├── smoke_sirecepde.xml          # siRecepDE (rEnviDe) con DE firmado
└── smoke_diff.txt               # Comparación con xmlgen (si disponible)
```

### Verificación de Firma Real

```bash
# Verificar que NO hay valores dummy
grep -i "dummy" /tmp/sifen_smoketest_artifacts/smoke_python_de.xml
# Output: (vacío - no debe encontrar nada)

# Verificar algoritmos correctos
grep -E "rsa-sha256|sha256" /tmp/sifen_smoketest_artifacts/smoke_python_de.xml
# Output: debe mostrar rsa-sha256 y sha256

# Verificar que NO hay prefijo ds: en Signature
head -1 /tmp/sifen_smoketest_artifacts/smoke_python_de.xml | grep "ds:Signature"
# Output: (vacío - Signature debe tener default namespace)

# Verificar que siRecepDE NO tiene xmlns:ds duplicado en root
head -1 /tmp/sifen_smoketest_artifacts/smoke_sirecepde.xml | grep -o 'xmlns:ds=' | wc -l
# Output: 1 (solo una vez, necesario para prefijos ds: dentro del DE)
```

## Troubleshooting

### Error: "Contraseña del certificado P12 incorrecta"

**Causa:** `SIFEN_CERT_PASS` está mal configurado o el certificado está corrupto.

**Solución:**
```bash
# Verificar que la contraseña es correcta
openssl pkcs12 -in $SIFEN_CERT_PATH -noout -passin pass:$SIFEN_CERT_PASS
# Si falla, la contraseña es incorrecta
```

### Error: "SIFEN_CERT_PATH y SIFEN_CERT_PASS requeridos"

**Causa:** Variables de entorno no configuradas.

**Solución:**
```bash
export SIFEN_CERT_PATH="/ruta/completa/al/cert.p12"
export SIFEN_CERT_PASS="password"
```

### Error: "Certificado no existe"

**Causa:** Ruta al certificado incorrecta.

**Solución:**
```bash
# Verificar que el archivo existe
ls -la $SIFEN_CERT_PATH

# Usar ruta absoluta
export SIFEN_CERT_PATH="/Users/robinklaiss/.sifen/certs/MI_CERT.p12"
```

### Error: "Firma criptográfica inválida"

**Causa:** El signer no está generando firma correcta o el XML se alteró.

**Solución:**
1. Verificar que `xmldsig_signer.py` está usando algoritmos correctos
2. Verificar que el XML no se está modificando después de firmar
3. Ejecutar manualmente:
   ```bash
   .venv/bin/python tools/sifen_signature_crypto_verify.py \
     /tmp/sifen_smoketest_artifacts/smoke_python_de.xml
   ```

### Error: "Perfil de firma incorrecto"

**Causa:** La firma no cumple con el perfil SIFEN v150.

**Solución:**
1. Verificar algoritmos: debe ser `rsa-sha256` y `sha256`
2. Verificar canonicalización: debe ser `xml-exc-c14n#`
3. Verificar transforms: `enveloped-signature` + `xml-exc-c14n#`
4. Ejecutar manualmente:
   ```bash
   .venv/bin/python tools/sifen_signature_profile_check.py \
     /tmp/sifen_smoketest_artifacts/smoke_python_de.xml
   ```

## Diferencias con Versión Anterior

### Antes (Dummy)
- ❌ Firma con valores dummy: "this is a test"
- ❌ Algoritmos: `rsa-sha1` / `sha1`
- ❌ Canonicalización: `xml-c14n` (sin exclusive)
- ❌ Prefijo `ds:` en Signature
- ❌ No validación criptográfica

### Ahora (Real)
- ✅ Firma con certificado P12 real
- ✅ Algoritmos: `rsa-sha256` / `sha256`
- ✅ Canonicalización: `xml-exc-c14n#`
- ✅ Signature con default namespace (sin prefijo)
- ✅ Validación criptográfica completa
- ✅ Validación de perfil SIFEN v150

## Ejemplo de Salida Exitosa

```
======================================================================
SMOKE TEST END-TO-END SIFEN
======================================================================
📄 Input: tools/de_input.json
📦 Artifacts: /tmp/sifen_smoketest_artifacts

1️⃣  Generando DE con implementación Python...
   🔐 Firmando con certificado: MI_CERT.p12
   ✅ Generado: smoke_python_de.xml

1️⃣.5 Validando firma criptográfica...
   ✅ Firma criptográfica válida

1️⃣.6 Validando perfil de firma SIFEN...
   ✅ Perfil de firma correcto (sha256, exc-c14n)

2️⃣  Validando estructura XML (DE Python)...
   ✅ XML bien formado

3️⃣  Validando XSD v150 (DE Python)...
   ✅ Válido según DE_v150.xsd

4️⃣  Generando DE con xmlgen (Node.js)...
   ⏭️  SKIPPED: Node/xmlgen no disponible

6️⃣  Generando siRecepDE (rEnviDe)...
   ✅ Generado: smoke_sirecepde.xml

7️⃣  Validando estructura XML (siRecepDE)...
   ✅ XML bien formado

8️⃣  Validando XSD WS (siRecepDE)...
   ✅ Válido según WS_SiRecepDE_v150.xsd

======================================================================
RESUMEN SMOKE TEST
======================================================================

📊 Totales: OK=8, FAIL=0, SKIPPED=1

✅ SMOKE TEST COMPLETADO
```

## Notas Importantes

1. **Certificado Real Obligatorio:** El smoketest requiere certificado P12 real. No acepta valores dummy.

2. **Hard Fails:** Si la firma o validación falla, el smoketest termina con `exit 2`.

3. **Preservación de Firma:** El XML firmado NO se modifica al generar siRecepDE. La firma se preserva intacta.

4. **Namespace ds:** El root `rEnviDe` tiene `xmlns:ds` declarado (necesario para prefijos `ds:*` dentro del DE), pero NO está duplicado.

5. **Perfil SIFEN v150:** La firma cumple estrictamente con el perfil SIFEN v150 (sha256, exc-c14n, enveloped-signature).
