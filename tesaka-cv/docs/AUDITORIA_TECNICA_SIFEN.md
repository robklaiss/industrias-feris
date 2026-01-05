# Auditoría Técnica SIFEN - Checklist de Integración

**Fecha**: 2025-01-XX  
**Auditor**: Sistema Automatizado  
**Objetivo**: Verificar qué puntos del checklist SIFEN están cubiertos (offline) y qué queda pendiente por habilitación/credenciales/conexión real.

---

## PASO 1 — INVENTARIO RÁPIDO DEL REPO

### Estructura Relevante
```
tesaka-cv/
├── app/
│   ├── sifen_client/          # Cliente SOAP + firma XML
│   │   ├── config.py          # Configuración test/prod
│   │   ├── soap_client.py     # Cliente SOAP 1.2 (3860 líneas)
│   │   ├── xmlsec_signer.py   # Firma XMLDSig
│   │   ├── pkcs12_utils.py    # Conversión P12→PEM para mTLS
│   │   ├── xsd_validator.py   # Validación XSD local
│   │   └── exceptions.py       # Excepciones personalizadas
│   └── requirements.txt       # Dependencias (lxml, xmlsec, zeep, requests, cryptography)
├── web/
│   ├── main.py                # Endpoint FastAPI /de/{id}/send
│   ├── db.py                  # SQLite (de_documents, sifen_lotes)
│   └── lotes_db.py            # Gestión de lotes
├── tools/
│   ├── send_sirecepde.py      # CLI para envío (5291 líneas)
│   ├── consulta_lote_de.py    # CLI para consulta lote
│   └── regen_cdc_from_rde.py  # Regeneración de CDC
├── tests/
│   ├── test_xml_signer.py     # Tests de firma XML
│   ├── test_pkcs12_utils.py   # Tests de conversión P12
│   └── test_soap_client_mtls.py # Tests de mTLS
└── docs/
    ├── ANALISIS_DCODRES_0301.md
    ├── MECANISMOS_REINTENTO.md
    └── FLUJO_SIRECEPLOTEDE.md
```

### Stack Tecnológico
- **Lenguaje**: Python 3.11/3.12
- **Librerías SOAP**: `zeep` (SOAP 1.2)
- **Firma XML**: `xmlsec` + `lxml`
- **mTLS**: `requests` + `cryptography` (P12→PEM)
- **Framework Web**: FastAPI
- **Base de Datos**: SQLite

---

## PASO 2 — VERIFICACIÓN OFFLINE (CHECKLIST)

