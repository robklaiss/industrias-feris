# ESTADO ACTUAL — Integración SIFEN (Paraguay)

**Fecha de Auditoría:** 2025-01-29  
**Repositorio:** industrias-feris-facturacion-electronica-simplificado  
**Alcance:** Módulos Python (tesaka-cv), librería Java (rshk-jsifenlib), smoke test (sifen-smoketest)

---

## 1) Resumen Ejecutivo

### Qué está hecho hoy (alto nivel)

- ✅ **Módulo cliente SIFEN (`tesaka-cv/app/sifen_client/`)**: Estructura completa con 15 archivos Python
- ✅ **Configuración por ambiente**: Selector TEST/PROD implementado en `config.py`
- ✅ **Validación XML**: Validador contra XSD con soporte para múltiples versiones (v141, v150)
- ✅ **Generación XML**: Generadores para DE crudo y siRecepDE wrapper (`xml_generator.py`, `xml_generator_v150.py`)
- ✅ **Prevalidador SIFEN**: Integración funcional con servicio público (aplicación web Angular)
- ✅ **Endpoints FastAPI**: Rutas `/dev/sifen-smoke-test`, `/dev/sifen-prevalidate`, `/dev/sifen-prevalidate-angular`
- ✅ **Esquemas XSD**: 94 archivos XSD descargados en `schemas_sifen/` y `xsd/`
- ✅ **Firma Digital**: Módulo `xml_signer.py` implementado (XMLDSig Enveloped, RSA 2048, SHA-256)
- ✅ **Generación QR**: Módulo `qr_generator.py` implementado con hash SHA-256 y escape XML
- ✅ **Cliente SOAP**: Estructura base en `soap_client.py` (requiere WSDL real para completar)
- ✅ **Validación de tamaños**: Límites implementados (1000 KB / 10.000 KB) en `soap_client.py`
- ✅ **Tests unitarios**: 3 archivos de test (`test_xml_signer.py`, `test_qr_generator.py`, `test_size_validation.py`)
- ✅ **Librería Java**: `rshk-jsifenlib` clonada (160 archivos Java, versión 0.2.4)
- ✅ **Smoke test Java**: Módulo Maven `sifen-smoketest` con consulta RUC funcional
- ✅ **Documentación**: 8 archivos MD en `tesaka-cv/docs/` + `docs/SIFEN_REQUISITOS.md`

### Qué NO está hecho hoy (alto nivel)

- ❌ **Cliente SOAP funcional**: Estructura existe pero métodos lanzan `NotImplementedError` (requiere WSDL real)
- ❌ **Envío real a SIFEN**: Solo smoke test y prevalidación, no envío de documentos reales
- ❌ **Persistencia de respuestas SIFEN**: No hay tablas en BD para guardar respuestas/estados
- ❌ **Manejo de eventos**: No implementado (anulaciones, cancelaciones, etc.)
- ❌ **Consulta de documentos**: Método existe pero no funcional (requiere WSDL)
- ❌ **Lotes asíncronos**: No implementado (siRecepLoteDE)
- ❌ **Sincronización NTP**: NO ENCONTRADO (scripts, config, docs)
- ❌ **Validación CRL/LCR**: Mencionado en requisitos pero no implementado en código
- ❌ **Integración end-to-end**: Flujo completo desde factura interna → XML → firma → envío → respuesta

---

## 2) Arquitectura Actual del Sistema

### Diagrama Textual

