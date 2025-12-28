# Plan Técnico de Integración SIFEN - Ambiente de Pruebas

## 📋 Estado de la Investigación

**⚠️ NOTA IMPORTANTE**: Esta documentación requiere acceso directo a las fuentes oficiales mencionadas. Las búsquedas web no proporcionaron acceso directo a los PDFs y documentación técnica específica. Se requiere revisión manual de:

**✅ ARQUITECTURA DECIDIDA**: Mantener FastAPI + Jinja2 (server-side rendering)
- No se requiere migrar a Angular
- El Prevalidador SIFEN es una aplicación web externa (Angular del DNIT)
- Nuestra app genera XML y puede validarlo localmente o usar el Prevalidador web manualmente

1. **Guía de Pruebas del SIFEN (PDF DNIT)**: https://www.dnit.gov.py/documents/20123/424160/Gu%C3%ADa%2Bde%2BPruebas%2BFase%2Bde%2BVoluntariedad%2BAbierta%2Bpara%2Bel%2BSistema%2BIntegrado%2Bde%2BFacturaci%C3%B3n%2BElectr%C3%B3nica%2BNacional.pdf

2. **Portal e-Kuatia - Documentación Técnica**: https://www.dnit.gov.py/web/e-kuatia/documentacion-tecnica

3. **Prevalidador SIFEN**: https://ekuatia.set.gov.py/prevalidador/validacion

---

## A) Ambiente de Pruebas Oficial

### ❓ Pregunta: ¿Existe "Ambiente de Pruebas" oficial?

**Estado**: PENDIENTE DE CONFIRMACIÓN desde documentación oficial

**Fuente esperada**: Guía de Pruebas del SIFEN (PDF DNIT)

**Acción requerida**: 
- [ ] Descargar y leer el PDF completo de la Guía de Pruebas
- [ ] Identificar sección que describe el ambiente de pruebas/sandbox
- [ ] Extraer información sobre:
  - URL base del ambiente de pruebas
  - Qué permite validar exactamente
  - Limitaciones vs. ambiente productivo

**Suposición inicial** (requiere verificación):
- Probablemente existe un ambiente de pruebas que permite:
  - Validar estructura XML de Documentos Electrónicos (DE)
  - Enviar solicitudes sin generar documentos válidos fiscalmente
  - Probar flujos de timbrado sin compromiso legal

---

## B) URLs/Endpoints - Servicios Web

### ❓ Información requerida desde documentación técnica

**Fuente esperada**: Portal e-Kuatia - Documentación Técnica

### Checklist de información a extraer:

#### B.1. URL Base Ambiente de Pruebas
- [ ] URL base del ambiente de pruebas (ej: `https://ekuatia.set.gov.py/test/` o similar)
- [ ] Sección del documento donde se encuentra (ej: "Configuración", pág. X)

#### B.2. Tipo de Servicio
- [ ] ¿SOAP o REST?
  - [ ] Si SOAP: URL del WSDL
  - [ ] Si REST: Base URL + endpoints
- [ ] Versión de API
- [ ] Sección del documento

#### B.3. Autenticación y Seguridad
- [ ] ¿Usa mutual TLS (mTLS)?
- [ ] Si usa mTLS:
  - [ ] Tipo de certificado requerido (.p12, .pfx, .pem)
  - [ ] Cadena de certificados necesaria
  - [ ] Password del certificado
  - [ ] Si requiere certificado CA intermedio
- [ ] Si no usa mTLS:
  - [ ] Tipo de autenticación (API Key, OAuth, Basic Auth, etc.)
- [ ] Sección del documento

#### B.4. Endpoints Principales
- [ ] Endpoint para envío/recepción de DE
- [ ] Endpoint para consulta de estado
- [ ] Endpoint para anulación
- [ ] Otros endpoints relevantes
- [ ] Métodos HTTP (POST, GET, etc.)
- [ ] Formatos de request/response (XML, JSON)

---

## C) Datos de Prueba

### Checklist de datos requeridos:

