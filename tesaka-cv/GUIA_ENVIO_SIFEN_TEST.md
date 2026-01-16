# Guía de Envío a SIFEN TEST

## 📋 Resumen

Esta guía explica cómo enviar documentos electrónicos (DE) a SIFEN en ambiente TEST.

---

## 🔑 Credenciales SIFEN TEST

**Solicitud de habilitación:** 364010034907  
**Timbrado:** Tu RUC (generado automáticamente)

**CSC Genéricos para TEST:**
- **IDCSC: 1** → `ABCD0000000000000000000000000000`
- **IDCSC: 2** → `EFGH0000000000000000000000000000`

---

## 📁 Archivos Generados

### 1. XML Sin Firma (para prevalidador)
```
/Users/robinklaiss/Desktop/sifen_de_test_sin_firma.xml
```
- ✅ Sin firma
- ✅ CDC de 44 dígitos
- ✅ dCodSeg: 000000001 (genérico TEST)
- 📍 **Uso:** https://ekuatia.set.gov.py/prevalidador/validacion

### 2. XML Firmado (para envío real)
```
/Users/robinklaiss/Desktop/sifen_de_firmado_test.xml
```
- ✅ Firma completa con cadena de certificados
- ✅ 2 certificados (Usuario + CA Intermedia)
- ✅ Algoritmos NT16 (rsa-sha256, sha256)
- ✅ CDC de 44 dígitos
- 📍 **Uso:** Envío a SIFEN TEST mediante API

---

## 🚀 Flujo de Envío

### Opción 1: Usando el Script de Envío

```bash
# Enviar DE firmado a SIFEN TEST
.venv/bin/python tools/enviar_de_sifen_test.py ~/Desktop/sifen_de_firmado_test.xml
```

El script:
1. Lee el XML firmado
2. Extrae el CDC
3. Codifica el XML en base64
4. Envía a SIFEN TEST con CSC genérico
5. Muestra la respuesta de SIFEN

### Opción 2: Envío Manual mediante API

**Endpoint SIFEN TEST:**
```
POST https://sifen-test.set.gov.py/de/ws/sync/recibe.json
```

**Headers:**
```json
{
  "Content-Type": "application/json",
  "Accept": "application/json"
}
```

**Payload:**
```json
{
  "dId": "<CDC_44_DIGITOS>",
  "xDE": "<XML_EN_BASE64>",
  "dCSC": "ABCD0000000000000000000000000000"
}
```

**Ejemplo con curl:**
```bash
# Codificar XML en base64
XML_BASE64=$(base64 -i ~/Desktop/sifen_de_firmado_test.xml)

# Extraer CDC del XML
CDC="0104554737800100120822011202601121000000019"

# Enviar a SIFEN
curl -X POST https://sifen-test.set.gov.py/de/ws/sync/recibe.json \
  -H "Content-Type: application/json" \
  -H "Accept: application/json" \
  -d "{
    \"dId\": \"$CDC\",
    \"xDE\": \"$XML_BASE64\",
    \"dCSC\": \"ABCD0000000000000000000000000000\"
  }"
```

---

## ✅ Respuestas Esperadas de SIFEN

### Respuesta Exitosa (Aprobado)
```json
{
  "dCodRes": "0300",
  "dMsgRes": "Aprobado",
  "gResProcLote": {
    "dProtConsLote": "<PROTOCOLO>",
    "dFecProc": "2026-01-12T08:22:01",
    "dCodRes": "0300",
    "dMsgRes": "Aprobado"
  }
}
```

### Respuesta con Error
```json
{
  "dCodRes": "0400",
  "dMsgRes": "Error en validación",
  "gResProcLote": {
    "dProtConsLote": "<PROTOCOLO>",
    "dFecProc": "2026-01-12T08:22:01",
    "dCodRes": "0400",
    "dMsgRes": "Descripción del error"
  }
}
```

**Códigos de respuesta comunes:**
- `0300` - Aprobado
- `0400` - Error de validación
- `0401` - Error de firma
- `0402` - Error de certificado
- `0500` - Error interno de SIFEN

---

## 🔍 Verificación del Envío

### 1. Consultar Estado del DE

**Endpoint:**
```
GET https://sifen-test.set.gov.py/de/ws/consultas/consulta-ruc.json?ruc=<RUC>&cdc=<CDC>
```

**Ejemplo:**
```bash
curl "https://sifen-test.set.gov.py/de/ws/consultas/consulta-ruc.json?ruc=4554737&cdc=0104554737800100120822011202601121000000019"
```

### 2. Validador de Consulta

**URL:** https://ekuatia.set.gov.py/consultas-test/

