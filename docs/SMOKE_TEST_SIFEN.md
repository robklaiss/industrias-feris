# Smoke Test SIFEN - consultaRUC

Este documento describe cómo ejecutar smoke tests contra SIFEN TEST para la operación `consultaRUC` de forma repetible y segura.

## 🎯 Objetivo

Validar que la integración con SIFEN TEST funciona correctamente sin guardar secretos en el repositorio. Los tests son ejecutables localmente y usan certificados P12 exportados a PEM temporales.

## 📋 Prerrequisitos

1. **Certificado P12**: Debe estar disponible en:
   - `$HOME/.sifen/certs/F1T_65478.p12` (default)
   - O definir `SIFEN_P12_PATH` con la ruta completa

2. **Herramientas requeridas**:
   - `openssl` (para exportar P12 a PEM)
   - `curl` (para hacer requests SOAP con mTLS)
   - `bash` (para ejecutar los scripts)

3. **Conocimiento del password del P12**: Se solicitará de forma interactiva (no se guarda en disco ni en history).

## 🚀 Pasos Rápidos

### 1. Exportar certificado P12 a PEM

El primer paso es exportar el certificado P12 a archivos PEM temporales que usarán los scripts:

```bash
# Si el P12 está en la ubicación default:
bash scripts/sifen_export_p12_to_pem.sh

# O especificar ruta manualmente:
export SIFEN_P12_PATH=/ruta/al/certificado.p12
bash scripts/sifen_export_p12_to_pem.sh
```

Este script:
- ✅ Pide el password del P12 de forma interactiva (no queda en history)
- ✅ Exporta certificado a `/tmp/sifen_cert.pem`
- ✅ Exporta clave privada a `/tmp/sifen_key.pem`
- ✅ Establece permisos 600 (solo propietario puede leer/escribir)
- ✅ Valida que los archivos tienen el formato PEM correcto

**Nota de seguridad**: Los archivos PEM son temporales y están en `/tmp`. NO deben compartirse ni commitearse.

### 2. Ejecutar Smoke Test consultaRUC

Una vez que los archivos PEM están disponibles, ejecutar el smoke test:

```bash
export SIFEN_RUC_CONS="80012345"  # RUC a consultar (formato según XSD tRuc)
bash scripts/sifen_smoke_consulta_ruc.sh
```

**Formato de RUC (`SIFEN_RUC_CONS`)**:

El script normaliza automáticamente el RUC según la especificación SIFEN consultaRUC:
- **Longitud**: 7-8 dígitos totales (incluyendo el dígito verificador)
- **Solo dígitos**: El RUC paraguayo NUNCA tiene letras
- **Sin guión**: El guión es solo para visualización, se elimina automáticamente

**Ejemplos válidos**:
```bash
# Formato preferido (sin guión, 7-8 dígitos)
export SIFEN_RUC_CONS="45547378"    # 8 dígitos ✅
export SIFEN_RUC_CONS="4554737"     # 7 dígitos ✅

# Formato con guión (se normaliza automáticamente)
export SIFEN_RUC_CONS="4554737-8"   # → normaliza a "45547378" (7 base + 1 DV = 8 total) ✅
export SIFEN_RUC_CONS="455473-7"    # → normaliza a "4554737" (6 base + 1 DV = 7 total) ✅
```

**Nota importante**: 
- Si el input viene con guión, el RUC base debe tener 6 o 7 dígitos, y el DV debe ser 1 dígito
- El resultado final siempre tiene 7 u 8 dígitos (sin guión, solo números)
- Si el input viene sin guión, debe tener exactamente 7 u 8 dígitos

**Parámetros opcionales**:
```bash
export SIFEN_DID="1"                # ID del documento (default: 1)
export SIFEN_ENV="test"             # Ambiente: test o prod (default: test)
export SIFEN_SMOKE_ALLOW_0160="1"   # Permite 0160 (XML Mal Formado) para modo conectividad (default: 0)
```

**Qué hace el script**:
1. Verifica que los archivos PEM existen (si no, llama automáticamente al script de export)
2. Construye el SOAP request con el formato correcto:
   ```xml
   <soap12:Envelope>
     <soap12:Body>
       <ns0:rEnviConsRUC>
         <ns0:dId>1</ns0:dId>
         <ns0:dRUCCons>80012345-7</ns0:dRUCCons>
       </ns0:rEnviConsRUC>
     </soap12:Body>
   </soap12:Envelope>
   ```
