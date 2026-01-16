# WORKFLOW TEST COMPLETO — SIFEN (tesaka-cv)

Generación de XML nuevo firmado con QR TEST usando las funciones reales del repo.

---

## 📋 Funciones utilizadas

- **`create_rde_xml_v150()`** - Genera XML base (rDE) v150
- **`sign_de_with_p12()`** - Firma con certificado P12/PFX + genera QR automáticamente

---

## 0️⃣ CONFIGURACIÓN INICIAL (variables de ambiente)

Ejecutar desde la raíz del repo `tesaka-cv/` con venv activo:

```bash
cd /Users/robinklaiss/Dev/industrias-feris-facturacion-electronica-simplificado/tesaka-cv

# Ambiente SIEMPRE test
export SIFEN_ENV=test

# Certificado P12/PFX
export SIFEN_P12_PATH="/ruta/completa/a/tu/certificado.p12"
export SIFEN_P12_PASSWORD="TU_PASSWORD_DEL_P12"

# Emisor (IMPORTANTE: incluir DV, formato: 1234567-8)
export SIFEN_EMISOR_RUC="4554737-8"

# QR CSC (los que te dio SET para TEST)
export SIFEN_ID_CSC="0001"
export SIFEN_CSC="TU_CSC_DE_TEST_32_CARACTERES"

# (Opcional) Código de seguridad del CDC
export SIFEN_CODSEG="123456789"
```

### Verificar configuración:

```bash
echo "SIFEN_ENV=$SIFEN_ENV"
echo "SIFEN_P12_PATH=$SIFEN_P12_PATH"
echo "SIFEN_EMISOR_RUC=$SIFEN_EMISOR_RUC"
echo "SIFEN_CSC=$SIFEN_CSC"
ls -la "$SIFEN_P12_PATH"  # Debe existir
```

---

## 1️⃣ GENERAR XML FIRMADO CON QR TEST

```bash
python3 tools/generate_test_xml.py
```

### Output esperado:

```
================================================================================
GENERADOR DE XML DE PRUEBA PARA SIFEN
================================================================================

📝 Configuración:
   RUC Emisor: 4554737-8
   Ambiente: TEST (SIFEN_ENV=test)
   Certificado P12: ✅
   CSC: ✅

🔨 Generando XML DE de prueba...
✅ XML base generado

🔐 Firmando XML con P12 (incluye QR automático)...
✅ XML firmado y QR generado

💾 Guardando archivo...
✅ Archivo guardado: /Users/robinklaiss/Desktop/SIFEN_TEST_20260112_044500.xml

📊 Información del archivo:
   Tamaño: 12,345 bytes
   Ruta: /Users/robinklaiss/Desktop/SIFEN_TEST_20260112_044500.xml

🔍 QR generado:
   Ambiente: TEST
   URL: https://ekuatia.set.gov.py/consultas-test/qr?nVersion=150&Id=01800455473...

================================================================================
📤 WORKFLOW TEST - PRÓXIMOS PASOS
================================================================================

1️⃣  INSPECCIONAR QR (verificar coherencia):

   python3 tools/inspect_qr.py /Users/robinklaiss/Desktop/SIFEN_TEST_20260112_044500.xml

2️⃣  PREVALIDAR XML:

   a) Abre: https://ekuatia.set.gov.py/prevalidador/validacion
   b) Resuelve captcha, abre DevTools (F12) > Network
   c) Sube cualquier XML, busca petición 'validar'
   d) Copia header 'captcha' de Request Headers
   e) Ejecuta:

   python3 tools/prevalidate_http.py \
     /Users/robinklaiss/Desktop/SIFEN_TEST_20260112_044500.xml \
     --captcha "PEGA_AQUI_EL_CAPTCHA"

   (Modo 1 se detecta automáticamente desde SIFEN_ENV=test)

================================================================================
```

---

## 2️⃣ INSPECCIONAR QR (verificar coherencia)

```bash
python3 tools/inspect_qr.py ~/Desktop/SIFEN_TEST_*.xml
```

### Output esperado:

```
=== SIFEN QR Inspector ===
Archivo: SIFEN_TEST_20260112_044500.xml
SIFEN_ENV : TEST
dVerFor   : 150
DE Id     : 01800455473780001001000000120260112
Signature : DE
dCarQR    : https://ekuatia.set.gov.py/consultas-test/qr?nVersion=150&Id=...
QR base   : https://ekuatia.set.gov.py/consultas-test/qr
QR env    : TEST
Modo      : 1 (TEST)

✅ COHERENCIA DE AMBIENTE: OK

Parámetros del QR:
  - Id: 01800455473780001001000000120260112
  - IdCSC: 0001
  - cHashQR: a1b2c3d4e5f6...
  - cItems: 2
  - dFeEmiDE: 323032362d30312d3132
  - dRucRec: 38303031323334352d30
  - dTotGralOpe: 200000
  - dTotIVA: 18182
  - nVersion: 150
```

**Si hay error de coherencia:**
```
❌ ERRORES DE COHERENCIA DE AMBIENTE:
   ❌ SIFEN_ENV=test pero QR apunta a PROD (consultas/qr). Regenerar XML con SIFEN_ENV=test.
```

---

## 3️⃣ PREVALIDAR CON CAPTCHA

### a) Obtener captcha del navegador:

1. Abre: https://ekuatia.set.gov.py/prevalidador/validacion
2. Resuelve el captcha (reCAPTCHA)
3. Abre DevTools (F12) → pestaña **Network**
4. Sube cualquier XML de prueba al prevalidador
5. Busca la petición `validar` en Network
6. Click en `validar` → pestaña **Headers** → **Request Headers**
7. Copia el valor completo de `captcha:`

**Ejemplo:**
```
captcha: eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJleHAiOjE3MDUwMzY4MDAsImlhdCI6MTcwNTAzNjUwMH0.abc123def456...
```

### b) Ejecutar prevalidación:

```bash
python3 tools/prevalidate_http.py \
  ~/Desktop/SIFEN_TEST_*.xml \
  --captcha "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJleHAiOjE3MDUwMzY4MDAsImlhdCI6MTcwNTAzNjUwMH0.abc123def456..."
```

### Output esperado (ÉXITO):

```
ℹ️  Modo no especificado, usando modo=1 según SIFEN_ENV=test

🔍 Validando coherencia de ambiente...
✅ Ambiente coherente: SIFEN_ENV=test, QR=TEST, modo=1

POST https://ekuatia.set.gov.py/validar/validar?modo=1
HTTP 200 OK
Content-Type: application/json
------------------------------------------------------------
{
  "valid": true,
  "estado": "APROBADO",
  "errores": []
}
```

### Output esperado (ERROR DE VALIDACIÓN):

```
HTTP 200 OK
{
  "valid": false,
  "errores": [
    {
      "codigo": "E001",
      "mensaje": "Campo obligatorio faltante: dRucRec"
    }
  ]
}
```

### Output esperado (ERROR DE COHERENCIA):

```
❌ ERRORES DE COHERENCIA DE AMBIENTE:
   ❌ SIFEN_ENV=test pero modo=0 (prod). Usar modo=1 para TEST.
   ❌ QR TEST detectado con modo=0 (prod). Esto causará error 2502.

💡 SOLUCIÓN:
   1. Verificar SIFEN_ENV=test
   2. Regenerar XML con: python tools/generate_test_xml.py
   3. Usar --modo 1 (coherente con TEST)
```

---

## 🔒 PROTECCIONES IMPLEMENTADAS

### 1. Guard en generación de QR (`xmlsec_signer.py`)

Si `SIFEN_ENV=test` pero detecta base PROD:
```
ValueError: ❌ SIFEN_ENV=test pero QR base es 'https://ekuatia.set.gov.py/consultas/qr' (PROD).
Debe usar: https://ekuatia.set.gov.py/consultas-test/qr
```

### 2. Validación pre-POST (`prevalidate_http.py`)

Antes de enviar al prevalidador:
- ✅ Verifica QR ambiente vs `SIFEN_ENV`
- ✅ Verifica modo vs `SIFEN_ENV`
- ✅ Detecta error 2502 antes de que ocurra

### 3. Auto-detección de modo

Si no especificas `--modo`, se detecta automáticamente:
- `SIFEN_ENV=test` → `modo=1`
- `SIFEN_ENV=prod` → `modo=0`

---

## 🚨 ERRORES COMUNES Y SOLUCIONES

