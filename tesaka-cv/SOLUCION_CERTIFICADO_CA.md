# Solución: Certificado Inválido - Falta Cadena de CA

## Problema Diagnosticado

SIFEN rechaza el XML con el error:
```
Validacion Firma
Certificado inválido.
```

**Causa raíz:** El XML solo incluye el certificado del usuario, pero SIFEN requiere la **cadena completa de certificados** (usuario + CA intermedia).

## Estado Actual

✅ **Implementado:**
- Detección automática de URL de CA desde extensión AIA del certificado
- Descarga automática del certificado de CA (cuando el servidor responde)
- Inclusión automática de la cadena completa en el XML firmado

❌ **Problema:**
- El servidor de DOCUMENTA S.A. (`www.digito.com.py`) no responde
- URL del certificado: `https://www.digito.com.py/uploads/certificado-documenta-sa-1535117771.crt`
- Error: Connection timeout

## Soluciones

### Opción 1: Obtener Certificado de CA Manualmente (RECOMENDADO)

1. **Contactar a DOCUMENTA S.A.** para obtener el certificado de la CA:
   - Email: info@documenta.com.py
   - Web: https://www.documenta.com.py/
   - Solicitar: "Certificado de CA-DOCUMENTA S.A. (RUC 80050172-1)"

2. **Guardar el certificado:**
   ```bash
   # Guardar como PEM o DER en:
   ~/.sifen/certs/ca-documenta.crt
   ```

3. **Modificar el código para usar el certificado local:**
   Editar `app/sifen_client/xmldsig_signer.py` línea ~507:
   ```python
   # Intentar descargar certificado de CA desde AIA
   ca_cert = _download_ca_cert_from_aia(cert)
   
   # Si falla, intentar cargar desde archivo local
   if not ca_cert:
       ca_cert_path = Path.home() / ".sifen" / "certs" / "ca-documenta.crt"
       if ca_cert_path.exists():
           with open(ca_cert_path, 'rb') as f:
               ca_cert_data = f.read()
               try:
                   ca_cert = x509.load_der_x509_certificate(ca_cert_data, default_backend())
               except:
                   ca_cert = x509.load_pem_x509_certificate(ca_cert_data, default_backend())
   ```

### Opción 2: Extraer CA del P12 Original

Si el P12 original incluía la cadena completa:

```bash
# Extraer todos los certificados del P12
openssl pkcs12 -in certificado.p12 -nokeys -out chain.pem

# Separar certificados individuales
# El primer certificado es el usuario, los siguientes son las CAs
```

### Opción 3: Usar Certificado de Prueba de SIFEN

SIFEN proporciona certificados de prueba que incluyen la cadena completa:
- Descargar desde: https://ekuatia.set.gov.py/
- Sección: "Certificados de Prueba"

## Verificación

Una vez obtenido el certificado de CA:

```bash
# Regenerar XML con cadena completa
export SIFEN_CERT_PATH="/ruta/certificado.p12"
export SIFEN_CERT_PASS="password"

.venv/bin/python tools/generate_signed_de_to_desktop.py

# Verificar que el XML incluye 2 certificados
.venv/bin/python -c "
from lxml import etree
with open('/Users/robinklaiss/Desktop/sifen_with_ca_chain.xml', 'rb') as f:
    root = etree.fromstring(f.read())
ns = {'ds': 'http://www.w3.org/2000/09/xmldsig#'}
certs = root.xpath('//ds:X509Certificate', namespaces=ns)
print(f'Certificados en XML: {len(certs)}')
print('✅ OK' if len(certs) >= 2 else '❌ Falta CA')
"
```

## Información del Certificado Actual

```
Subject: C=PY,O=CERTIFICADO CUALIFICADO TRIBUTARIO,OU=F1,2.5.4.4=FERIS AGUILERA,2.5.4.42=MARCIO RUBEN,2.5.4.5=CI4554737,CN=MARCIO RUBEN FERIS AGUILERA
Issuer: C=PY,O=DOCUMENTA S.A.,2.5.4.5=RUC80050172-1,CN=CA-DOCUMENTA S.A.
Válido: 2025-12-29 hasta 2026-12-29
```

**Certificado de CA requerido:**
- Issuer: CA-DOCUMENTA S.A.
- RUC: 80050172-1
- URL (no disponible): https://www.digito.com.py/uploads/certificado-documenta-sa-1535117771.crt

## Próximos Pasos

1. ✅ Contactar a DOCUMENTA S.A. para obtener el certificado de CA
2. ⏳ Guardar el certificado en `~/.sifen/certs/ca-documenta.crt`
3. ⏳ Modificar código para cargar CA desde archivo local
4. ⏳ Regenerar XML y verificar que incluye 2 certificados
5. ⏳ Subir a SIFEN TEST y verificar que pasa validación

## Contacto

**DOCUMENTA S.A.**
- Web: https://www.documenta.com.py/
- Email: info@documenta.com.py
- Teléfono: Consultar en sitio web
- Solicitud: "Certificado de CA-DOCUMENTA S.A. para cadena de certificados SIFEN"