| ITEM | STATUS | EVIDENCIA | NOTAS / ACCIÓN RECOMENDADA |
|------|--------|-----------|----------------------------|
| **A) CONFIGURACIÓN Y SEPARACIÓN DE AMBIENTES** |
| A1) Existe configuración explícita para TEST vs PROD (URLs/flags) | ✅ **OK** | `app/sifen_client/config.py` líneas 84-121<br/>`SifenConfig.BASE_URLS` dict con "test" y "prod"<br/>`SifenConfig.SOAP_SERVICES` dict con URLs por ambiente | URLs parametrizadas, defaults seguros |
| A2) Endpoints SIFEN parametrizados (no hardcodeados) y con defaults seguros | ✅ **OK** | `app/sifen_client/config.py` líneas 92-121<br/>`BASE_URLS` y `SOAP_SERVICES` usan `os.getenv()` con defaults | Permite override por env vars |
| A3) Validación de formato de env vars (por ejemplo: SIFEN_ENV=test\|prod) | ✅ **OK** | `app/sifen_client/config.py` líneas 130-138<br/>`if env not in [self.ENV_TEST, self.ENV_PROD]: raise ValueError(...)` | Valida que env sea "test" o "prod" |
| **B) SOAP 1.2 (SIN CONECTAR)** |
| B1) El cliente SOAP usa SOAP 1.2 (Content-Type / binding / librería) | ✅ **OK** | `app/sifen_client/soap_client.py` línea 2: "Cliente SOAP 1.2 Document/Literal"<br/>Línea 1970: `Content-Type: application/soap+xml; charset=utf-8; action="siRecepLoteDE"`<br/>Línea 3112: `SOAP_12_NS = "http://www.w3.org/2003/05/soap-envelope"` | SOAP 1.2 confirmado en múltiples lugares |
| B2) WSDLs o rutas de servicios están soportadas (estructura de llamadas y stubs) | ✅ **OK** | `app/sifen_client/config.py` líneas 104-121: `SOAP_SERVICES` dict con WSDL URLs<br/>`app/sifen_client/soap_client.py` líneas 173-244: `_extract_soap_address_from_wsdl()` | Extrae endpoint desde WSDL usando mTLS |
| B3) Timeouts configurados y manejo de errores (reintentos controlados/no infinitos) | ✅ **OK** | `app/sifen_client/config.py` línea 179: `self.request_timeout = int(os.getenv("SIFEN_REQUEST_TIMEOUT", "30"))`<br/>`app/sifen_client/soap_client.py` líneas 107-108: `connect_timeout=15`, `read_timeout=45`<br/>Líneas 2751-2848: Reintentos solo para `ConnectionResetError` (máx 2) | Timeouts configurables, reintentos limitados |
| **C) TLS 1.2 + mTLS (SIN CONECTAR)** |
| C1) Soporte de TLS 1.2 forzado o verificado en la configuración | ⚠️ **PARTIAL** | `app/sifen_client/soap_client.py` línea 144: Comentario "TLS 1.2 con autenticación mutua"<br/>**FALTA**: No hay verificación explícita de versión TLS mínima en `requests.Session()` | **ACCIÓN**: Agregar `session.mount("https://", HTTPAdapter())` con `ssl_version=ssl.PROTOCOL_TLSv1_2` o verificar en runtime |
| C2) Configuración de mutual TLS: client cert + private key cargables desde PFX/P12 | ✅ **OK** | `app/sifen_client/pkcs12_utils.py`: `p12_to_temp_pem_files()` convierte P12→PEM<br/>`app/sifen_client/soap_client.py` líneas 249-341: `_create_transport()` carga P12 y configura `session.cert = (cert_pem_path, key_pem_path)` | Soporta P12 y PEM directo |
| C3) Validación/parseo del PFX/P12 (sin exponer contraseña) | ✅ **OK** | `app/sifen_client/pkcs12_utils.py` líneas 59-314: `_p12_to_pem_openssl_fallback()` con fallback a OpenSSL legacy<br/>Líneas 223-252: Tests verifican que password no aparece en logs | Valida P12, fallback a OpenSSL, no loguea passwords |
| C4) Almacenamiento seguro: nada hardcodeado; uso de .env / secret manager; ejemplo .env.example | ⚠️ **PARTIAL** | `app/sifen_client/config.py` líneas 9-14: Carga `.env` con `dotenv` (opcional)<br/>Líneas 31-43: `get_cert_path_and_password()` lee desde env vars<br/>`.gitignore` líneas 77-80: Excluye `*.p12`, `*.pfx`, `*certificates*`<br/>**FALTA**: No existe `.env.example` en el repo | **ACCIÓN**: Crear `tesaka-cv/.env.example` con variables requeridas (sin valores reales) |
| **D) FIRMA DIGITAL XML (SIN CONECTAR)** |
| D1) Implementación de XML Digital Signature "enveloped" | ✅ **OK** | `app/sifen_client/xmlsec_signer.py` línea 496: `transform1.set("Algorithm", "http://www.w3.org/2000/09/xmldsig#enveloped-signature")`<br/>Línea 285: `sign_de_with_p12()` firma el DE completo | Enveloped signature implementado |
| D2) Algoritmos razonables (RSA 2048 / SHA-256 o superior si el código lo define) | ✅ **OK** | `app/sifen_client/xmlsec_signer.py` línea 487: `SignatureMethod Algorithm="http://www.w3.org/2001/04/xmldsig-more#rsa-sha256"`<br/>Línea 504: `DigestMethod Algorithm="http://www.w3.org/2001/04/xmlenc#sha256"` | RSA-SHA256 y SHA-256 confirmados |
| D3) Pruebas unitarias con XML de ejemplo: genera firma determinística verificable | ✅ **OK** | `tests/test_xml_signer.py` líneas 140-156: `test_xml_signer_sign()` genera firma y verifica estructura<br/>Líneas 158-167: `test_xml_signer_verify()` verifica firma | Tests unitarios con XML de ejemplo |
| D4) Verificador local (opcional): valida que la firma se verifica con el cert público | ✅ **OK** | `tests/test_xml_signer.py` líneas 158-167: `test_xml_signer_verify()` verifica firma<br/>Líneas 170-182: `test_xml_signer_verify_tampered()` detecta modificaciones | Verificación local implementada |
| **E) GENERACIÓN/VALIDACIÓN ESTRUCTURAL DEL DE (SIN CONECTAR)** |
| E1) Validación XSD o validación estructural equivalente (schemas local) | ✅ **OK** | `app/sifen_client/xsd_validator.py`: Módulo completo para validación XSD local<br/>Líneas 83-104: `load_schema()` carga XSD con resolver local<br/>Líneas 107-143: `validate_xml_bytes()` valida XML contra XSD | Validación XSD local con resolver |
| E2) Normalización de campos obligatorios (fechas, RUC-DV, límites numéricos) | ⚠️ **PARTIAL** | `tools/send_sirecepde.py` líneas 3366-3383: `_scan_xml_bytes_for_common_malformed()` detecta BOM, control chars, `&` mal formados<br/>**FALTA**: No hay validación explícita de formato de fechas, RUC-DV, límites numéricos antes de enviar | **ACCIÓN**: Agregar validación de formato de campos obligatorios (fechas ISO, RUC-DV regex, totales numéricos) |
| E3) Manejo de errores: mensajes claros y trazables | ✅ **OK** | `app/sifen_client/exceptions.py`: `SifenClientError`, `SifenSizeLimitError`<br/>`tools/send_sirecepde.py` líneas 2750-2767: Guarda artifacts si faltan dependencias<br/>Líneas 3073-3089: Guarda artifacts si falla firma | Errores con mensajes claros y artifacts para diagnóstico |
| **F) FLUJO ASYNC (SIN CONECTAR)** |
| F1) Existe módulo "recibe-lote" (async) y "consulta-lote" (polling) | ✅ **OK** | `app/sifen_client/soap_client.py` línea 1708: `recepcion_lote()` envía `siRecepLoteDE`<br/>Línea 2569: `consulta_lote_raw()` consulta `siConsLoteDE`<br/>`web/main.py` líneas 1102-1178: `_check_lote_status_async()` polling automático | Async recepción + polling consulta implementados |
| F2) Persistencia de dProtConsLote y estado de lote | ✅ **OK** | `web/lotes_db.py` líneas 40-55: Tabla `sifen_lotes` con `d_prot_cons_lote TEXT NOT NULL UNIQUE`<br/>Líneas 81-123: `create_lote()` guarda `d_prot_cons_lote`<br/>`web/db.py` líneas 59, 204: `de_documents` tiene `d_prot_cons_lote` | Persistencia en SQLite con UNIQUE constraint |
| F3) Mecanismo de polling/consulta periódica (sin conexión real) | ✅ **OK** | `tools/poll_sifen_lotes.py`: Script de polling infinito con backoff<br/>`web/main.py` líneas 1102-1178: `_check_lote_status_async()` ejecuta en background<br/>`app/sifen_client/lote_checker.py` líneas 94-272: `check_lote_status()` con retry | Polling implementado (CLI y web) |
| **G) CONSULTAS (SIN CONECTAR)** |
| G1) Consulta de lote por dProtConsLote (siConsLoteDE) | ✅ **OK** | `app/sifen_client/soap_client.py` líneas 2569-2891: `consulta_lote_raw()` implementa `siConsLoteDE`<br/>Líneas 2879-2891: SOAP 1.2 con `rEnviConsLoteDe` en Body | Implementado con SOAP 1.2 |
| G2) Consulta de DE individual por CDC (siConsDE) | ✅ **OK** | `app/sifen_client/soap_client.py` líneas 3087-3433: `consulta_de_por_cdc_raw()` implementa `siConsDE`<br/>Líneas 3126-3139: `rEnviConsDeRequest` con `dId` y `dCDC` | Implementado con SOAP 1.2 |
| G3) Consulta de RUC (siConsRUC) | ✅ **OK** | `app/sifen_client/soap_client.py` líneas 3449-3838: `consulta_ruc_raw()` implementa `siConsRUC`<br/>Líneas 3497-3511: `rEnviConsRUC` con `dId` y `dRUCCons` | Implementado con SOAP 1.2 |
| **H) OBSERVABILIDAD (SIN CONECTAR)** |
| H1) Logging estructurado (nivel, contexto, sin secretos) | ✅ **OK** | `app/sifen_client/soap_client.py` línea 65: `logger = logging.getLogger(__name__)`<br/>Líneas 321-330: Logs sin exponer paths completos de certs<br/>`tools/send_sirecepde.py` líneas 4846-4866: SIFEN SANITY CHECK con logging estructurado | Logging estructurado, no expone secretos |
| H2) Artifacts de debug (request/response, ZIP, lote.xml) | ✅ **OK** | `app/sifen_client/soap_client.py` líneas 1988-2010: Guarda `soap_last_request_BYTES.bin`, `soap_last_request_SENT.xml`<br/>`tools/send_sirecepde.py` líneas 3613-3670: Guarda `last_xde.zip`, `last_lote.xml` siempre | Artifacts extensivos para diagnóstico |
| H3) Trazabilidad de errores (tracebacks, contexto) | ✅ **OK** | `tools/send_sirecepde.py` líneas 3073-3089: Guarda `sign_error_details.txt` con traceback<br/>Líneas 3241-3257: Guarda `sign_preflight_error.txt` con contexto | Tracebacks y contexto guardados en artifacts |
| **I) SEGURIDAD (SIN CONECTAR)** |
| I1) No hay secretos hardcodeados (passwords, claves, PFX) | ✅ **OK** | `.gitignore` líneas 77-80: Excluye `*.p12`, `*.pfx`, `*certificates*`<br/>`grep -i "password\|BEGIN PRIVATE KEY" tesaka-cv/`: No hay secretos hardcodeados<br/>`app/sifen_client/config.py` líneas 31-43: Lee desde env vars | **RIESGO**: Bajo. No se encontraron secretos hardcodeados |
| I2) Validación de entrada (sanitización, escape) | ⚠️ **PARTIAL** | `tools/send_sirecepde.py` líneas 3366-3383: `_scan_xml_bytes_for_common_malformed()` detecta BOM, control chars<br/>**FALTA**: No hay sanitización explícita de user input en web endpoints | **ACCIÓN**: Agregar validación de entrada en `web/main.py` endpoints (sanitizar XML, validar RUC formato) |
| I3) Guard-rails para dependencias faltantes | ✅ **OK** | `tools/send_sirecepde.py` líneas 2695-2704: `_check_signing_dependencies()` verifica `lxml` y `xmlsec`<br/>Líneas 2750-2767: Bloquea envío si faltan dependencias, guarda artifacts | Guard-rails implementados |
| **J) TESTS (SIN CONECTAR)** |
| J1) Tests unitarios de firma XML | ✅ **OK** | `tests/test_xml_signer.py`: 8 tests de firma/verificación<br/>Líneas 140-156: `test_xml_signer_sign()` genera firma<br/>Líneas 158-167: `test_xml_signer_verify()` verifica firma | Tests unitarios completos |
| J2) Tests de conversión P12→PEM | ✅ **OK** | `tests/test_pkcs12_utils.py`: 10 tests de conversión P12<br/>Líneas 91-123: `test_p12_to_temp_pem_files_success()` verifica conversión<br/>Líneas 223-252: Tests verifican que password no aparece en logs | Tests completos de P12 |
| J3) Tests de mTLS (mock) | ✅ **OK** | `tests/test_soap_client_mtls.py`: Tests de fallback a env vars<br/>Líneas 34-50: `test_create_transport_fallback_to_env_vars()` verifica mTLS | Tests de mTLS con mocks |
| J4) Tests de validación XSD | ⚠️ **PARTIAL** | `tests/test_schemas.py`: Existe pero no se verificó contenido<br/>**FALTA**: Verificar que hay tests de validación XSD con XMLs de ejemplo | **ACCIÓN**: Revisar `tests/test_schemas.py` y agregar tests si faltan |
| **K) VALIDACIONES PREFLIGHT (SIN CONECTAR)** |
| K1) Validación de estructura XML (root, namespaces) | ✅ **OK** | `tools/send_sirecepde.py` líneas 3690-3955: `preflight_soap_request()` valida SOAP, ZIP, lote.xml<br/>Líneas 3776-3895: Valida root `rLoteDE`, namespace SIFEN, estructura | Validación preflight extensiva |
| K2) Validación de firma (SHA256, URI correcto) | ✅ **OK** | `tools/send_sirecepde.py` líneas 3091-3257: Validación post-firma<br/>Líneas 3148-3199: Valida `SignatureMethod=rsa-sha256`, `DigestMethod=sha256`, `Reference URI=#Id` | Validación de firma completa |
| K3) Validación de tamaño (límites SIFEN) | ✅ **OK** | `app/sifen_client/soap_client.py` líneas 75-81: `SIZE_LIMITS` dict con límites<br/>Líneas 547-575: `_validate_size()` valida antes de enviar | Validación de tamaño implementada |
| K4) Gate de habilitación FE del RUC | ✅ **OK** | `tools/send_sirecepde.py` líneas 4789-4945: Gate que llama `consulta_ruc_raw()`<br/>Líneas 4905-4920: Valida `dRUCFactElec ∈ {"1","S","SI"}`<br/>`web/main.py` líneas 711-884: Gate replicado en web flow | Gate implementado (CLI y web) |
| K5) Sanity check de RUCs (DE vs GATE vs CERT) | ✅ **OK** | `tools/send_sirecepde.py` líneas 4846-4866: SIFEN SANITY CHECK compara RUC-DE, RUC-GATE, RUC-CERT<br/>`web/main.py` líneas 774-801: Sanity check replicado en web | Sanity check implementado |
| **L) PENDIENTES POR HABILITACIÓN/CREDENCIALES/CONEXIÓN REAL** |
| L1) Certificado P12 real emitido por PSC | 🔴 **EXTERNAL/WAITING** | **REQUIERE**: Certificado P12 real emitido por PSC (Proveedor de Servicios de Certificación)<br/>**ACCIÓN**: Obtener certificado P12 real de PSC autorizado | Depende de gestión externa (PSC) |
| L2) Habilitación FE del RUC en SIFEN | 🔴 **EXTERNAL/WAITING** | **REQUIERE**: RUC habilitado para Facturación Electrónica en SIFEN<br/>**ACCIÓN**: Gestionar habilitación FE del RUC en SIFEN/SET | Depende de gestión externa (SIFEN/SET) |
| L3) Acceso a ambiente TEST de SIFEN | 🔴 **EXTERNAL/WAITING** | **REQUIERE**: Credenciales y acceso a `sifen-test.set.gov.py`<br/>**ACCIÓN**: Solicitar acceso a ambiente TEST de SIFEN | Depende de gestión externa (SIFEN) |
| L4) Acceso a ambiente PROD de SIFEN | 🔴 **EXTERNAL/WAITING** | **REQUIERE**: Credenciales y acceso a `sifen.set.gov.py`<br/>**ACCIÓN**: Solicitar acceso a ambiente PROD de SIFEN | Depende de gestión externa (SIFEN) |
| L5) Pruebas end-to-end con SIFEN real | 🔴 **EXTERNAL/WAITING** | **REQUIERE**: Conexión real a SIFEN TEST/PROD<br/>**ACCIÓN**: Ejecutar pruebas E2E una vez obtenidas credenciales | Depende de L1-L4 |