```
┌─────────────────────────────────────────────────────────────┐
│                    FastAPI Application                       │
│  (tesaka-cv/app/main.py, routes_*.py)                       │
└──────────────────────┬──────────────────────────────────────┘
                       │
                       ▼
┌─────────────────────────────────────────────────────────────┐
│              SIFEN Client Module                            │
│  (tesaka-cv/app/sifen_client/)                              │
│                                                             │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐     │
│  │  config.py   │  │  client.py   │  │ validator.py │     │
│  │ (TEST/PROD)  │  │  (httpx)     │  │  (XSD)       │     │
│  └──────────────┘  └──────────────┘  └──────────────┘     │
│                                                             │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐     │
│  │xml_generator │  │ xml_signer   │  │qr_generator  │     │
│  │  _v150.py    │  │  (signxml)   │  │  (SHA-256)   │     │
│  └──────────────┘  └──────────────┘  └──────────────┘     │
│                                                             │
│  ┌──────────────┐  ┌──────────────┐                       │
│  │soap_client.py│  │xml_utils.py  │                       │
│  │ (zeep - WIP) │  │  (clean)     │                       │
│  └──────────────┘  └──────────────┘                       │
└──────────────────────┬──────────────────────────────────────┘
                       │
                       ▼
┌─────────────────────────────────────────────────────────────┐
│              External Services                               │
│                                                             │
│  • Prevalidador SIFEN (Angular web app)                     │
│    https://ekuatia.set.gov.py/prevalidador/validacion       │
│                                                             │
│  • Servicios SIFEN (SOAP - NO CONECTADO)                    │
│    TEST: https://sifen-test.set.gov.py/...                 │
│    PROD: https://sifen.set.gov.py/...                       │
└─────────────────────────────────────────────────────────────┘
```

### Flujo: Emisión → Firma → Envío → Respuesta → Persistencia

**Flujo Actual (Parcial):**

1. **Emisión**: Generación XML DE desde datos internos
   - Archivos: `tools/build_de.py`, `app/sifen_client/xml_generator_v150.py`
   - Output: XML DE crudo (elemento `<DE>`)

2. **Wrapper**: Generación siRecepDE
   - Archivo: `tools/build_sirecepde.py`
   - Output: XML siRecepDE (elemento `<rEnviDe>` con `<xDE>`)

3. **Firma**: Firma digital XML (IMPLEMENTADO pero no integrado en flujo)
   - Archivo: `app/sifen_client/xml_signer.py`
   - Método: `sign()` - XMLDSig Enveloped, RSA 2048, SHA-256

4. **Validación**: Validación local contra XSD
   - Archivo: `app/sifen_client/validator.py`
   - Métodos: `validate_xml_structure()`, `validate_against_xsd()`

5. **Prevalidación**: Prevalidador SIFEN (web app Angular)
   - Archivo: `app/sifen_client/validator.py` → `prevalidate_with_service()`
   - URL: `https://ekuatia.set.gov.py/prevalidador/validacion`
   - Nota: Es aplicación web, no API REST directa

6. **Envío**: NO IMPLEMENTADO (solo estructura)
   - Archivo: `app/sifen_client/soap_client.py`
   - Estado: Métodos `recepcion_de()`, `consulta_ruc()` lanzan `NotImplementedError`

7. **Respuesta**: NO PERSISTIDO
   - No hay tablas en BD para guardar respuestas SIFEN
   - Solo logs en consola/archivos

### Tecnologías Detectadas

- **Lenguaje**: Python 3.x (FastAPI), Java 8 (rshk-jsifenlib)
- **Framework Web**: FastAPI (`app/main.py`)
- **Templates**: Jinja2 (`app/templates/`)
- **Base de Datos**: SQLite (`tesaka.db`)
- **HTTP Client**: httpx (`app/sifen_client/client.py`)
- **SOAP Client**: zeep (importado pero no usado, `soap_client.py`)
- **XML Processing**: lxml, xml.etree.ElementTree
- **Firma Digital**: signxml, cryptography
- **Validación XSD**: lxml.etree.XMLSchema
- **Build Tools**: Maven (sifen-smoketest), Gradle (rshk-jsifenlib)

---

## 3) Configuración y Secretos (sin valores)

### Archivos de Config

- **`tesaka-cv/app/sifen_client/config.py`**: Clase `SifenConfig` con URLs, ambientes, certificados
- **`rshk-jsifenlib/config/sifen.properties.example`**: Template de propiedades Java
- **`sifen-smoketest/.env.example`**: Template de variables de entorno
- **NO ENCONTRADO**: Archivo `.env` real (está en `.gitignore`)

### Variables de Entorno Detectadas