3. Hace POST con curl + mTLS al endpoint:
   - TEST: `https://sifen-test.set.gov.py/de/ws/consultas/consulta-ruc.wsdl`
   - PROD: `https://sifen.set.gov.py/de/ws/consultas/consulta-ruc.wsdl`
4. Guarda la respuesta en:
   - `/tmp/sifen_ruc_req.xml` (request enviado)
   - `/tmp/sifen_ruc_resp.xml` (response recibido)
   - `/tmp/sifen_ruc_resp.hdr` (headers HTTP)

**Criterios de éxito**:
- ✅ Respuesta contiene XML válido con `dCodRes` y/o `dMsgRes` (indica que llegó al servicio SIFEN)
- ✅ HTTP code puede ser 200, 400, 500 (SOAP faults vienen con HTTP 400 pero tienen XML útil)
- ✅ Si `dCodRes=0160` (XML Mal Formado): el script falla con **EXIT 3** (modo estricto) a menos que `SIFEN_SMOKE_ALLOW_0160=1`

**Modo estricto (default)**:
- Si el request no cumple el XSD y SIFEN responde `0160`, el script termina con **EXIT 3**
- Esto ayuda a detectar problemas de formato antes de desplegar

**Modo conectividad** (con `SIFEN_SMOKE_ALLOW_0160=1`):
- Permite `0160` para verificar solo conectividad mTLS/endpoint
- Útil para debugging cuando se sabe que el formato puede no ser perfecto

**Ejemplo de output exitoso**:
```
🧪 Smoke test consultaRUC contra SIFEN TEST
📋 Normalizando RUC según XSD tRuc...
   Input SIFEN_RUC_CONS: 80012345-7
   Normalizado dRUCCons: 80012345
   ⚠️  Se ignoró el DV porque tRuc maxLength=8; usando solo RUC sin guión

📝 Construyendo SOAP request...
   ✅ Request XML creado y validado: /tmp/sifen_ruc_req.xml

🌐 Enviando request a: https://sifen-test.set.gov.py/de/ws/consultas/consulta-ruc.wsdl
✅ Respuesta recibida

📊 RESUMEN
HTTP Code: 200
Tamaño respuesta: 1234 bytes

dCodRes: 0502
dMsgRes: RUC consultado exitosamente

✅ Smoke test completado exitosamente
```

**Ejemplo con error 0160 (modo estricto)**:
```
📋 Normalizando RUC según XSD tRuc...
   Input SIFEN_RUC_CONS: 80012345-7
   Normalizado dRUCCons: 80012345

📊 RESUMEN
HTTP Code: 400
dCodRes: 0160
dMsgRes: XML Mal Formado

❌ Error: dCodRes=0160 (XML Mal Formado)
   Esto indica que el request XML no cumple el XSD de SIFEN

   Para verificar solo conectividad (ignorar 0160):
   export SIFEN_SMOKE_ALLOW_0160=1
   bash scripts/sifen_smoke_consulta_ruc.sh
```

### 3. Actualizar Snapshot WSDL (opcional)

Para habilitar los contract tests offline, es necesario descargar el snapshot WSDL:

```bash
bash scripts/update_wsdl_snapshot_consulta_ruc_test.sh
```

Este script:
- ✅ Usa los archivos PEM temporales (si no existen, llama al export script)
- ✅ Descarga el WSDL desde: `https://sifen-test.set.gov.py/de/ws/consultas/consulta-ruc.wsdl?wsdl`
- ✅ Guarda el snapshot en: `tesaka-cv/wsdl_snapshots/consulta-ruc_test.wsdl`
- ✅ Valida que el WSDL contiene `wsdl:definitions` y es válido

**Nota**: El snapshot WSDL SÍ se puede commitear (no contiene secretos).

### 4. Ejecutar Contract Tests

Una vez que el snapshot WSDL existe, ejecutar los contract tests:

```bash
bash scripts/check_sifen_contracts.sh
```

Este script ejecuta todos los tests de contrato, incluyendo:
- ✅ Test de estructura WSDL (si el snapshot existe)
- ✅ Test de endpoint SOAP address
- ✅ Test de operación `rEnviConsRUC`
- ✅ Tests de mTLS, PKCS12, XML signer, etc.

**Si el snapshot NO existe**: El contract test WSDL se omite con un warning, pero el script termina con `EXIT_CODE=0` si los demás tests pasan.

## 🔍 Troubleshooting

### Error: "Certificado P12 no encontrado"
**Causa**: El archivo P12 no está en la ubicación esperada.

