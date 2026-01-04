# URLs de SIFEN Agrupadas por Servicio

Este documento lista todas las URLs hacia `sifen-test.set.gov.py`, `sifen.set.gov.py` y `ekuatia.set.gov.py` encontradas en el repositorio, agrupadas por servicio.

---

## 📋 Resumen de Operaciones (excluyendo siRecepLoteDE)

| Servicio | Operación | Test URL | Prod URL | Estado |
|----------|-----------|----------|----------|--------|
| **Async Recepción** | `siRecepLoteDE` | ✅ | ✅ | ✅ Implementado |
| **Sync Recepción** | `siRecepDE` | ✅ | ✅ | ❌ No implementado |
| **Consulta Lote** | `siConsLoteDE` | ✅ | ✅ | ✅ Implementado |
| **Consulta DE** | `siConsDE` / `rEnviConsDE` | ✅ | ✅ | ✅ Implementado |
| **Consulta RUC** | `siConsRUC` / `rEnviConsRUC` | ✅ | ✅ | ❌ No implementado |
| **Eventos** | `siRecepEvento` | ✅ | ✅ | ❌ No implementado |
| **Prevalidador** | Web UI | ✅ | ✅ | ✅ Integrado (web) |
| **QR Consultas** | Web | ✅ | ✅ | ✅ Implementado |

---

## 1. 🚀 Async Recepción (siRecepLoteDE)

**Operación**: `siRecepLoteDE`  
**Propósito**: Recibir lotes de hasta 50 DEs para procesamiento asíncrono

### URLs

**Test**:
- `https://sifen-test.set.gov.py/de/ws/async/recibe-lote.wsdl?wsdl` (config.py línea 107)
- `https://sifen-test.set.gov.py/de/ws/async/recibe-lote.wsdl` (docs/SIFEN_BEST_PRACTICES.md línea 29)

**Prod**:
- `https://sifen.set.gov.py/de/ws/async/recibe-lote.wsdl` (config.py línea 115, docs/SIFEN_BEST_PRACTICES.md línea 30)

### Archivos donde se usa:
- `app/sifen_client/config.py` (líneas 107, 115)
- `docs/SIFEN_BEST_PRACTICES.md` (líneas 29-30)
- `tools/consulta_lote_de.py` (línea 1032 - ejemplo en help)

### Estado: ✅ **IMPLEMENTADO**
- Función: `SoapClient.recepcion_lote()` (línea 1707 en `soap_client.py`)
- CLI: `tools/send_sirecepde.py`

---

## 2. 🔄 Sync Recepción (siRecepDE)

**Operación**: `siRecepDE`  
**Propósito**: Recibir un DE individual de forma síncrona (no por lote)

### URLs

**Test**:
- `https://sifen-test.set.gov.py/de/ws/sync/recibe.wsdl` (config.py línea 106)

**Prod**:
- `https://sifen.set.gov.py/de/ws/sync/recibe.wsdl` (config.py línea 114)

### Archivos donde se usa:
- `app/sifen_client/config.py` (líneas 106, 114)

### Estado: ❌ **NO IMPLEMENTADO**
- Configurado en `config.py` pero sin función wrapper

---

## 3. 🔍 Consulta Lote (siConsLoteDE)

**Operación**: `siConsLoteDE` / `rEnviConsLoteDe`  
**Propósito**: Consultar el estado de procesamiento de un lote recibido

### URLs

**Test**:
- `https://sifen-test.set.gov.py/de/ws/consultas-lote/consulta-lote.wsdl` (config.py línea 109)
- `https://sifen-test.set.gov.py/de/ws/consultas-lote/consulta-lote.wsdl?wsdl` (consulta_lote_de.py línea 623)
- `https://sifen-test.set.gov.py/de/ws/consultas-lote/consulta-lote` (consulta_lote_de.py línea 942 - endpoint sin .wsdl)
- `https://sifen-test.set.gov.py/de/ws/consultas/consulta-lote.wsdl` (soap_client.py línea 2993 - **NOTA: ruta diferente**)

**Prod**:
- `https://sifen.set.gov.py/de/ws/consultas-lote/consulta-lote.wsdl` (config.py línea 117)
- `https://sifen.set.gov.py/de/ws/consultas-lote/consulta-lote.wsdl?wsdl` (consulta_lote_de.py línea 625)
- `https://sifen.set.gov.py/de/ws/consultas-lote/consulta-lote` (consulta_lote_de.py línea 940 - endpoint sin .wsdl)
- `https://sifen.set.gov.py/de/ws/consultas/consulta-lote.wsdl` (soap_client.py línea 2995 - **NOTA: ruta diferente**)