**Python (tesaka-cv):**
- `SIFEN_ENV` (test/prod)
- `SIFEN_TEST_BASE_URL`
- `SIFEN_PROD_BASE_URL`
- `SIFEN_USE_MTLS` (default: "true")
- `SIFEN_CERT_PATH`
- `SIFEN_CERT_PASSWORD`
- `SIFEN_CA_BUNDLE_PATH`
- `SIFEN_API_KEY` (si no es mTLS)
- `SIFEN_USER` (si no es mTLS)
- `SIFEN_PASSWORD` (si no es mTLS)
- `SIFEN_REQUEST_TIMEOUT`
- `SIFEN_TEST_RUC`
- `SIFEN_TEST_TIMBRADO`
- `SIFEN_TEST_CSC`
- `SIFEN_TEST_RAZON_SOCIAL`
- `SIFEN_SOAP_TIMEOUT_CONNECT`
- `SIFEN_SOAP_TIMEOUT_READ`
- `SIFEN_SOAP_MAX_RETRIES`
- `SIFEN_CSC` (para QR)
- `SIFEN_CSC_ID` (para QR)

**Java (sifen-smoketest):**
- `SIFEN_ENV` (DEV/PROD)
- `PFX_PATH`
- `PFX_PASSWORD`
- `CSC_ID`
- `CSC`
- `RUC_QUERY`

### Dónde se Espera Cargar Certificado

- **Python**: Variable `SIFEN_CERT_PATH` → archivo PFX/P12
- **Java**: Variable `PFX_PATH` → archivo PFX
- **Código**: `app/sifen_client/config.py` línea 71-83, `app/sifen_client/xml_signer.py` línea 30-35
- **Validación**: Se verifica existencia del archivo en `config.py` línea 82-83

### Logging y Sanitización

- **Logging**: Módulo `logging` estándar de Python
- **Sanitización QR**: Método `sanitize_for_logging()` en `qr_generator.py` línea 85-95
- **CSC**: Nunca se loggea (verificado en `qr_generator.py`)
- **Contraseñas**: NO se loggean (solo paths de archivos)
- **NO ENCONTRADO**: Configuración específica de niveles de log para SIFEN

---

## 4) Certificados y Firma Digital

### Estado: IMPLEMENTADO (módulo completo)

### Estándar Usado

- **XML Digital Signature**: Enveloped (firma envuelve el contenido)
- **Certificado**: X.509 v3
- **Algoritmo de clave**: RSA 2048 bits (validado en código)
- **Algoritmo de hash**: SHA-256
- **Librería**: `signxml` (Python), `cryptography`

### Archivos Responsables

- **`app/sifen_client/xml_signer.py`**: Módulo principal (230 líneas)
  - Clase: `XmlSigner`
  - Métodos: `sign()`, `verify()`, `get_certificate_info()`, `_validate_certificate()`
  - Validaciones: Fecha de expiración, algoritmo RSA, tamaño de clave (>= 2048)

### Validación de Firma

- **Método**: `verify()` en `xml_signer.py` línea 95-108
- **Librería**: `XMLVerifier` de `signxml`
- **Validación**: Estructura de firma, certificado X.509

### Manejo de CRL/LCR

- **Estado**: NO ENCONTRADO
- **Mencionado en**: `docs/SIFEN_REQUISITOS.md` (requisito documentado)
- **Código**: No hay implementación de validación de cadena de confianza ni CRL/LCR

---

## 5) Comunicación con SIFEN

### 5.1 Cliente de Red / Protocolo

#### SOAP vs REST

- **Configurado**: SOAP 1.2 Document/Literal
- **Archivo**: `app/sifen_client/config.py` línea 46: `SERVICE_TYPE = "SOAP"`
- **Implementación**: `app/sifen_client/soap_client.py` (estructura, no funcional)
- **Librería**: `zeep` (importado pero métodos lanzan `NotImplementedError`)

#### WSDLs / Endpoints Configurados

**Archivo**: `app/sifen_client/config.py` líneas 32-43