**Solución**:
```bash
export SIFEN_P12_PATH=/ruta/completa/al/certificado.p12
bash scripts/sifen_export_p12_to_pem.sh
```

### Error: "MAC verified OK" pero falla la extracción
**Causa**: El password es correcto pero hay un problema con el formato del P12.

**Solución**: Verificar el P12 manualmente:
```bash
openssl pkcs12 -info -in certificado.p12
```

### Error: "No se pudo establecer conexión mTLS"
**Causa**: Problema con los certificados PEM o con la conexión a SIFEN.

**Solución**:
1. Verificar que los PEM tienen contenido:
   ```bash
   head /tmp/sifen_cert.pem
   head /tmp/sifen_key.pem
   ```
2. Verificar que tienen permisos 600:
   ```bash
   ls -l /tmp/sifen_*.pem
   ```
3. Probar conexión manual:
   ```bash
   curl --cert /tmp/sifen_cert.pem --key /tmp/sifen_key.pem \
     https://sifen-test.set.gov.py/de/ws/consultas/consulta-ruc.wsdl?wsdl
   ```

### Error: HTTP 000 o timeout
**Causa**: Problema de red o firewall bloqueando conexión a SIFEN.

**Solución**: Verificar conectividad:
```bash
curl -I https://sifen-test.set.gov.py
```

### Error: "La respuesta no parece ser XML válido"
**Causa**: SIFEN devolvió un error HTTP pero no en formato XML.

**Solución**: Revisar el contenido de `/tmp/sifen_ruc_resp.xml` para ver el error real.

## 🔒 Seguridad

### ⚠️ IMPORTANTE: No commitear secretos

- ❌ NO commitear archivos `.p12`, `.pfx`, `.pem`, `.key`
- ❌ NO commitear `/tmp/sifen_*.pem`
- ✅ SÍ se puede commitear el snapshot WSDL (no contiene secretos)
- ✅ SÍ se puede commitear scripts y tests

### Archivos ignorados (`.gitignore`)

Los siguientes archivos están en `.gitignore`:
- `*.p12`, `*.pfx`, `*.pem`, `*.key`
- `**/tmp/sifen_*.pem`
- `tesaka-cv/tmp/sifen_*.pem`

### Uso de archivos PEM temporales

Los archivos PEM en `/tmp` son temporales y:
- ✅ Se generan con permisos 600 (solo propietario puede leer/escribir)
- ✅ Contienen la clave privada SIN passphrase (solo para smoke local)
- ✅ NO deben compartirse ni subirse a ningún repositorio
- ✅ Se pueden eliminar después de usar: `rm /tmp/sifen_*.pem`

## 📚 Referencias

- **Endpoint SIFEN TEST**: `https://sifen-test.set.gov.py/de/ws/consultas/consulta-ruc.wsdl`
- **Endpoint SIFEN PROD**: `https://sifen.set.gov.py/de/ws/consultas/consulta-ruc.wsdl`
- **Operación**: `rEnviConsRUC`
- **Formato RUC**: `########-#` (ej: `80012345-7`)

## ✅ Acceptance Criteria

Para verificar que todo funciona correctamente:

```bash
# A) Smoke test (con normalización)
export SIFEN_RUC_CONS="80012345-7"  # Se normaliza a "80012345" (DV ignorado)
bash scripts/sifen_smoke_consulta_ruc.sh
# ✅ Debe terminar con exit 0 mostrando dCodRes/dMsgRes (si no es 0160)

# A.1) Smoke test (formato directo)
export SIFEN_RUC_CONS="80012345"  # Sin guión, cumple XSD directamente
bash scripts/sifen_smoke_consulta_ruc.sh
# ✅ Debe terminar con exit 0 mostrando dCodRes/dMsgRes

# A.2) Modo conectividad (permite 0160)
export SIFEN_RUC_CONS="80012345"
export SIFEN_SMOKE_ALLOW_0160=1
bash scripts/sifen_smoke_consulta_ruc.sh
# ✅ Si dCodRes=0160, debe terminar con exit 0 (modo conectividad)

# B) Snapshot WSDL
bash scripts/update_wsdl_snapshot_consulta_ruc_test.sh
# ✅ Debe crear/actualizar tesaka-cv/wsdl_snapshots/consulta-ruc_test.wsdl

# C) Contract tests
bash scripts/check_sifen_contracts.sh ; echo "EXIT_CODE=$?"
# ✅ Debe terminar con EXIT_CODE=0
```