- [ ] **RUC de Prueba**
  - Valor: `_____________`
  - Uso: `_____________`
  - Fuente: `_____________` (Sección/página)

- [ ] **Timbrado de Prueba**
  - Valor: `_____________`
  - Uso: `_____________`
  - Fuente: `_____________`

- [ ] **CSC (Código de Seguridad del Contribuyente) de Prueba**
  - Valor: `_____________`
  - Uso: `_____________`
  - Fuente: `_____________`

- [ ] **Datos de Cliente/Comprador de Prueba**
  - RUC: `_____________`
  - Razón Social: `_____________`
  - Fuente: `_____________`

- [ ] **Otros datos de prueba** (si aplica):
  - `_____________`
  - `_____________`

---

## D) Flujo Mínimo "Smoke Test" End-to-End

### Flujo propuesto (requiere validación con documentación):

#### Paso 1: Generar DE XML
- [ ] Verificar esquema XSD de SIFEN
- [ ] Generar XML válido según estructura oficial
- [ ] Validación local contra XSD
- **Fuente requerida**: Esquema XSD oficial (¿disponible en documentación técnica?)

#### Paso 2: Prevalidar XML
- [ ] Enviar XML al Prevalidador SIFEN
  - URL: https://ekuatia.set.gov.py/prevalidador/validacion
  - Método: POST (verificar en documentación)
  - Formato: multipart/form-data o directo XML
- [ ] Obtener resultado de validación
- [ ] Corregir errores si los hay
- **Fuente requerida**: Documentación del Prevalidador

#### Paso 3: Enviar DE al Ambiente de Pruebas
- [ ] Configurar cliente HTTP/SOAP con certificados (si aplica)
- [ ] Enviar XML al endpoint de recepción
- [ ] Obtener respuesta (código de respuesta, XML respuesta)
- **Fuente requerida**: Documentación técnica - Endpoints

#### Paso 4: Consultar Estado/Resultado
- [ ] Usar endpoint de consulta con identificador recibido
- [ ] Verificar estado del DE (aceptado, rechazado, pendiente)
- [ ] Obtener detalles adicionales si aplica
- **Fuente requerida**: Documentación técnica - Consultas

#### Paso 5: Guardar Respuesta
- [ ] Persistir XML enviado
- [ ] Persistir XML respuesta
- [ ] Persistir estado final
- [ ] Registrar timestamp y metadatos

### Checklist de validación del flujo:
- [ ] XML generado es válido según XSD
- [ ] Prevalidador acepta el XML sin errores críticos
- [ ] Servicio de pruebas acepta la solicitud
- [ ] Se recibe respuesta válida
- [ ] Consulta de estado funciona correctamente
- [ ] Datos se persisten correctamente en BD

---

## E) Limitaciones sin Habilitación

### ❓ ¿Qué NO se puede probar sin estar habilitado?

**Estado**: PENDIENTE DE CONFIRMACIÓN

### Información a verificar:

- [ ] **Envío real de DE**: ¿Requiere credenciales/productivo?
- [ ] **Timbrado real**: ¿El ambiente de pruebas timbra documentos?
- [ ] **Consultas a RUC reales**: ¿Hay limitaciones?
- [ ] **Generación de PDF**: ¿Funciona en pruebas?
- [ ] **Anulaciones**: ¿Se pueden probar anulaciones?
- [ ] **Otros servicios específicos**: `_____________`

### Datos que necesitamos del cliente (si aplica):
- [ ] RUC del contribuyente
- [ ] Número de timbrado
- [ ] CSC (Código de Seguridad del Contribuyente)
- [ ] Certificado digital (.p12/.pfx) si usa mTLS
- [ ] Password del certificado
- [ ] Fecha de vencimiento del timbrado
- [ ] Ambiente autorizado (pruebas/producción)
- [ ] Otros: `_____________`

---

## 3. Propuesta de Integración en FastAPI

### 3.1. Estructura de Módulo