**TEST:**
- `recibe`: `https://sifen-test.set.gov.py/de/ws/sync/recibe.wsdl`
- `recibe_lote`: `https://sifen-test.set.gov.py/de/ws/async/recibe-lote.wsdl`
- `evento`: `https://sifen-test.set.gov.py/de/ws/eventos/evento.wsdl`
- `consulta_lote`: `https://sifen-test.set.gov.py/de/ws/consultas/consulta-lote.wsdl`
- `consulta_ruc`: `https://sifen-test.set.gov.py/de/ws/consultas/consulta-ruc.wsdl`
- `consulta`: `https://sifen-test.set.gov.py/de/ws/consultas/consulta.wsdl`

**PROD:**
- Mismos paths pero con `sifen.set.gov.py` (sin `-test`)

#### Soporte TEST/PROD

- **Selector**: Variable `SIFEN_ENV` (test/prod)
- **Código**: `app/sifen_client/config.py` clase `SifenConfig.__init__()` línea 52-62
- **Método**: `get_soap_service_url(service_key)` línea 107-120

#### TLS/mTLS

- **Estado**: PARCIAL (configuración existe, no probado)
- **Código**: `app/sifen_client/config.py` línea 67: `use_mtls = os.getenv("SIFEN_USE_MTLS", "true")`
- **Implementación**: `app/sifen_client/client.py` líneas 48-55 (httpx), `soap_client.py` líneas 50-85 (zeep/requests)
- **Certificado**: Se carga desde `SIFEN_CERT_PATH` (PFX/P12)
- **TLS Versión**: NO ESPECIFICADO en código (httpx/requests usan default del sistema)

#### Timeouts, Retries, Backoff

- **Timeouts**: 
  - `SIFEN_REQUEST_TIMEOUT` (default: 30s) - `config.py` línea 91
  - `SIFEN_SOAP_TIMEOUT_CONNECT` (default: 15s) - `soap_client.py` línea 42
  - `SIFEN_SOAP_TIMEOUT_READ` (default: 45s) - `soap_client.py` línea 43
- **Retries**: 
  - `SIFEN_SOAP_MAX_RETRIES` (default: 3) - `soap_client.py` línea 44
  - **NO ENCONTRADO**: Implementación de retries (solo variable configurada)
- **Backoff**: NO ENCONTRADO

### 5.2 Operaciones/Servicios Ya Integrados

#### siRecepDE (sync) — Estado y Archivos

- **Estado**: PARCIAL (estructura, no funcional)
- **Archivo**: `app/sifen_client/soap_client.py` método `recepcion_de()` línea 149-177
- **Problema**: Lanza `NotImplementedError` (requiere WSDL real)
- **Validación de tamaño**: Implementada (1000 KB) - línea 152

#### siRecepLoteDE (lote/async) — Estado y Archivos

- **Estado**: NO IMPLEMENTADO
- **Archivo**: NO ENCONTRADO (solo mencionado en `config.py` como endpoint)

#### Eventos — Estado y Archivos

- **Estado**: NO IMPLEMENTADO
- **Archivo**: NO ENCONTRADO (solo mencionado en `config.py` como endpoint)

#### Consultas (consulta, consulta-lote, consulta-ruc) — Estado y Archivos

- **consulta_ruc**: PARCIAL
  - Archivo: `app/sifen_client/soap_client.py` método `consulta_ruc()` línea 112-147
  - Estado: Lanza `NotImplementedError` (requiere WSDL real)
  - Validación de tamaño: Implementada (1000 KB)
- **consulta**: NO IMPLEMENTADO (solo endpoint en config)
- **consulta-lote**: NO IMPLEMENTADO (solo endpoint en config)
- **Smoke test Java**: `sifen-smoketest/src/main/java/.../Smoketest.java` - Consulta RUC funcional usando librería Java

---

## 6) Validaciones, Límites y Manejo de Errores

### Validaciones de Tamaño de Payload

