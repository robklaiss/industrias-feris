# Workflow TEST-ONLY para SIFEN

Este documento describe el flujo completo para trabajar **exclusivamente en ambiente TEST** hasta obtener aprobación de SET para pasar a producción.

## 🎯 Objetivo

**Forzar ambiente TEST en TODO el flujo SIFEN** para evitar mezclar ambientes y prevenir el error 2502.

---

## ✅ Configuración inicial

### 1. Variables de ambiente (.env)

```bash
# OBLIGATORIO: Ambiente TEST
SIFEN_ENV=test

# Certificado y llave (TEST)
SIFEN_CERT_PATH=/ruta/a/certificado_test.pem
SIFEN_KEY_PATH=/ruta/a/llave_test.key
SIFEN_KEY_PASSWORD=tu_password

# CSC de TEST
SIFEN_CSC=tu_csc_test_32_caracteres
SIFEN_CSC_ID=0001

# RUC emisor
SIFEN_RUC=80012345
```

### 2. Verificar configuración

```bash
export SIFEN_ENV=test
echo $SIFEN_ENV  # Debe mostrar: test
```

---

## 🔄 Flujo completo TEST

### Paso 1: Generar XML de prueba

```bash
python tools/generate_test_xml.py
```

**Qué hace:**
- ✅ Fuerza `SIFEN_ENV=test` si no está configurado
- ✅ Genera XML con QR TEST: `https://ekuatia.set.gov.py/consultas-test/qr`
- ✅ Firma el XML con tu certificado
- ✅ Guarda en Desktop: `SIFEN_TEST_YYYYMMDD_HHMMSS.xml`
- ✅ Muestra comando para prevalidar

**Output esperado:**
```
📝 Configuración:
   RUC Emisor: 80012345
   Ambiente: TEST (SIFEN_ENV=test)
   Certificado: ✅
   CSC: ✅

✅ Archivo guardado: /Users/tu_usuario/Desktop/SIFEN_TEST_20260112_040000.xml

🔍 QR generado:
   Ambiente: TEST
   URL: https://ekuatia.set.gov.py/consultas-test/qr?...
```

---

### Paso 2: Inspeccionar QR (opcional)

```bash
python tools/inspect_qr.py ~/Desktop/SIFEN_TEST_*.xml
```

**Qué hace:**
- ✅ Extrae dCarQR del XML
- ✅ Detecta ambiente del QR (TEST/PROD)
- ✅ Valida coherencia con `SIFEN_ENV`
- ✅ Detecta automáticamente modo=1 desde `SIFEN_ENV=test`

**Output esperado:**
```
=== SIFEN QR Inspector ===
Archivo: SIFEN_TEST_20260112_040000.xml
SIFEN_ENV : TEST
QR env    : TEST
Modo      : 1 (TEST)

✅ COHERENCIA DE AMBIENTE: OK
```

**Si hay error:**
```
❌ ERRORES DE COHERENCIA DE AMBIENTE:
   ❌ SIFEN_ENV=test pero QR apunta a PROD (consultas/qr). Regenerar XML con SIFEN_ENV=test.
```

---

### Paso 3: Obtener captcha del navegador

1. Abre: https://ekuatia.set.gov.py/prevalidador/validacion
2. Resuelve el captcha
3. Abre DevTools (F12) → Network
4. Sube cualquier XML de prueba
5. Busca la petición `validar`
6. En Request Headers, copia el valor de `captcha`

**Ejemplo:**
```
captcha: eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...
```

---

### Paso 4: Prevalidar XML

```bash
python tools/prevalidate_http.py \
  ~/Desktop/SIFEN_TEST_*.xml \
  --captcha "PEGA_AQUI_EL_CAPTCHA"
```

**Qué hace:**
- ✅ Auto-detecta `modo=1` desde `SIFEN_ENV=test`
- ✅ Valida coherencia QR vs modo antes del POST
- ✅ Envía POST a: `https://ekuatia.set.gov.py/validar/validar?modo=1`
- ✅ Parsea respuesta JSON del prevalidador

**Output esperado (éxito):**
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

**Output esperado (error de validación):**
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

**Output esperado (error de coherencia):**
```
❌ ERRORES DE COHERENCIA DE AMBIENTE:
   ❌ SIFEN_ENV=test pero modo=0 (prod). Usar modo=1 para TEST.

💡 SOLUCIÓN:
   1. Verificar SIFEN_ENV=test
   2. Regenerar XML con: python tools/generate_test_xml.py
   3. Usar --modo 1 (coherente con TEST)
```

---

## 🔒 Protecciones implementadas

### 1. Guard en generación de QR (`xmlsec_signer.py`)