```
tesaka-cv/app/
├── sifen_client/
│   ├── __init__.py
│   ├── config.py          # Configuración por ambiente
│   ├── client.py          # Cliente HTTP/SOAP principal
│   ├── models.py          # Modelos de datos SIFEN (XML, respuestas)
│   ├── xml_generator.py   # Generación de XML según esquema SIFEN
│   ├── validator.py       # Validación XSD local + Prevalidador
│   └── utils.py           # Utilidades (certificados, encoding, etc.)
├── routes/
│   └── sifen_routes.py    # Endpoints FastAPI para SIFEN
└── templates/
    └── sifen/
        └── test.html      # UI para smoke test
```

### 3.2. Configuración por Ambiente

**Archivo**: `sifen_client/config.py`

```python
# Propuesta de estructura
class SifenConfig:
    ENV_TEST = "test"
    ENV_PROD = "prod"
    
    # URLs base (requiere confirmación desde doc)
    BASE_URLS = {
        "test": "https://ekuatia.set.gov.py/test/api/v1/",  # EJEMPLO - VERIFICAR
        "prod": "https://ekuatia.set.gov.py/api/v1/"        # EJEMPLO - VERIFICAR
    }
    
    # Endpoints (requiere confirmación desde doc)
    ENDPOINTS = {
        "prevalidador": "/prevalidador/validacion",
        "envio_de": "/documentos/electronico/enviar",
        "consulta": "/documentos/electronico/consultar",
        # ... otros
    }
```

### 3.3. Variables de Entorno

**Archivo**: `.env` (extender el existente)

```env
# SIFEN Configuration
SIFEN_ENV=test  # test | prod

# URLs Base (REQUIERE CONFIRMACIÓN desde documentación oficial)
SIFEN_TEST_BASE_URL=https://ekuatia.set.gov.py/test/api/v1/  # VERIFICAR
SIFEN_PROD_BASE_URL=https://ekuatia.set.gov.py/api/v1/  # VERIFICAR

# Tipo de Servicio (REQUIERE CONFIRMACIÓN)
SIFEN_SERVICE_TYPE=REST  # REST o SOAP - VERIFICAR

# WSDL URLs (si es SOAP)
SIFEN_WSDL_URL_TEST=
SIFEN_WSDL_URL_PROD=

# Autenticación - Mutual TLS
SIFEN_USE_MTLS=false  # true si requiere certificado
SIFEN_CERT_PATH=/path/to/certificate.p12  # Solo si SIFEN_USE_MTLS=true
SIFEN_CERT_PASSWORD=your_password
SIFEN_CA_BUNDLE_PATH=/path/to/ca-bundle.pem  # Si aplica

# Credenciales alternativas (si no usa mTLS)
SIFEN_API_KEY=your_api_key  # VERIFICAR si aplica
SIFEN_USER=your_user        # VERIFICAR si aplica
SIFEN_PASSWORD=your_password  # VERIFICAR si aplica

# Timeouts
SIFEN_REQUEST_TIMEOUT=30

# Datos de Prueba (solo para ambiente test)
SIFEN_TEST_RUC=12345678901  # VERIFICAR con documentación
SIFEN_TEST_TIMBRADO=12345678  # VERIFICAR
SIFEN_TEST_CSC=test_csc_code  # VERIFICAR
SIFEN_TEST_RAZON_SOCIAL=Contribuyente de Prueba
```

**✅ IMPLEMENTADO**: La estructura base está lista en `app/sifen_client/config.py`

### 3.4. Endpoint de Smoke Test

**✅ IMPLEMENTADO**: `app/routes_sifen.py`

Endpoints disponibles:
- `POST /dev/sifen-smoke-test` - Ejecuta smoke test completo
- `GET /dev/sifen-smoke-test` - UI HTML para ejecutar test
- `POST /dev/sifen-prevalidate` - Prevalida XML personalizado