- **Estado**: IMPLEMENTADO
- **Archivo**: `app/sifen_client/soap_client.py` líneas 8-15 (constantes), método `_validate_size()` líneas 87-105
- **Límites**:
  - `siRecepDE`: 1000 KB (código error 0200)
  - `siRecepLoteDE`: 10.000 KB (código error 0270)
  - `siConsRUC`: 1000 KB (código error 0460)
  - `siConsDE`: 1000 KB (asumido)
  - `siConsLoteDE`: 10.000 KB (asumido)

### Manejo de Códigos de Error

- **Archivo**: `app/sifen_client/soap_client.py` líneas 17-30 (diccionario `ERROR_CODES`)
- **Códigos definidos**:
  - `0200`: Mensaje excede tamaño máximo (siRecepDE)
  - `0270`: Lote excede tamaño máximo (siRecepLoteDE)
  - `0460`: Mensaje excede tamaño máximo (siConsRUC)
  - `0500`: RUC inexistente
  - `0501`: Sin permiso para consultar
  - `0502`: Éxito (RUC encontrado)
  - `0183`: RUC del certificado no activo/válido
- **Método de parseo**: `_parse_error_code()` líneas 107-125 (extrae código de SOAP Fault)

### Estrategia de Reintentos y Errores Transitorios

- **Variable configurada**: `SIFEN_SOAP_MAX_RETRIES` (default: 3)
- **Implementación**: NO ENCONTRADO (solo variable, no lógica de retry)

### Persistencia de Respuestas / Trazabilidad

- **Logs**: NO ENCONTRADO configuración específica de logging para SIFEN
- **Base de Datos**: NO ENCONTRADO tablas para guardar respuestas SIFEN
- **Archivos**: Se guardan XML generados en `artifacts/` (timestamp en nombre)
- **Trazabilidad**: Solo archivos XML, no respuestas de SIFEN

---

## 7) Generación de QR (dCarQR)

### Estado: IMPLEMENTADO

### Algoritmo

**Archivo**: `app/sifen_client/qr_generator.py`

**Pasos implementados** (líneas 47-95):
1. **Paso 1**: Concatenar datos del documento (dId + dFeEmi + dRucEm + ...)
2. **Paso 2**: Concatenar CSC (solo para hash) - línea 62
3. **Paso 3**: Generar hash SHA-256 en hexadecimal mayúsculas - líneas 65-66
4. **Paso 4**: Construir URL final SIN CSC - línea 69
5. **Paso 5**: Escape XML (`&` → `&amp;`) - línea 72

**URLs base** (líneas 19-22):
- TEST: `https://www.ekuatia.set.gov.py/consultas-test/qr?`
- PROD: `https://www.ekuatia.set.gov.py/consultas/qr?`

### Protección del CSC

- **Código**: `qr_generator.py` líneas 62, 69, 85-95
- **Verificación**: CSC nunca en URL final (solo usado para hash)
- **Sanitización**: Método `sanitize_for_logging()` línea 85-95
- **Tests**: `tests/test_qr_generator.py` test `test_qr_generator_sanitize_for_logging()` verifica que CSC no esté en URL

### Escape XML

- **Implementado**: `escape_xml()` método estático línea 78-84
- **Uso**: Se aplica automáticamente en `generate()` línea 72
- **Tests**: `tests/test_qr_generator.py` test `test_qr_generator_escape_xml()` verifica `&amp;`

---

## 8) Sincronización Horaria / NTP

### Estado: NO ENCONTRADO

### Evidencia en Repo

- **Scripts**: NO ENCONTRADO
- **Docs**: Mencionado en `docs/SIFEN_REQUISITOS.md` (requisito documentado)
- **Docker**: NO ENCONTRADO
- **Systemd**: NO ENCONTRADO
- **Código**: NO ENCONTRADO validación de fecha/hora del sistema
- **Servidores NTP**: Documentados en `docs/SIFEN_REQUISITOS.md` (aravo1.set.gov.py, aravo2.set.gov.py) pero no hay código que los use

---

## 9) Datos del Emisor y Mapeo de Campos

### Dónde se Configuran