---

## RESUMEN EJECUTIVO

### ✅ **IMPLEMENTADO (OFFLINE)**
- **Configuración test/prod**: ✅ Separación clara, URLs parametrizadas
- **SOAP 1.2**: ✅ Cliente SOAP 1.2 con Content-Type correcto
- **mTLS**: ✅ Soporte completo P12→PEM, configuración de certificados
- **Firma XML**: ✅ XMLDSig enveloped con RSA-SHA256/SHA-256
- **Validación XSD**: ✅ Validación local con resolver
- **Flujo async**: ✅ Recepción async + polling consulta
- **Persistencia**: ✅ SQLite con tablas para documentos y lotes
- **Consultas**: ✅ `siConsLoteDE`, `siConsDE`, `siConsRUC` implementados
- **Observabilidad**: ✅ Logging estructurado, artifacts extensivos
- **Seguridad**: ✅ No hay secretos hardcodeados, guard-rails implementados
- **Tests**: ✅ Tests unitarios de firma, P12, mTLS
- **Validaciones preflight**: ✅ Validación extensiva antes de enviar
- **Gates**: ✅ Gate de habilitación FE del RUC + sanity check

### ⚠️ **PARCIALMENTE IMPLEMENTADO**
- **TLS 1.2 forzado**: ⚠️ Comentario pero no verificación explícita
- **Normalización de campos**: ⚠️ Detecta malformación pero no valida formato de fechas/RUC-DV
- **`.env.example`**: ⚠️ Falta archivo de ejemplo
- **Validación de entrada**: ⚠️ Detecta malformación XML pero no sanitiza user input
- **Tests XSD**: ⚠️ Existe `test_schemas.py` pero no se verificó contenido