Ingresa el CDC para consultar el estado del documento.

---

## 📝 Notas Importantes

### Sobre el CDC
- **Longitud:** Exactamente 44 dígitos
- **Formato:** Numérico (0-9)
- **Composición:**
  - Tipo DE (2)
  - RUC (8)
  - DV RUC (1)
  - Establecimiento (3)
  - Punto Expedición (3)
  - Número Documento (7)
  - Tipo Contribuyente (1)
  - Fecha (8)
  - Tipo Emisión (1)
  - Código Seguridad (9)
  - DV CDC (1)

### Sobre el CSC
- **CSC genéricos** son para TEST únicamente
- **NO van en el XML**, se usan en el payload de envío
- **dCodSeg** (9 dígitos) es diferente del CSC completo
- Para TEST: usar `ABCD0000000000000000000000000000` (IDCSC: 1)

### Sobre la Firma
- **Cadena completa:** Usuario + CA Intermedia
- **Algoritmos NT16:** rsa-sha256, sha256
- **Transform:** Solo enveloped-signature
- **Certificado de CA:** Debe estar en `~/.sifen/certs/ca-documenta.crt`

---

## 🐛 Troubleshooting

### Error: "Certificado inválido"
- ✅ **Solución:** Verificar que el XML incluya 2 certificados (Usuario + CA)
- Comando: Ver sección "Verificación del XML Firmado"

### Error: "Firma difiere del estándar"
- ✅ **Solución:** Verificar algoritmos NT16
- SignatureMethod debe ser `rsa-sha256`
- DigestMethod debe ser `sha256`

### Error: "CDC inválido"
- ✅ **Solución:** Verificar longitud y DV del CDC
- Debe tener exactamente 44 dígitos
- El último dígito es el DV (módulo 11)

### Error: "CSC inválido"
- ✅ **Solución:** Usar CSC genérico de SIFEN TEST
- `ABCD0000000000000000000000000000` (IDCSC: 1)
- `EFGH0000000000000000000000000000` (IDCSC: 2)

---

## 🔧 Comandos Útiles

### Generar XML sin firma
```bash
.venv/bin/python -c "
from app.sifen_client.xml_generator_v150 import create_rde_xml_v150
xml = create_rde_xml_v150(
    ruc='4554737',
    dv_ruc='8',
    timbrado='12345678',
    establecimiento='001',
    punto_expedicion='001',
    numero_documento='0001002',
    tipo_documento='1'
)
with open('de_sin_firma.xml', 'w') as f:
    f.write(xml)
print('✅ XML sin firma generado')
"
```

### Generar XML firmado
```bash
export SIFEN_CERT_PATH="/Users/robinklaiss/.sifen/certs/F1T_65478.p12"
export SIFEN_CERT_PASS="bH1%T7EP"

.venv/bin/python tools/generate_signed_de_to_desktop.py
```

### Verificar XML firmado
```bash
.venv/bin/python -c "
from lxml import etree
import base64
from cryptography import x509
from cryptography.hazmat.backends import default_backend

with open('sifen_de_firmado_test.xml', 'rb') as f:
    root = etree.fromstring(f.read())

ns = {'ds': 'http://www.w3.org/2000/09/xmldsig#'}
certs = root.xpath('//ds:X509Certificate', namespaces=ns)

print(f'Certificados: {len(certs)}')
for i, cert_elem in enumerate(certs, 1):
    cert_der = base64.b64decode(cert_elem.text)
    cert_obj = x509.load_der_x509_certificate(cert_der, default_backend())
    subj = cert_obj.subject.rfc4514_string()
    if 'FERIS' in subj:
        print(f'{i}. Usuario')
    elif 'CA-DOCUMENTA' in subj:
        print(f'{i}. CA Intermedia')
"
```

---

## 📚 Referencias

- **Documentación SIFEN:** https://www.dnit.gov.py/
- **Manual Técnico v150:** NT16 (MT v150)
- **Prevalidador TEST:** https://ekuatia.set.gov.py/prevalidador/validacion
- **Consultas TEST:** https://ekuatia.set.gov.py/consultas-test/

---

## ✅ Checklist de Envío

Antes de enviar a SIFEN TEST, verificar:

- [ ] XML tiene CDC de 44 dígitos
- [ ] XML está firmado con certificado válido
- [ ] XML incluye 2 certificados (Usuario + CA)
- [ ] Algoritmos son NT16 (rsa-sha256, sha256)
- [ ] dCodSeg es numérico de 9 dígitos
- [ ] CSC genérico TEST está disponible
- [ ] Certificado de CA está en `~/.sifen/certs/ca-documenta.crt`

---

**Última actualización:** 2026-01-12