- **Variables de entorno**:
  - `SIFEN_TEST_RUC` / `SIFEN_EMISOR_RUC`
  - `SIFEN_TEST_RAZON_SOCIAL` / `SIFEN_EMISOR_RAZON_SOCIAL`
  - `SIFEN_TEST_TIMBRADO` / `SIFEN_TIMBRADO_NUMERO`
  - `SIFEN_ESTABLECIMIENTO`
  - `SIFEN_PUNTO_EXPEDICION`
- **Código**: `app/sifen_client/config.py` líneas 94-98 (solo para TEST)
- **Hardcodeado en generadores**: `app/sifen_client/xml_generator_v150.py` líneas 162-163 (razón social "Contribuyente de Prueba S.A.")

### Validaciones de Formato

- **RUC**: Validación de longitud (8 dígitos) en `xml_generator_v150.py` línea 122
- **DV RUC**: Cálculo simplificado en `xml_generator_v150.py` líneas 124-133
- **Timbrado**: Validación de longitud mínima en `xml_generator_v150.py` línea 24
- **NO ENCONTRADO**: Validación de formato RUC-DV completo (ej: "4554737-8")

### Archivos y Estructuras

- **JSON**: `tesaka-cv/examples/de_input.json` (ejemplo de datos)
- **Base de Datos**: Tabla `system_config` en `db.py` línea 233-238 (solo números base, no datos emisor)
- **NO ENCONTRADO**: Tabla específica para datos del emisor

---

## 10) Persistencia / Base de Datos

### Motor

- **SQLite**: `tesaka.db` (ruta: `tesaka-cv/tesaka.db`)
- **Código**: `app/db.py`

### Tablas/Modelos Relevantes

**Tablas existentes** (de `app/db.py`):
- `invoices` (línea 25-33): Facturas internas (NO relacionadas con SIFEN)
- `clients` (línea 36-46): Clientes
- `products` (línea 49-60): Productos
- `contracts` (línea 63-76): Contratos
- `purchase_orders` (línea 92-105): Órdenes de compra
- `delivery_notes` (línea 123-144): Notas de entrega
- `remissions` (línea 163-184): Remisiones
- `sales_invoices` (línea 201-215): Facturas de venta
- `system_config` (línea 233-238): Configuración del sistema
- `submissions` (línea 248-261): Registro de envíos a Tesaka (NO SIFEN)

### Qué se Guarda de Cada DE / Lote / Respuesta / Evento

- **DE generados**: Se guardan como archivos XML en `artifacts/` (no en BD)
- **Respuestas SIFEN**: NO SE GUARDAN (no hay tabla)
- **Lotes**: NO SE GUARDAN (no hay tabla)
- **Eventos**: NO SE GUARDAN (no hay tabla)
- **Estados de documentos**: NO SE GUARDAN (no hay tabla)

---

## 11) Tests y QA

### Tests Existentes

**Python** (`tesaka-cv/tests/`):
- `test_xml_signer.py`: 8 tests (firma, verificación, validación certificado)
- `test_qr_generator.py`: 10 tests (generación, hash, escape, sanitización)
- `test_size_validation.py`: 8 tests (límites, validación de tamaño)

**Java** (`rshk-jsifenlib/src/test/`):
- `ConsultaRUCTest.java`: Test de consulta RUC (marcado con `@Ignore`)
- `DETest.java`: Test de generación DE
- `SignatureTests.java`: Tests de firma
- `SOAPTests.java`: Tests SOAP

**Smoke test** (`sifen-smoketest/`):
- `Smoketest.java`: Main ejecutable para consulta RUC

### Cobertura Aproximada

- **Firma XML**: ✅ Cubierto (8 tests)
- **Generación QR**: ✅ Cubierto (10 tests)
- **Validación de tamaños**: ✅ Cubierto (8 tests)
- **Envío a SIFEN**: ❌ NO cubierto (métodos no implementados)
- **Consulta RUC**: ⚠️ Parcial (solo smoke test Java, no tests unitarios Python)
- **Validación XSD**: ⚠️ Parcial (tests manuales, no automatizados)

### Casos Cubiertos