### Error: "Certificado P12 no configurado"

**Solución:**
```bash
export SIFEN_P12_PATH="/ruta/completa/a/certificado.p12"
export SIFEN_P12_PASSWORD="tu_password"
ls -la "$SIFEN_P12_PATH"  # Verificar que existe
```

### Error: "CSC no configurado"

**Solución:**
```bash
export SIFEN_CSC="tu_csc_de_32_caracteres_de_test"
export SIFEN_ID_CSC="0001"
```

### Error 2502: "URL de consulta de código QR es inválida"

**Causa:** QR TEST enviado con modo=0 (PROD) o viceversa.

**Solución:**
```bash
# 1. Verificar ambiente
echo $SIFEN_ENV  # Debe ser: test

# 2. Regenerar XML
python3 tools/generate_test_xml.py

# 3. Inspeccionar
python3 tools/inspect_qr.py ~/Desktop/SIFEN_TEST_*.xml

# 4. Prevalidar (modo se detecta automáticamente)
python3 tools/prevalidate_http.py ~/Desktop/SIFEN_TEST_*.xml --captcha "..."
```

### Captcha inválido o expirado

**Síntoma:** Respuesta HTML en lugar de JSON

**Solución:**
1. El captcha expira rápido (1-2 minutos)
2. Obtener nuevo captcha del navegador
3. Copiar inmediatamente después de resolver
4. Ejecutar comando sin demora

---

## 📊 CHECKLIST DE VALIDACIÓN

Antes de prevalidar, verifica:

- [ ] `SIFEN_ENV=test` configurado
- [ ] `SIFEN_P12_PATH` apunta a certificado válido
- [ ] `SIFEN_P12_PASSWORD` configurado
- [ ] `SIFEN_EMISOR_RUC` con formato correcto (incluye DV)
- [ ] `SIFEN_CSC` configurado (32 caracteres)
- [ ] XML generado con `generate_test_xml.py`
- [ ] `inspect_qr.py` muestra "✅ COHERENCIA DE AMBIENTE: OK"
- [ ] Captcha copiado del navegador (fresco)

---

## 🎓 MIGRACIÓN A PRODUCCIÓN (futuro)

Cuando SET apruebe tu implementación:

### 1. Actualizar variables de ambiente

```bash
# Cambiar a PROD
export SIFEN_ENV=prod

# Certificado y CSC de PRODUCCIÓN
export SIFEN_P12_PATH="/ruta/a/certificado_prod.p12"
export SIFEN_P12_PASSWORD="password_prod"
export SIFEN_CSC="tu_csc_prod_32_caracteres"
```

### 2. Regenerar XMLs

```bash
python3 tools/generate_test_xml.py --env prod
```

### 3. Prevalidar en PROD

```bash
python3 tools/prevalidate_http.py \
  ~/Desktop/SIFEN_TEST_*.xml \
  --captcha "..."
  # modo=0 se detecta automáticamente desde SIFEN_ENV=prod
```

**El sistema validará automáticamente que QR PROD coincida con modo=0.**

---

## 📚 RESUMEN DE COMANDOS

```bash
# 0. Configurar
export SIFEN_ENV=test
export SIFEN_P12_PATH="/ruta/a/certificado.p12"
export SIFEN_P12_PASSWORD="password"
export SIFEN_EMISOR_RUC="4554737-8"
export SIFEN_CSC="tu_csc_32_caracteres"

# 1. Generar XML firmado
python3 tools/generate_test_xml.py

# 2. Inspeccionar QR
python3 tools/inspect_qr.py ~/Desktop/SIFEN_TEST_*.xml

# 3. Prevalidar (obtener captcha del navegador primero)
python3 tools/prevalidate_http.py \
  ~/Desktop/SIFEN_TEST_*.xml \
  --captcha "VALOR_DEL_NAVEGADOR"
```

---

## 🆘 SOPORTE

Si encuentras errores:

1. Verifica variables: `env | grep SIFEN`
2. Inspecciona XML: `python3 tools/inspect_qr.py archivo.xml`
3. Verifica certificado: `ls -la "$SIFEN_P12_PATH"`
4. Regenera XML: `python3 tools/generate_test_xml.py`

**Todos los comandos detectan automáticamente el ambiente correcto desde `SIFEN_ENV`.**