### 🔴 **PENDIENTE (EXTERNAL/WAITING)**
- **Certificado P12 real**: 🔴 Requiere gestión externa (PSC)
- **Habilitación FE del RUC**: 🔴 Requiere gestión externa (SIFEN/SET)
- **Acceso TEST/PROD**: 🔴 Requiere credenciales de SIFEN
- **Pruebas E2E**: 🔴 Requiere conexión real

---

## RIESGOS IDENTIFICADOS

### 🔴 **RIESGO ALTO**
- **Ninguno identificado**: No se encontraron secretos hardcodeados ni riesgos críticos.

### ⚠️ **RIESGO MEDIO**
1. **TLS 1.2 no forzado explícitamente**: Aunque se usa `requests` que por defecto soporta TLS 1.2+, no hay verificación explícita de versión mínima.
   - **ACCIÓN**: Agregar verificación de versión TLS mínima en `_create_transport()`.

2. **Falta `.env.example`**: No hay archivo de ejemplo para configurar variables de entorno.
   - **ACCIÓN**: Crear `tesaka-cv/.env.example` con todas las variables requeridas (sin valores reales).

### ✅ **RIESGO BAJO**
1. **Validación de formato de campos**: Aunque se detecta malformación XML, no hay validación explícita de formato de fechas, RUC-DV, límites numéricos.
   - **ACCIÓN**: Agregar validación de formato antes de enviar (opcional, pero recomendado).

