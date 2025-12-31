# Requisitos Técnicos SIFEN - Sistema Integrado de Facturación Electrónica Nacional

**Versión del Manual:** V150  
**Fecha de Documentación:** 2025-01-29  
**Emisor Base:** Marcio Ruben Feris Aguilera (RUC: 4554737-8)

---

## Resumen Ejecutivo

Este documento consolida todos los requisitos técnicos extraídos del Manual Técnico SIFEN V150 para la implementación del sistema de facturación electrónica. Los requisitos cubren protocolos de comunicación, seguridad, certificados digitales, firma XML, generación de QR, endpoints, límites de tamaño, códigos de error y sincronización horaria.

### Puntos Críticos

1. **Comunicación:** SOAP 1.2 Document/Literal con mTLS (TLS 1.2)
2. **Firma Digital:** XML Digital Signature Enveloped, RSA 2048, SHA-256
3. **Certificados:** X.509 v3 emitidos por PSC habilitado
4. **Sincronización NTP:** Crítica para validación de firma (CRL/LCR)
5. **QR:** Generación con hash SHA-256, CSC nunca en URL final
6. **Límites:** 1000 KB (siRecepDE, siConsRUC), 10.000 KB (siRecepLoteDE)

---

## Checklist Técnico de Implementación

### A) Comunicación / Web Services

- [x] **SOAP 1.2 Document/Literal**
  - Estilo de mensajería: Document/Literal
  - Versión SOAP: 1.2
  - Encoding: UTF-8

- [x] **TLS y Autenticación Mutua (mTLS)**
  - Protocolo: TLS 1.2 (mínimo)
  - Autenticación mutua con certificados digitales
  - Certificado cliente requerido para todas las peticiones

- [x] **Firma Digital en Peticiones**
  - Todas las peticiones deben estar firmadas digitalmente
  - Firma según especificación XML Digital Signature

### B) Certificados y Firma Digital