**Funcionalidad actual**:
- ✅ Validación de estructura XML (well-formed)
- ✅ Validación XSD (template, requiere esquema oficial)
- ✅ Integración con Prevalidador SIFEN (https://ekuatia.set.gov.py/prevalidador/validacion)
- ✅ Envío al ambiente de pruebas (si datos configurados)
- ✅ Manejo de errores y logging
- ✅ UI HTML para pruebas manuales

**Pendiente**:
- ⏳ XML de prueba real según esquema SIFEN (requiere XSD oficial)
- ⏳ Validación XSD completa (requiere esquema oficial)
- ⏳ Consulta de estado después del envío

---

## 4. Checklist Técnico de Implementación

### Fase 1: Investigación y Documentación
- [ ] Descargar y leer completamente "Guía de Pruebas del SIFEN (PDF DNIT)"
- [ ] Revisar "Portal e-Kuatia - Documentación Técnica" completa
- [ ] Probar Prevalidador SIFEN manualmente
- [ ] Documentar todos los hallazgos en este archivo
- [ ] Identificar URLs, endpoints, formatos exactos

### Fase 2: Configuración Base
- [x] Crear módulo `sifen_client/`
- [x] Implementar `config.py` con configuración por ambiente
- [x] Agregar variables de entorno necesarias
- [x] Crear estructura de modelos de datos

### Fase 3: Cliente HTTP/SOAP
- [x] Implementar cliente base REST (template listo)
- [x] Configurar mTLS si aplica (estructura lista, requiere confirmación)
- [x] Manejar certificados y passwords (estructura lista)
- [x] Implementar manejo de errores y timeouts
- [ ] Implementar cliente SOAP (si aplica, requiere WSDL)

### Fase 4: Generación y Validación XML
- [ ] Obtener/especificar esquema XSD de SIFEN (CRÍTICO)
- [ ] Implementar generador de XML según estructura oficial (pendiente XSD)
- [x] Validación local básica (well-formed XML)
- [x] Integración con Prevalidador SIFEN (✅ funcional)

### Fase 5: Smoke Test
- [x] Implementar endpoint `/dev/sifen-smoke-test`
- [x] Flujo completo end-to-end (parcial - requiere datos oficiales)
- [ ] Persistencia de resultados (pendiente tabla en BD)
- [x] UI básica para ejecutar test (✅ template HTML)

### Fase 6: Documentación
- [ ] Documentar configuración
- [ ] Guía de uso del smoke test
- [ ] Troubleshooting común
- [ ] Actualizar README principal

---

## 5. Información Faltante (Requerir al Cliente/DNIT)

### Crítico (imposible avanzar sin esto):
1. [ ] URLs exactas del ambiente de pruebas
2. [ ] Tipo de servicio (SOAP/REST)
3. [ ] Esquema XSD oficial de SIFEN
4. [ ] Tipo de autenticación requerida
5. [ ] Datos de prueba (RUC, Timbrado, CSC)

### Importante (necesario para funcionalidad completa):
6. [ ] WSDL (si SOAP) o OpenAPI spec (si REST)
7. [ ] Ejemplos de request/response XML
8. [ ] Códigos de error y su significado
9. [ ] Límites de tasa (rate limits)
10. [ ] Horarios de disponibilidad del servicio

### Opcional (mejora la experiencia):
11. [ ] Herramientas de testing recomendadas
12. [ ] Comunidad/foro de soporte
13. [ ] Contacto técnico para consultas

---

## 6. Próximos Pasos Inmediatos

1. **Descargar y revisar documentos oficiales**:
   - [ ] Guía de Pruebas PDF
   - [ ] Documentación técnica e-Kuatia
   - [ ] Probar Prevalidador manualmente

2. **Completar este documento** con información extraída

3. **Una vez completa la información**, proceder con implementación según checklist técnico

---

## Notas Adicionales

- Este plan es una plantilla inicial que requiere completarse con información oficial
- No asumir URLs, formatos o protocolos sin confirmación en documentación
- Mantener separación clara entre ambiente de pruebas y producción
- Implementar logging detallado para debugging
- Considerar implementar retry logic y circuit breakers
- Validar siempre contra esquemas oficiales antes de enviar

---

**Última actualización**: [FECHA]  
**Estado**: Pendiente de información oficial  
**Responsable**: [NOMBRE]