---

## ACCIONES RECOMENDADAS (PRIORIDAD)

### 🔴 **ALTA PRIORIDAD (ANTES DE PROD)**
1. **Crear `.env.example`**: Documentar todas las variables de entorno requeridas.
2. **Forzar TLS 1.2 explícitamente**: Agregar verificación de versión TLS mínima.

### ⚠️ **MEDIA PRIORIDAD (MEJORAS)**
1. **Validación de formato de campos**: Agregar validación de fechas ISO, RUC-DV regex, totales numéricos.
2. **Sanitización de entrada**: Agregar validación de user input en web endpoints.
3. **Revisar tests XSD**: Verificar que `tests/test_schemas.py` tiene cobertura adecuada.

### ✅ **BAJA PRIORIDAD (NICE TO HAVE)**
1. **Métricas estructuradas**: Agregar contadores/histogramas de códigos de respuesta SIFEN.
2. **Alertas**: Implementar alertas si `dCodRes=0301` ocurre frecuentemente.

---

## CONCLUSIÓN

**El repositorio está bien preparado para la integración SIFEN**. La mayoría de los puntos del checklist están implementados (✅ **OK**). Los puntos pendientes son principalmente:

1. **Gestión externa** (certificados, habilitación RUC, acceso SIFEN): 🔴 **EXTERNAL/WAITING**
2. **Mejoras menores** (TLS 1.2 explícito, `.env.example`, validación de formato): ⚠️ **PARTIAL**

**Recomendación**: Proceder con la obtención de credenciales y certificados reales. El código está listo para pruebas E2E una vez que se obtengan los accesos.

---

**Última actualización**: 2025-01-XX  
**Versión**: 1.0

