# SIFEN Tools - Flujo END-TO-END

## Configuración Inicial

Antes de ejecutar cualquier script, configurar las variables de entorno:

```bash
export SIFEN_CERT_PATH="/Users/robinklaiss/.sifen/certs/TU_CERT_REAL.p12"
export SIFEN_CERT_PASS="tu_password_real"
export SIFEN_CSC="12345678"  # Código de Seguridad del Contribuyente
export SIFEN_ENV="TEST"      # TEST o PROD
```

## Scripts Disponibles

### 1. `sifen_build_artifacts_real.py`
Genera XML firmado con certificado real + SOAP envelope.

**Uso:**
```bash
.venv/bin/python tools/sifen_build_artifacts_real.py
```

**Salidas:**
- `~/Desktop/sifen_de_firmado_test.xml` - XML firmado con firma real
- `~/Desktop/sifen_de_prevalidador_firmado.xml` - XML sin gCamFuFD
- `/tmp/sifen_rEnviDe_soap12.xml` - SOAP envelope

**Hard Fails:**
- Exit 2 si encuentra `dummy_*` en DigestValue/SignatureValue/X509Certificate
- Exit 2 si no existe `ds:Signature`
- Exit 2 si verificación criptográfica falla

---

### 2. `sifen_signature_crypto_verify.py`
Verifica firma criptográfica del XML usando signxml + xmlsec1.

**Uso:**
```bash
.venv/bin/python tools/sifen_signature_crypto_verify.py <xml_path>
```

**Exit codes:**
- 0: Firma válida
- 2: Firma inválida o dummy values detectados

---

### 3. `sifen_build_soap12_envelope.py`
Construye SOAP 1.2 envelope **SIN alterar la firma** (raw bytes).

**Uso:**
```bash
# Básico
.venv/bin/python tools/sifen_build_soap12_envelope.py firmado.xml /tmp/soap.xml

# Con selftest (verifica que no se alteró la firma)
.venv/bin/python tools/sifen_build_soap12_envelope.py firmado.xml /tmp/soap.xml --selftest

# Usando --out
.venv/bin/python tools/sifen_build_soap12_envelope.py firmado.xml --out /tmp/soap.xml
```

**Características:**
- Inserta rDE como **bytes raw** (NO re-parsea con lxml)
- NO cambia prefijos, NO agrega xmlns:xsi
- Preserva firma digital intacta
- `--selftest`: extrae rDE del SOAP y verifica firma (exit 2 si falla)

---

### 4. `sifen_send_soap12_mtls.py`
Envía SOAP a SIFEN TEST con mTLS.

**Uso:**
```bash
# Con variables de entorno
.venv/bin/python tools/sifen_send_soap12_mtls.py /tmp/sifen_rEnviDe_soap12.xml --debug

# Con certificado explícito
.venv/bin/python tools/sifen_send_soap12_mtls.py /tmp/soap.xml \
  --cert-path /path/to/cert.p12 \
  --cert-pass "password" \
  --debug
```

**Características:**
- Envía bytes raw (NO re-parsea XML)
- `--debug`: muestra SHA256 de bytes enviados, guarda en `/tmp/last_sent_soap.xml`
- Guarda respuesta en `/tmp/sifen_rEnviDe_response.xml`
- Parsea y muestra `dCodRes` / `dMsgRes`

---

### 5. `sifen_extract_xde_from_soap.py`
Extrae rDE desde SOAP envelope (para testing).

**Uso:**
```bash
.venv/bin/python tools/sifen_extract_xde_from_soap.py /tmp/soap.xml --out /tmp/extracted.xml
```

---

### 6. `sifen_smoketest.py` ⭐
**Prueba END-TO-END completa** - ejecuta todo el flujo.

**Uso:**
```bash
.venv/bin/python tools/sifen_smoketest.py
```

**Flujo:**
1. Genera XML firmado con certificado real
2. Verifica firma criptográfica (exit 0 = OK)
3. Construye SOAP con `--selftest` (verifica que no se alteró firma)
4. Envía a SIFEN TEST con mTLS
5. Parsea respuesta y muestra `dCodRes`/`dMsgRes`

