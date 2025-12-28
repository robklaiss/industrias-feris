# Guía de Mejores Prácticas SIFEN - Implementación

Basado en: **"Recomendaciones y mejores prácticas para SIFEN - Guía para el desarrollador"** (Octubre 2024)

Fuente: [Portal e-Kuatia](https://ekuatia.set.gov.py)

---

## 📋 Resumen Ejecutivo

Esta guía implementa las mejores prácticas oficiales de SIFEN para la generación y envío de Documentos Electrónicos (DE).

---

## 🏗️ Arquitectura de Servicios

### Ambientes

Según la Guía de Mejores Prácticas:

1. **Ambiente de Producción**: `sifen.set.gov.py`
2. **Ambiente de Pruebas**: `sifen-test.set.gov.py`

### Servicios Web SOAP

SIFEN utiliza **SOAP versión 1.2** para todos los servicios principales:

#### 1. Recibe Lote DE
- **URL Test**: `https://sifen-test.set.gov.py/de/ws/async/recibe-lote.wsdl`
- **URL Prod**: `https://sifen.set.gov.py/de/ws/async/recibe-lote.wsdl`
- **Función**: Recibe lotes de hasta **50 Documentos Electrónicos** para procesamiento asíncrono
- **Método**: `rEnvRecLoteDE`

#### 2. Consulta Lote
- **URL Test**: `https://sifen-test.set.gov.py/de/ws/consultas/consulta-lote.wsdl`
- **URL Prod**: `https://sifen.set.gov.py/de/ws/consultas/consulta-lote.wsdl`
- **Función**: Consulta el estado de procesamiento de un lote recibido
- **Método**: `rEnviConsLoteDE`

#### 3. Consulta DE por CDC
- **URL Test**: `https://sifen-test.set.gov.py/de/ws/consultas/consulta.wsdl`
- **URL Prod**: `https://sifen.set.gov.py/de/ws/consultas/consulta.wsdl`
- **Función**: Consulta un DE específico por su CDC (Código de Control)
- **Método**: `rEnviConsDE`

### Prevalidador

- **URL**: `https://ekuatia.set.gov.py/prevalidador/`
- **Función**: Herramienta de desarrollo para prevalidar XML antes de envío
- **Tipo**: Aplicación web Angular (no API REST programática)

---

## 📝 Generación de Documentos Electrónicos

### Estructura XML

Según Manual Técnico v150:

```xml
<rDE xmlns="http://ekuatia.set.gov.py/sifen/xsd" 
     xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance" 
     xsi:schemaLocation="http://ekuatia.set.gov.py/sifen/xsd siRecepDE_v150.xsd">
```

### ⚠️ Reglas CRÍTICAS (NO violar)

1. **NO incluir espacios en blanco** al inicio o final de campos numéricos y alfanuméricos
2. **NO incluir comentarios XML** (`<!-- -->`)
3. **NO incluir caracteres de formato**:
   - Line-feed (`\n`)
   - Carriage return (`\r`)
   - Tab (`\t`)
   - Espacios entre etiquetas
4. **NO incluir prefijos** en el namespace de las etiquetas
5. **NO incluir etiquetas vacías** (excepto las obligatorias)
6. **NO incluir valores negativos** o caracteres no numéricos en campos numéricos
7. **Los nombres de campos son case-sensitive** (respetar exactamente minúsculas/mayúsculas)

Ejemplo: `gOpeDE` ≠ `GopeDE` ≠ `gopede`

### Procesamiento de Lotes

- **Máximo**: 50 DE por lote
- **Formato de envío**: Archivo ZIP con múltiples XML
- **Codificación**: XML debe ser codificado en **Base64** dentro del SOAP body
- **Procesamiento**: Asíncrono (enviar lote → consultar resultado más tarde)

---

## 🔐 Seguridad

### Mutual TLS (mTLS)

Según documentación técnica:

- **Protocolo**: TLS versión 1.2 con autenticación mutua
- **Certificado**: Expedido por PSC habilitado en Paraguay
- **Estándar**: `http://www.w3.org/2000/09/xmldsig#X509Data`
- **Clave**: RSA 2048 (software) o superior
- **Función criptográfica**: RSA conforme a XML Encryption
- **Message digest**: SHA-2 (SHA-256)

### Firma Digital

- **Estándar**: XML Digital Signature, formato Enveloped (W3C)
- **Transformaciones requeridas**:
  - Enveloped: `https://www.w3.org/TR/xmldsig-core1/#sec-EnvelopedSignature`
  - C14N: `http://www.w3.org/2001/10/xml-exc-c14n#`
- **Codificación**: Base64

---

## 📊 Códigos de Respuesta

### Recibe Lote

| Código | Significado | Acción |
|--------|-------------|--------|
| `0300` | Lote recibido con éxito | El lote será procesado. Consultar estado después de 10 minutos |
| `0301` | Lote no encolado | El lote NO será procesado. Verificar motivos de rechazo/bloqueo |

### Consulta Lote

| Código | Significado | Acción |
|--------|-------------|--------|
| `0360` | Número de lote inexistente | Verificar número de lote |
| `0361` | Lote en procesamiento | Consultar nuevamente después de 10 minutos (puede tardar 1-24 horas en alta carga) |
| `0362` | Procesamiento concluido | Revisar detalles de cada DE en el lote |
| `0364` | Consulta extemporánea | Lote consultado después de 48 horas. Usar consulta por CDC individual |

### Consulta DE

| Código | Significado | Acción |
|--------|-------------|--------|
| `0420` | DE no existe o no está aprobado | Reenviar DE después de revisar errores |
| `0422` | CDC encontrado (DE aprobado) | DE válido. XML retornado en `xContenDE` |

---

## 🔄 Flujo Recomendado

### 1. Prevalidación (Desarrollo)

```python
# Usar Prevalidador web: https://ekuatia.set.gov.py/prevalidador/
# O validación local contra XSD
from app.sifen_client.validator import SifenValidator

validator = SifenValidator()
result = validator.validate_against_xsd(xml_content)
```

### 2. Generación y Limpieza

```python
from app.sifen_client.xml_generator_v150 import create_rde_xml_v150
from app.sifen_client.xml_utils import prepare_xml_for_sifen

# Generar XML
xml_raw = create_rde_xml_v150(...)

# Aplicar mejores prácticas (remover espacios, comentarios, etc.)
xml_clean = prepare_xml_for_sifen(xml_raw)
```

### 3. Envío por Lotes

```python
# Agrupar hasta 50 DE en un lote
# Codificar en Base64
# Enviar vía SOAP recibe-lote
# Obtener dProtConsLote (número de lote)
```

### 4. Consulta de Resultado

```python
# Esperar mínimo 10 minutos
# Consultar estado del lote usando dProtConsLote
# Si código 0361, consultar nuevamente cada 10 minutos
# Si código 0362, procesar resultados
```

---

## 📚 Referencias

1. **Guía de Mejores Prácticas**: "Recomendaciones y mejores prácticas para SIFEN - Guía para el desarrollador" (Octubre 2024)
2. **Manual Técnico v150**: Documentación técnica completa del formato XML
3. **Portal e-Kuatia**: https://ekuatia.set.gov.py
4. **XSD Schemas**: http://ekuatia.set.gov.py/sifen/xsd
5. **Prevalidador**: https://ekuatia.set.gov.py/prevalidador/

---

## ✅ Checklist de Implementación

- [x] Función `clean_xml()` actualizada con todas las reglas
- [x] Función `prepare_xml_for_sifen()` implementada
- [x] URLs de servicios SOAP actualizadas según guía oficial
- [x] Configuración de ambientes (test/prod) correcta
- [ ] Implementación cliente SOAP (usando zeep o similar)
- [ ] Función para generar lotes (agrupar hasta 50 DE)
- [ ] Función para codificar XML en Base64 para envío
- [ ] Manejo de códigos de respuesta según guía
- [ ] Reintentos y consultas automáticas de estado de lote