### Archivos donde se usa:
- `app/sifen_client/config.py` (líneas 109, 117)
- `app/sifen_client/soap_client.py` (líneas 2993, 2995)
- `tools/consulta_lote_de.py` (líneas 623, 625, 940, 942)
- `docs/SIFEN_BEST_PRACTICES.md` (líneas 35-36)
- `docs/OPERACIONES_SOAP_SIFEN.md` (líneas 155-156)

### ⚠️ **INCONSISTENCIA DETECTADA**:
- `config.py` usa: `/de/ws/consultas-lote/consulta-lote.wsdl`
- `soap_client.py` usa: `/de/ws/consultas/consulta-lote.wsdl` (ruta diferente)

### Estado: ✅ **IMPLEMENTADO**
- Funciones:
  - `SoapClient.consulta_lote_de()` (línea 2564 - WSDL-driven)
  - `SoapClient.consulta_lote_raw()` (línea 2945 - SOAP 1.2 manual)
- CLI: `tools/consulta_lote_de.py`

---

## 4. 📄 Consulta DE por CDC (siConsDE)

**Operación**: `rEnviConsDE`  
**Propósito**: Consultar un DE específico por su CDC (Código de Control)

### URLs

**Test**:
- `https://sifen-test.set.gov.py/de/ws/consultas/consulta.wsdl` (config.py línea 111)
- `https://sifen-test.set.gov.py/de/ws/consultas/consulta-de.wsdl` (soap_client.py línea 3129 - **NOTA: ruta diferente**)

**Prod**:
- `https://sifen.set.gov.py/de/ws/consultas/consulta.wsdl` (config.py línea 119)
- `https://sifen.set.gov.py/de/ws/consultas/consulta-de.wsdl` (soap_client.py línea 3131 - **NOTA: ruta diferente**)

### Archivos donde se usa:
- `app/sifen_client/config.py` (líneas 111, 119)
- `app/sifen_client/soap_client.py` (líneas 3129, 3131)
- `docs/SIFEN_BEST_PRACTICES.md` (líneas 41-42)
- `docs/OPERACIONES_SOAP_SIFEN.md` (líneas 88-89)

### ⚠️ **INCONSISTENCIA DETECTADA**:
- `config.py` usa: `/de/ws/consultas/consulta.wsdl`
- `soap_client.py` usa: `/de/ws/consultas/consulta-de.wsdl` (ruta diferente)

### Estado: ✅ **IMPLEMENTADO**
- Función: `SoapClient.consulta_de_por_cdc_raw()` (línea 3086)
- CLI: Usado como fallback en `tools/consulta_lote_de.py` para `dCodResLot=0364`

---

## 5. 🏢 Consulta RUC (siConsRUC)

**Operación**: `siConsRUC` / `rEnviConsRUC`  
**Propósito**: Consultar estado y habilitación de un RUC (sin enviar DE)

### URLs

**Test**:
- `https://sifen-test.set.gov.py/de/ws/consultas/consulta-ruc.wsdl` (config.py línea 110)

**Prod**:
- `https://sifen.set.gov.py/de/ws/consultas/consulta-ruc.wsdl` (config.py línea 118)

### Archivos donde se usa:
- `app/sifen_client/config.py` (líneas 110, 118)
- `docs/OPERACIONES_SOAP_SIFEN.md` (líneas 12-13)

### Estado: ❌ **NO IMPLEMENTADO**
- Configurado en `config.py` pero sin función wrapper
- **Recomendado para verificar habilitación sin enviar DE**

---

## 6. 📅 Eventos (siRecepEvento)

**Operación**: `siRecepEvento`  
**Propósito**: Enviar eventos relacionados con DEs (anulaciones, etc.)

### URLs

**Test**:
- `https://sifen-test.set.gov.py/de/ws/eventos/evento.wsdl` (config.py línea 108)

**Prod**:
- `https://sifen.set.gov.py/de/ws/eventos/evento.wsdl` (config.py línea 116)

### Archivos donde se usa:
- `app/sifen_client/config.py` (líneas 108, 116)
- `docs/OPERACIONES_SOAP_SIFEN.md` (líneas 235-236)

### Estado: ❌ **NO IMPLEMENTADO**
- Configurado en `config.py` pero sin función wrapper

---

## 7. ✅ Prevalidador (Web UI)

**Propósito**: Herramienta de desarrollo para prevalidar XML antes de envío

### URLs

**Base**:
- `https://ekuatia.set.gov.py/prevalidador/` (config.py línea 99)

**Endpoints**:
- `https://ekuatia.set.gov.py/prevalidador/validacion` (validator.py línea 29, routes_sifen.py líneas 190, 237)
- `https://ekuatia.set.gov.py/prevalidador/api/validar` (validator.py línea 32 - tentativo)
- `https://ekuatia.set.gov.py/api/prevalidador/validar` (validator.py línea 33 - tentativo)
- `https://ekuatia.set.gov.py/prevalidador/validar` (validator.py línea 34 - tentativo)