- [x] **Certificado Digital**
  - Estándar: X.509 v3
  - Emitido por: PSC (Prestador de Servicios de Certificación) habilitado
  - Formato soportado: PFX/P12 (PKCS#12)

- [x] **Firma XML Digital Signature**
  - Tipo: Enveloped (firma envuelve el contenido)
  - Certificado: X.509 v3
  - Algoritmo de clave: RSA 2048 bits
  - Algoritmo de hash: SHA-256
  - Validación: Integridad, autoría y cadena de confianza

- [x] **Validación de Firma (CRL/LCR)**
  - Validar cadena de confianza usando LCR (Lista de Certificados Revocados)
  - Validación en relación al momento de la firma (fecha de firma)
  - Requiere sincronización horaria correcta (ver NTP)

### C) Endpoints / Ambientes

- [x] **Selector de Ambiente**
  - TEST: Ambiente de desarrollo/pruebas
  - PROD: Ambiente de producción

- [x] **URLs WSDL por Servicio**

#### Ambiente de Producción (PROD)

| Servicio | Endpoint WSDL |
|----------|---------------|
| Recepción Síncrona (siRecepDE) | `https://sifen.set.gov.py/de/ws/sync/recibe.wsdl?wsdl` |
| Recepción Asíncrona (siRecepLoteDE) | `https://sifen.set.gov.py/de/ws/async/recibe-lote.wsdl?wsdl` |
| Eventos (siRecepEvento) | `https://sifen.set.gov.py/de/ws/eventos/evento.wsdl?wsdl` |
| Consulta Lote (siConsLoteDE) | `https://sifen.set.gov.py/de/ws/consultas/consulta-lote.wsdl?wsdl` |
| Consulta RUC (siConsRUC) | `https://sifen.set.gov.py/de/ws/consultas/consulta-ruc.wsdl?wsdl` |
| Consulta DE (siConsDE) | `https://sifen.set.gov.py/de/ws/consultas/consulta.wsdl?wsdl` |

#### Ambiente de Pruebas (TEST)

| Servicio | Endpoint WSDL |
|----------|---------------|
| Recepción Síncrona (siRecepDE) | `https://sifen-test.set.gov.py/de/ws/sync/recibe.wsdl?wsdl` |
| Recepción Asíncrona (siRecepLoteDE) | `https://sifen-test.set.gov.py/de/ws/async/recibe-lote.wsdl?wsdl` |
| Eventos (siRecepEvento) | `https://sifen-test.set.gov.py/de/ws/eventos/evento.wsdl?wsdl` |
| Consulta Lote (siConsLoteDE) | `https://sifen-test.set.gov.py/de/ws/consultas/consulta-lote.wsdl?wsdl` |
| Consulta RUC (siConsRUC) | `https://sifen-test.set.gov.py/de/ws/consultas/consulta-ruc.wsdl?wsdl` |
| Consulta DE (siConsDE) | `https://sifen-test.set.gov.py/de/ws/consultas/consulta.wsdl?wsdl` |

### D) Sincronización Horaria (NTP)

- [x] **Servidores NTP Oficiales**
  - `aravo1.set.gov.py`
  - `aravo2.set.gov.py`

- [x] **Requisito Crítico**
  - El reloj del servidor debe estar sincronizado con los servidores NTP oficiales
  - La validación de firma digital depende de la fecha/hora correcta
  - Sin sincronización correcta, las firmas pueden ser rechazadas

**Guía de Sincronización:**

```bash
# Linux (systemd)
sudo timedatectl set-ntp true
sudo systemctl restart systemd-timesyncd

# Linux (ntpdate)
sudo ntpdate -s aravo1.set.gov.py

# Windows
# Configurar en "Configuración de fecha y hora" > "Sincronizar con servidor de tiempo"
# Agregar: aravo1.set.gov.py, aravo2.set.gov.py
```

### E) Límites de Tamaño y Validaciones

#### Límites por Servicio Web

| Servicio | Límite Máximo | Código de Error si se Excede |
|----------|---------------|------------------------------|
| siRecepDE | 1000 KB | 0200 (rechazo) |
| siRecepLoteDE | 10.000 KB | 0270 (rechazo) |
| siConsRUC | 1000 KB | 0460 (rechazo) |
| siConsDE | 1000 KB | (verificar en manual) |
| siConsLoteDE | 10.000 KB | (verificar en manual) |

**Implementación Requerida:**
- Validar tamaño ANTES de enviar al servidor SIFEN
- Rechazar peticiones que excedan el límite con error descriptivo
- Incluir tamaño en logs (sin exponer contenido sensible)

#### Códigos de Error Relevantes

##### Consulta RUC (siConsRUC)

| Código | Descripción | Acción |
|--------|-------------|--------|
| 0500 | RUC inexistente | Informar al usuario |
| 0501 | Sin permiso para consultar | Verificar certificado/permisos |
| 0502 | Éxito (RUC encontrado) | Procesar datos del contribuyente |

##### Validaciones Genéricas

| Código | Descripción | Acción |
|--------|-------------|--------|
| 0183 | RUC del certificado no activo/válido | Verificar estado del certificado |
| 0200 | Mensaje excede tamaño máximo (siRecepDE) | Reducir tamaño del documento |
| 0270 | Lote excede tamaño máximo (siRecepLoteDE) | Dividir en lotes más pequeños |
| 0460 | Mensaje excede tamaño máximo (siConsRUC) | Verificar tamaño de la consulta |

**Nota:** El PDF menciona validaciones genéricas del HeaderMsg que deben implementarse según la especificación.

### F) Generación de QR (Código QR)

#### Pasos para Generar URL QR

**Paso 1: Concatenar Datos**
```
dId + dFeEmi + dRucEm + dEst + dPunExp + dNumDoc + dTipoDoc + dTipoCont + dTipoEmi + dCodGen + dDenSuc + dDVEmi
```

**Paso 2: Concatenar CSC (Solo para Hash)**
```
datos_paso_1 + CSC
```

**Paso 3: Generar Hash SHA-256**
```
hash = SHA256(datos_paso_1 + CSC)
hash_hex = hash.hexdigest().upper()
```

**Paso 4: Construir URL Final**
```
URL_BASE + datos_paso_1 + "&cHashQR=" + hash_hex
```

#### URLs de Consulta QR

| Ambiente | URL Base |
|----------|----------|
| PROD | `https://www.ekuatia.set.gov.py/consultas/qr?` |
| TEST | `https://www.ekuatia.set.gov.py/consultas-test/qr?` |

#### Reglas de Seguridad QR

1. **CSC NUNCA en URL Final**
   - El CSC se usa SOLO para generar el hash
   - El CSC NO se concatena en la URL final
   - El CSC NO debe aparecer en logs ni en ningún lugar expuesto

2. **Escape XML**
   - Al insertar la URL en el XML, reemplazar `&` por `&amp;`
   - Ejemplo: `https://...?param1=value1&cHashQR=ABC` → `https://...?param1=value1&amp;cHashQR=ABC`

3. **Sanitización de Logs**
   - Nunca loggear el CSC
   - Si es necesario loggear la URL QR, sanitizar el CSC antes

#### Ejemplo de Implementación

```python
# Paso 1: Concatenar datos
datos = f"{dId}{dFeEmi}{dRucEm}{dEst}{dPunExp}{dNumDoc}{dTipoDoc}{dTipoCont}{dTipoEmi}{dCodGen}{dDenSuc}{dDVEmi}"

# Paso 2: Concatenar CSC (solo para hash)
datos_con_csc = datos + csc

# Paso 3: Generar hash
import hashlib
hash_obj = hashlib.sha256(datos_con_csc.encode('utf-8'))
hash_hex = hash_obj.hexdigest().upper()

# Paso 4: Construir URL (SIN CSC)
url_base = "https://www.ekuatia.set.gov.py/consultas/qr?"
url_final = f"{url_base}{datos}&cHashQR={hash_hex}"

# Paso 5: Escapar para XML
url_xml = url_final.replace('&', '&amp;')
```

---

## Variables de Configuración (.env)

### Variables Requeridas

```bash
# Ambiente
SIFEN_ENV=TEST  # TEST o PROD

# Certificado Digital
SIFEN_CERT_PATH=/ruta/al/certificado.pfx
SIFEN_CERT_PASSWORD=contraseña_del_certificado

# Código Secreto del Contribuyente (CSC)
SIFEN_CSC_ID=0001  # ID del CSC (formato: 4 dígitos)
SIFEN_CSC=ABCD0000000000000000000000000000  # CSC (32 caracteres alfanuméricos)

# Datos del Emisor
SIFEN_EMISOR_RUC=4554737-8
SIFEN_EMISOR_RAZON_SOCIAL=Marcio Ruben Feris Aguilera

# Configuración de Timbrado (si aplica)
SIFEN_TIMBRADO_NUMERO=12345678
SIFEN_ESTABLECIMIENTO=001
SIFEN_PUNTO_EXPEDICION=001

# Configuración de Cliente SOAP
SIFEN_SOAP_TIMEOUT_CONNECT=15  # segundos
SIFEN_SOAP_TIMEOUT_READ=45  # segundos
SIFEN_SOAP_MAX_RETRIES=3

# NTP (opcional, para validación)
SIFEN_NTP_SERVER1=aravo1.set.gov.py
SIFEN_NTP_SERVER2=aravo2.set.gov.py
```

### Variables Opcionales

```bash
# Debug/Logging
SIFEN_DEBUG=false
SIFEN_LOG_LEVEL=INFO
SIFEN_LOG_SOAP_REQUESTS=false  # Cuidado: puede exponer datos sensibles

# Validación Local
SIFEN_VALIDATE_XSD=true
SIFEN_XSD_PATH=./schemas_sifen/
```

---

## Arquitectura de Módulos

### Estructura Propuesta

```
app/
├── sifen_client/
│   ├── __init__.py
│   ├── config.py              # Configuración y selector de ambiente
│   ├── client.py              # Cliente SOAP 1.2 con mTLS
│   ├── xml_signer.py          # Firma XML Digital Signature
│   ├── qr_generator.py        # Generación de QR
│   ├── models.py              # Modelos de datos
│   └── exceptions.py          # Excepciones personalizadas
├── tests/
│   ├── test_xml_signer.py
│   ├── test_qr_generator.py
│   └── test_size_validation.py
```

### Responsabilidades por Módulo

#### `sifen_client/config.py`
- Carga variables de entorno
- Selector de ambiente (TEST/PROD)
- URLs WSDL por servicio y ambiente
- Validación de configuración requerida

#### `sifen_client/client.py`
- Cliente SOAP 1.2 Document/Literal
- Configuración mTLS (certificado + clave)
- Timeouts y retries
- Manejo uniforme de errores/códigos SIFEN
- Validación de tamaño antes de enviar

#### `sifen_client/xml_signer.py`
- Firma XML Digital Signature Enveloped
- RSA 2048, SHA-256
- Adjuntar certificado X.509 al XML
- Validación de estructura de firma

#### `sifen_client/qr_generator.py`
- Construcción de dCarQR según pasos del PDF
- Hash SHA-256
- Escape XML (`&` → `&amp;`)
- Sanitización de logs (no exponer CSC)

---

## Referencias del Manual Técnico

Las siguientes secciones del Manual Técnico SIFEN V150 contienen información detallada:

- **Comunicación SOAP:** Sección de Web Services
- **Certificados y Firma:** Sección de Seguridad y Firma Digital
- **Endpoints:** Tabla de URLs por ambiente
- **NTP:** Sección de Requisitos de Infraestructura
- **Límites de Tamaño:** Sección de Validaciones y Límites
- **Códigos de Error:** Anexo de Códigos de Respuesta
- **QR:** Sección de Generación de Código QR

---

## Notas de Implementación

1. **Seguridad:**
   - Nunca exponer CSC, contraseñas de certificados ni claves privadas
   - Sanitizar logs antes de escribir
   - Usar variables de entorno para secretos (nunca hardcodear)

2. **Validaciones:**
   - Validar tamaño ANTES de enviar (ahorrar ancho de banda y tiempo)
   - Validar estructura XML contra XSD antes de firmar
   - Validar certificado antes de usar (fecha de expiración, estado)

3. **Manejo de Errores:**
   - Mapear códigos de error SIFEN a excepciones descriptivas
   - Incluir contexto en logs (sin datos sensibles)
   - Implementar retries solo para errores transitorios (no para 0200, 0270, etc.)

4. **Testing:**
   - Usar ambiente TEST para todas las pruebas
   - Validar con certificados de prueba
   - Probar límites de tamaño
   - Probar generación de QR con datos de prueba

---

## Próximos Pasos

1. ✅ Documento de requisitos (este archivo)
2. ⏳ Implementar módulo `xml_signer`
3. ⏳ Implementar módulo `qr_generator`
4. ⏳ Mejorar módulo `client.py` con SOAP 1.2 y mTLS
5. ⏳ Crear tests unitarios
6. ⏳ Integrar con sistema existente

---

**Última Actualización:** 2025-01-29  
**Mantenido por:** Equipo de Desarrollo