**Exit 0 si:**
- HTTP 200
- Respuesta parseable (aunque SIFEN rechace por negocio)

---

## Flujo de Prueba Manual (A/B/C/D)

Verificar que SOAP builder NO altera la firma:

```bash
# A) Verificar XML original
.venv/bin/python tools/sifen_signature_crypto_verify.py ~/Desktop/sifen_de_firmado_test.xml
# Debe dar: EXIT 0

# B) Construir SOAP
.venv/bin/python tools/sifen_build_soap12_envelope.py \
  ~/Desktop/sifen_de_firmado_test.xml \
  /tmp/sifen_rEnviDe_soap12.xml

# C) Extraer rDE desde SOAP
.venv/bin/python tools/sifen_extract_xde_from_soap.py \
  /tmp/sifen_rEnviDe_soap12.xml \
  --out /tmp/extracted_rDE.xml

# D) Verificar rDE extraído
.venv/bin/python tools/sifen_signature_crypto_verify.py /tmp/extracted_rDE.xml
# Debe dar: EXIT 0 (SIN "Digest mismatch")
```

Si D da EXIT 0 → SOAP builder NO alteró la firma ✅

---

## Troubleshooting

### Error: "Contraseña del certificado P12 incorrecta"
Verificar que `SIFEN_CERT_PASS` esté correctamente configurado:
```bash
echo $SIFEN_CERT_PASS
```

### Error: "No se encontró SIFEN_CERT_PATH"
```bash
export SIFEN_CERT_PATH="/ruta/completa/al/certificado.p12"
```

### Error: "Digest mismatch" después de construir SOAP
El SOAP builder está alterando el XML. Verificar que se esté usando la versión raw bytes:
```bash
grep "RAW BYTES" tools/sifen_build_soap12_envelope.py
```

### Respuesta SIFEN: "El documento XML no tiene firma"
Verificar que:
1. El XML tiene `ds:Signature` como hijo de `rDE`
2. La firma es real (no dummy_*)
3. El SOAP builder no alteró la firma (ejecutar flujo A/B/C/D)

---

## Archivos Generados

| Archivo | Descripción |
|---------|-------------|
| `~/Desktop/sifen_de_firmado_test.xml` | XML firmado con certificado real |
| `~/Desktop/sifen_de_prevalidador_firmado.xml` | XML sin gCamFuFD (para prevalidador) |
| `/tmp/sifen_rEnviDe_soap12.xml` | SOAP envelope con rDE firmado |
| `/tmp/sifen_rEnviDe_response.xml` | Respuesta de SIFEN |
| `/tmp/last_sent_soap.xml` | Copia exacta de lo enviado (con --debug) |

---

## Reglas de Oro

1. **NO re-parsear XML firmado** - usar bytes raw
2. **NO alterar whitespace** - preservar canonicalización
3. **NO cambiar prefijos** (ns0/ns1) - rompe firma
4. **NO agregar xmlns:xsi** - rompe firma
5. **Verificar siempre** con `sifen_signature_crypto_verify.py`

---

## Ejemplo Completo

```bash
# 1. Configurar entorno
export SIFEN_CERT_PATH="/Users/robinklaiss/.sifen/certs/MI_CERT.p12"
export SIFEN_CERT_PASS="mi_password"
export SIFEN_CSC="12345678"

# 2. Ejecutar smoketest
.venv/bin/python tools/sifen_smoketest.py

# 3. Ver respuesta SIFEN
grep -E "dCodRes|dMsgRes" /tmp/sifen_rEnviDe_response.xml
```

---

## Soporte

Si el smoketest falla, revisar cada paso individualmente:
1. `sifen_build_artifacts_real.py` - ¿genera XML firmado?
2. `sifen_signature_crypto_verify.py` - ¿firma válida?
3. `sifen_build_soap12_envelope.py --selftest` - ¿preserva firma?
4. `sifen_send_soap12_mtls.py --debug` - ¿envía correctamente?