### Archivos donde se usa:
- `app/sifen_client/config.py` (línea 99)
- `app/sifen_client/validator.py` (líneas 29, 32-34, 38)
- `app/routes_sifen.py` (líneas 190, 237)
- `docs/ANALISIS_VALIDACIONES_PREFLIGHT.md` (línea 135)

### Estado: ✅ **INTEGRADO** (Web UI)
- Clase: `SifenValidator` (validator.py)
- Tipo: Aplicación web Angular (no API REST programática directa)
- Nota: Requiere uso manual del formulario web para validación completa

---

## 8. 🔗 QR Consultas (Web)

**Propósito**: Generar URLs de consulta QR para DEs

### URLs

**Test**:
- `https://www.ekuatia.set.gov.py/consultas-test/qr?` (qr_generator.py línea 37)

**Prod**:
- `https://www.ekuatia.set.gov.py/consultas/qr?` (qr_generator.py línea 38)

### Archivos donde se usa:
- `app/sifen_client/qr_generator.py` (líneas 37-38)
- `tests/test_qr_generator.py` (líneas 44, 52, 76)

### Estado: ✅ **IMPLEMENTADO**
- Clase: `QRGenerator` (qr_generator.py)

---

## 9. 📚 XSDs y Schemas (Referencias)

**Propósito**: Esquemas XSD oficiales de SIFEN

### URLs Base

- `https://ekuatia.set.gov.py/sifen/xsd/` (múltiples referencias en XSDs)

### Ejemplos de XSDs referenciados:
- `https://ekuatia.set.gov.py/sifen/xsd/protProcesDE_v150.xsd`
- `https://ekuatia.set.gov.py/sifen/xsd/DE_v150.xsd`
- `https://ekuatia.set.gov.py/sifen/xsd/FE_Types_v141.xsd`
- `https://ekuatia.set.gov.py/sifen/xsd/SIFEN_Types_v141.xsd`
- `https://ekuatia.set.gov.py/sifen/xsd/Evento_v150.xsd`
- Y muchos más...

### Archivos donde se usa:
- Múltiples archivos `.xsd` en `schemas_sifen/`
- `app/sifen_client/xsd_validator.py` (líneas 37, 45)

---

## 10. ⚠️ URLs Legacy/No Confirmadas

### Recepción (Legacy)

**Test**:
- `https://sifen-test.set.gov.py/de/ws/recepcion/DERecepcion.wsdl` (tools/README.md línea 417)

**Prod**:
- `https://sifen.set.gov.py/de/ws/recepcion/DERecepcion.wsdl` (tools/README.md línea 418)

**Nota**: Esta URL aparece en `tools/README.md` pero no está en `config.py`. Puede ser una versión antigua o no confirmada.

---

## 📊 Resumen de Inconsistencias

### 1. Consulta Lote
- **config.py**: `/de/ws/consultas-lote/consulta-lote.wsdl`
- **soap_client.py**: `/de/ws/consultas/consulta-lote.wsdl` ❌

### 2. Consulta DE
- **config.py**: `/de/ws/consultas/consulta.wsdl`
- **soap_client.py**: `/de/ws/consultas/consulta-de.wsdl` ❌

**Recomendación**: Verificar con documentación oficial cuál es la ruta correcta y unificar.

---

## 🎯 Operaciones Disponibles (excluyendo siRecepLoteDE)

### ✅ Implementadas:
1. **siConsLoteDE** - Consulta de Lote
2. **siConsDE** - Consulta DE por CDC
3. **Prevalidador** - Validación web
4. **QR Consultas** - Generación de URLs QR

### ❌ No Implementadas (pero configuradas):
1. **siRecepDE** - Recepción síncrona individual
2. **siConsRUC** - Consulta RUC (⚠️ **Recomendado para verificar habilitación**)
3. **siRecepEvento** - Eventos de DE

---

## 📝 Notas

1. **siConsRUC** es la operación recomendada para verificar habilitación de RUC sin enviar un DE.
2. Las inconsistencias en rutas (`consulta-lote` vs `consulta/consulta-lote`, `consulta` vs `consulta-de`) requieren verificación con documentación oficial.
3. El Prevalidador es una aplicación web Angular, no una API REST directa.
4. Los XSDs se referencian desde `https://ekuatia.set.gov.py/sifen/xsd/` pero también están disponibles localmente en `schemas_sifen/`.

---

**Última actualización**: 2025-01-XX  
**Fuente**: Búsqueda exhaustiva en el repositorio