Si intentas generar QR con base URL incorrecta:

```python
# Si SIFEN_ENV=test pero detecta base PROD
ValueError: ❌ SIFEN_ENV=test pero QR base es 'https://ekuatia.set.gov.py/consultas/qr' (PROD). 
Debe usar: https://ekuatia.set.gov.py/consultas-test/qr
```

### 2. Validación en prevalidador (`prevalidate_http.py`)

Antes de enviar POST, valida:
- ✅ QR ambiente coincide con `SIFEN_ENV`
- ✅ Modo coincide con `SIFEN_ENV`
- ✅ QR ambiente coincide con modo

### 3. Helper `assert_test_env()`

Función reutilizable para validar coherencia:

```python
from app.sifen_client.env_validator import assert_test_env

validation = assert_test_env(xml_content, modo=1)
if not validation["valid"]:
    for error in validation["errors"]:
        print(error)
```

---

## 🚫 Errores comunes y soluciones

### Error 2502: "URL de consulta de código QR es inválida"

**Causa:** QR TEST enviado con modo=0 (PROD) o viceversa.

**Solución:**
```bash
# 1. Verificar ambiente
echo $SIFEN_ENV  # Debe ser: test

# 2. Regenerar XML
python tools/generate_test_xml.py

# 3. Prevalidar sin especificar modo (auto-detecta)
python tools/prevalidate_http.py ~/Desktop/SIFEN_TEST_*.xml --captcha "..."
```

### Captcha inválido o expirado

**Síntoma:** Respuesta HTML en lugar de JSON

**Solución:**
1. Obtener nuevo captcha del navegador (expira rápido)
2. Copiar inmediatamente después de resolver el captcha
3. Ejecutar el comando sin demora

### Certificado no encontrado

**Síntoma:** `❌ ERROR: Certificado no encontrado`

**Solución:**
```bash
# Verificar rutas en .env
cat .env | grep SIFEN_CERT
cat .env | grep SIFEN_KEY

# Verificar que archivos existan
ls -la /ruta/a/certificado_test.pem
ls -la /ruta/a/llave_test.key
```

---

## 📋 Checklist de validación TEST

Antes de enviar a prevalidación, verifica:

- [ ] `SIFEN_ENV=test` configurado
- [ ] XML generado con `generate_test_xml.py`
- [ ] QR contiene `consultas-test/qr` (no `consultas/qr`)
- [ ] `inspect_qr.py` muestra "✅ COHERENCIA DE AMBIENTE: OK"
- [ ] Captcha copiado del navegador (fresco)
- [ ] Comando usa modo=1 o auto-detecta desde `SIFEN_ENV`

---

## 🎓 Migración a PRODUCCIÓN (futuro)

Cuando SET apruebe tu implementación:

### 1. Actualizar variables de ambiente

```bash
# Cambiar a PROD
SIFEN_ENV=prod

# Certificado y CSC de PRODUCCIÓN
SIFEN_CERT_PATH=/ruta/a/certificado_prod.pem
SIFEN_KEY_PATH=/ruta/a/llave_prod.key
SIFEN_CSC=tu_csc_prod_32_caracteres
```

### 2. Regenerar XMLs

```bash
python tools/generate_test_xml.py --env prod
```

### 3. Prevalidar en PROD

```bash
python tools/prevalidate_http.py \
  ~/Desktop/SIFEN_TEST_*.xml \
  --captcha "..."
  # modo=0 se detecta automáticamente desde SIFEN_ENV=prod
```

**El sistema validará automáticamente que QR PROD coincida con modo=0.**

---

## 📚 Archivos modificados

### Nuevos archivos:
- `app/sifen_client/env_validator.py` - Helper de validación de ambiente
- `tools/generate_test_xml.py` - Generador de XML de prueba
- `tools/prevalidate_http.py` - Cliente HTTP para prevalidador
- `WORKFLOW_TEST_ONLY.md` - Esta documentación

### Archivos modificados:
- `app/sifen_client/xmlsec_signer.py` - Guard de QR base URL
- `app/sifen_client/validator.py` - Auto-detección de modo
- `tools/inspect_qr.py` - Validación de coherencia

---

## 🆘 Soporte

Si encuentras errores de coherencia de ambiente:

1. Verifica `SIFEN_ENV`: `echo $SIFEN_ENV`
2. Inspecciona el XML: `python tools/inspect_qr.py archivo.xml`
3. Regenera el XML: `python tools/generate_test_xml.py`
4. Valida coherencia antes de enviar

**Todos los comandos ahora detectan automáticamente el ambiente correcto desde `SIFEN_ENV`.**