- ✅ Firma de XML con certificado PFX
- ✅ Verificación de firma
- ✅ Detección de XML modificado
- ✅ Generación de QR con hash SHA-256
- ✅ Escape XML para URLs QR
- ✅ Sanitización de logs (CSC no expuesto)
- ✅ Validación de límites de tamaño
- ✅ Diferentes ambientes (TEST vs PROD) para QR

---

## 12) Lista de "NO ENCONTRADO" (crítico)

1. **Sincronización NTP**: Scripts, configuración, validación de fecha/hora
2. **Validación CRL/LCR**: Código para validar cadena de confianza de certificados
3. **Cliente SOAP funcional**: Implementación completa con WSDL real (solo estructura existe)
4. **Persistencia de respuestas SIFEN**: Tablas en BD para guardar respuestas, estados, eventos
5. **Manejo de eventos**: Anulaciones, cancelaciones, etc.
6. **Lotes asíncronos**: Implementación de siRecepLoteDE
7. **Consulta de documentos**: Implementación funcional (solo estructura)
8. **Integración end-to-end**: Flujo completo desde factura → XML → firma → envío → respuesta
9. **Configuración de logging SIFEN**: Niveles específicos, sanitización automática
10. **Retries implementados**: Lógica de reintentos con backoff (solo variable configurada)
11. **Validación de formato RUC-DV**: Verificación completa de formato "12345678-9"
12. **Tabla de datos del emisor**: Persistencia de RUC, razón social, timbrado, etc.
13. **Manejo de errores transitorios**: Distinción entre errores permanentes y transitorios
14. **Trazabilidad completa**: Logs estructurados de todas las operaciones SIFEN

---

## 13) Próximos Pasos Sugeridos (máximo 8)

1. **Completar cliente SOAP funcional**
   - Archivo objetivo: `tesaka-cv/app/sifen_client/soap_client.py`
   - Acción: Obtener WSDL real y completar métodos `consulta_ruc()`, `recepcion_de()`
   - Dependencia: Acceso a WSDL oficial de SIFEN

2. **Implementar persistencia de respuestas SIFEN**
   - Archivo objetivo: `tesaka-cv/app/db.py`
   - Acción: Crear tablas `sifen_documents`, `sifen_responses`, `sifen_events`
   - Campos: CDC, estado, fecha, respuesta XML, códigos de error

3. **Integrar firma digital en flujo de generación**
   - Archivo objetivo: `tesaka-cv/tools/build_de.py` o `app/sifen_client/xml_generator_v150.py`
   - Acción: Llamar a `XmlSigner.sign()` después de generar XML
   - Dependencia: Certificado PFX configurado

4. **Implementar sincronización NTP**
   - Archivo objetivo: Nuevo script `tesaka-cv/scripts/sync_ntp.sh` o módulo Python
   - Acción: Validar fecha/hora del sistema contra aravo1.set.gov.py, aravo2.set.gov.py
   - Integración: Validar antes de firmar/enviar

5. **Completar validación CRL/LCR**
   - Archivo objetivo: `tesaka-cv/app/sifen_client/xml_signer.py`
   - Acción: Agregar validación de cadena de confianza usando LCR
   - Dependencia: Acceso a CRL/LCR del PSC

6. **Implementar manejo de eventos**
   - Archivo objetivo: Nuevo módulo `tesaka-cv/app/sifen_client/eventos.py`
   - Acción: Implementar anulaciones, cancelaciones según XSD de eventos
   - Dependencia: XSD de eventos (ya existe en `schemas_sifen/`)

7. **Agregar tests de integración end-to-end**
   - Archivo objetivo: `tesaka-cv/tests/test_sifen_integration.py`
   - Acción: Test completo: generar → firmar → validar → (prevalidar) → [enviar cuando esté funcional]
   - Dependencia: Certificado de prueba, datos de prueba

8. **Implementar retries con backoff**
   - Archivo objetivo: `tesaka-cv/app/sifen_client/soap_client.py`
   - Acción: Lógica de reintentos para errores transitorios (timeout, 5xx)
   - Backoff: Exponencial con jitter

---

**Fin del Documento**

