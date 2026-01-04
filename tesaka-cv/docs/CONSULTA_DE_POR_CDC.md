# Consulta de DE por CDC (siConsDE / rEnviConsDE)

Este documento detalla cómo consultar el estado de un Documento Electrónico (DE) por su CDC (Código de Control), sin necesidad de `dProtConsLote`.

---

## 📋 Resumen

**Operación SOAP**: `rEnviConsDE` (directo en Body, sin wrapper)  
**Propósito**: Consultar un DE específico por su CDC (Código de Control)  
**Estado**: ✅ **IMPLEMENTADO**

---

## 🔧 Función Wrapper

**Archivo**: `app/sifen_client/soap_client.py`  
**Función**: `consulta_de_por_cdc_raw(cdc: str, dump_http: bool = False)` (línea 3086)

**Firma**:
```python
def consulta_de_por_cdc_raw(self, cdc: str, dump_http: bool = False) -> Dict[str, Any]:
    """Consulta estado de un DE individual por CDC (sin depender del WSDL).
    
    Args:
        cdc: CDC (Código de Control) del documento electrónico
        dump_http: Si True, retorna también sent_headers y sent_xml para debug
        
    Returns:
        Dict con http_status, raw_xml, y opcionalmente dCodRes/dMsgRes/dProtAut.
        Si dump_http=True, también incluye sent_headers y sent_xml.
    """
```

---

## 🌐 WSDL URLs

**Test**:
- `https://sifen-test.set.gov.py/de/ws/consultas/consulta-de.wsdl` (usado en `soap_client.py` línea 3129)
- `https://sifen-test.set.gov.py/de/ws/consultas/consulta.wsdl` (configurado en `config.py` línea 111)

**Prod**:
- `https://sifen.set.gov.py/de/ws/consultas/consulta-de.wsdl` (usado en `soap_client.py` línea 3131)
- `https://sifen.set.gov.py/de/ws/consultas/consulta.wsdl` (configurado en `config.py` línea 119)

**⚠️ Nota**: Hay una inconsistencia entre `config.py` (`consulta.wsdl`) y `soap_client.py` (`consulta-de.wsdl`). El código actual usa `consulta-de.wsdl`.

---

## 📤 Request SOAP

### Estructura XML

**SOAP 1.2 Envelope**:
```xml
<?xml version="1.0" encoding="UTF-8"?>
<soap:Envelope xmlns:soap="http://www.w3.org/2003/05/soap-envelope">
    <soap:Header/>
    <soap:Body>
        <rEnviConsDE xmlns="http://ekuatia.set.gov.py/sifen/xsd">
            <dCDC>01234567890123456789012345678901234567890123</dCDC>
        </rEnviConsDE>
    </soap:Body>
</soap:Envelope>
```

### Características del Request

1. **SOAP 1.2**: Namespace `http://www.w3.org/2003/05/soap-envelope`
2. **Body directo**: `rEnviConsDE` va directamente en `Body`, sin wrapper
3. **Default namespace**: `rEnviConsDE` usa `xmlns="http://ekuatia.set.gov.py/sifen/xsd"` como default
4. **Sin dId**: **IMPORTANTE**: El request actual **NO incluye `dId`**, solo `dCDC`
   - ⚠️ **Nota**: El XSD (`WS_SiConsDE_v141.xsd`) define `rEnviConsDeRequest` con `dId` y `dCDC`, pero la implementación actual solo envía `dCDC`

### Headers HTTP

```http
Content-Type: application/soap+xml; charset=utf-8; action="rEnviConsDE"
Accept: application/soap+xml
```

**Nota**: NO se envía header `SOAPAction` separado (SOAP 1.2).

### Código de Construcción

```python
# app/sifen_client/soap_client.py (líneas 3099-3125)

SOAP_12_NS = "http://www.w3.org/2003/05/soap-envelope"

# Envelope SOAP 1.2
envelope = etree.Element(
    f"{{{SOAP_12_NS}}}Envelope",
    nsmap={"soap": SOAP_12_NS}
)

# Header vacío
header = etree.SubElement(envelope, f"{{{SOAP_12_NS}}}Header")

# Body
body = etree.SubElement(envelope, f"{{{SOAP_12_NS}}}Body")

# rEnviConsDE directamente en Body con namespace default
r_envi_cons_de = etree.SubElement(
    body, "rEnviConsDE", nsmap={None: SIFEN_NS}
)

# dCDC sin prefijo (unqualified, hereda el default namespace)
d_cdc_elem = etree.SubElement(r_envi_cons_de, "dCDC")
d_cdc_elem.text = str(cdc)

soap_bytes = etree.tostring(
    envelope, xml_declaration=True, encoding="UTF-8", pretty_print=False
)
```

---

## 📥 Response SOAP

### Estructura XML Esperada

```xml
<?xml version="1.0" encoding="UTF-8"?>
<soap:Envelope xmlns:soap="http://www.w3.org/2003/05/soap-envelope">
    <soap:Body>
        <rResEnviConsDE xmlns="http://ekuatia.set.gov.py/sifen/xsd">
            <dFecProc>2025-01-15T14:30:25-04:00</dFecProc>
            <dCodRes>0422</dCodRes>
            <dMsgRes>CDC encontrado</dMsgRes>
            <dProtAut>1234567890</dProtAut>
            <xContenDE>
                <!-- XML completo del DE (base64 o XML directo) -->
            </xContenDE>
        </rResEnviConsDE>
    </soap:Body>
</soap:Envelope>
```

### Campos de Respuesta

| Campo | Tipo | Descripción | Ocurrencia |
|-------|------|-------------|------------|
| `dFecProc` | `fecUTC` | Fecha de procesamiento | Requerido |
| `dCodRes` | `string(4)` | Código del resultado | Requerido |
| `dMsgRes` | `string(1-255)` | Mensaje del resultado | Requerido |
| `dProtAut` | `string` | Protocolo de autorización | Opcional |
| `xContenDE` | `string` | Contenedor del DE (XML completo) | Opcional |

### Códigos de Respuesta (dCodRes)

| Código | Significado | Acción |
|--------|-------------|--------|
| `0420` | DE no existe o no está aprobado | Verificar CDC o estado del DE |
| `0422` | CDC encontrado (DE aprobado) | ✅ DE válido, usar `dProtAut` y `xContenDE` |
| `0424` | CDC no encontrado | Verificar que el CDC sea correcto |

**Nota**: En `consulta_lote_de.py` (líneas 1519-1524), se mapean códigos adicionales:
- `0200`, `0300` → "Aprobado"
- `0201`, `0301` → "Rechazado"
- Otros → "En proceso"

### Código de Parsing

```python
# app/sifen_client/soap_client.py (líneas 3183-3196)

resp_root = etree.fromstring(resp.content)
cod_res = resp_root.find(".//{http://ekuatia.set.gov.py/sifen/xsd}dCodRes")
msg_res = resp_root.find(".//{http://ekuatia.set.gov.py/sifen/xsd}dMsgRes")
prot_aut = resp_root.find(".//{http://ekuatia.set.gov.py/sifen/xsd}dProtAut")

if cod_res is not None and cod_res.text:
    result["dCodRes"] = cod_res.text.strip()
if msg_res is not None and msg_res.text:
    result["dMsgRes"] = msg_res.text.strip()
if prot_aut is not None and prot_aut.text:
    result["dProtAut"] = prot_aut.text.strip()
```

---

## 📊 Estructura de Retorno

### Dict Retornado

```python
{
    "http_status": 200,  # Status code HTTP
    "raw_xml": "...",    # XML completo de la respuesta
    
    # Campos parseados (si están disponibles):
    "dCodRes": "0422",           # Código de respuesta
    "dMsgRes": "CDC encontrado", # Mensaje de respuesta
    "dProtAut": "1234567890",    # Protocolo de autorización (opcional)
    
    # Si dump_http=True, también incluye:
    "sent_headers": {...},           # Headers HTTP enviados
    "sent_xml": "...",               # XML SOAP enviado
    "received_headers": {...},       # Headers HTTP recibidos
    "received_body_preview": "..."   # Preview del body recibido (primeras 500 líneas)
}
```

---

## 💻 Ejemplo de Uso

### Python (SoapClient)

```python
from app.sifen_client.config import get_sifen_config
from app.sifen_client.soap_client import SoapClient

config = get_sifen_config(env="test")
with SoapClient(config) as client:
    result = client.consulta_de_por_cdc_raw(
        cdc="01234567890123456789012345678901234567890123",
        dump_http=True
    )
    
    print(f"HTTP Status: {result['http_status']}")
    print(f"dCodRes: {result.get('dCodRes', 'N/A')}")
    print(f"dMsgRes: {result.get('dMsgRes', 'N/A')}")
    print(f"dProtAut: {result.get('dProtAut', 'N/A')}")
    
    if result.get('dCodRes') == '0422':
        print("✅ DE encontrado y aprobado")
        # El XML completo del DE está en result['raw_xml']
        # Buscar <xContenDE> para extraer el DE
```

### Uso en Fallback Automático

**Archivo**: `tools/consulta_lote_de.py` (líneas 1506-1540)

Se usa automáticamente cuando `dCodResLot=0364` (lote fuera de ventana de 48h):

```python
# Si dCodResLot == "0364", consultar cada CDC individualmente
cdcs = get_cdcs_for_lote(dprot_cons_lote, artifacts_dir, debug=True)

for cdc in cdcs:
    cdc_result = client.consulta_de_por_cdc_raw(cdc)
    
    cdc_cod_res = cdc_result.get("dCodRes", "N/A")
    cdc_msg_res = cdc_result.get("dMsgRes", "N/A")
    cdc_prot_aut = cdc_result.get("dProtAut", None)
    
    # Determinar estado
    if cdc_cod_res in ("0200", "0300"):
        estado = "Aprobado"
    elif cdc_cod_res in ("0201", "0301"):
        estado = "Rechazado"
    else:
        estado = "En proceso"
```

---

## 📁 XSD de Referencia

**Archivo**: `schemas_sifen/WS_SiConsDE_v141.xsd`

### Request (según XSD)

```xml
<rEnviConsDeRequest>
    <dId>...</dId>      <!-- Tipo: dIdType -->
    <dCDC>...</dCDC>    <!-- Tipo: tCDC -->
</rEnviConsDeRequest>
```

**⚠️ Nota**: El XSD define `rEnviConsDeRequest` con `dId` y `dCDC`, pero la implementación actual solo envía `dCDC` (sin `dId`). Esto puede ser una diferencia entre v141 (XSD) y v150 (implementación actual).

### Response (según XSD)

```xml
<rEnviConsDeResponse>
    <dFecProc>...</dFecProc>      <!-- Tipo: fecUTC -->
    <dCodRes>...</dCodRes>         <!-- Tipo: string(4) -->
    <dMsgRes>...</dMsgRes>         <!-- Tipo: string(1-255) -->
    <xContenDE>...</xContenDE>     <!-- Tipo: string (opcional) -->
</rEnviConsDeResponse>
```

**Nota**: El XSD no define `dProtAut` en la respuesta, pero la implementación actual lo busca y parsea. Esto puede ser una diferencia entre v141 (XSD) y v150 (implementación actual).

---

## 🔍 Uso en el Repositorio

### 1. Función Principal

**Archivo**: `app/sifen_client/soap_client.py`  
**Línea**: 3086  
**Función**: `consulta_de_por_cdc_raw()`

### 2. Fallback Automático

**Archivo**: `tools/consulta_lote_de.py`  
**Línea**: 1509  
**Contexto**: Se usa cuando `dCodResLot=0364` (lote fuera de ventana de 48h)

### 3. TODO en Web

**Archivo**: `web/main.py`  
**Línea**: 1173  
**Estado**: `# TODO: Implementar consulta directa por CDC (siConsDE)`

### 4. Referencias en Documentación

- `docs/OPERACIONES_SOAP_SIFEN.md` (líneas 83-150)
- `docs/URLS_SIFEN_AGRUPADAS.md` (líneas 106-137)
- `docs/SIFEN_BEST_PRACTICES.md` (líneas 40-44)

---

## ⚠️ Diferencias con XSD

### 1. Request sin `dId`

- **XSD**: Define `rEnviConsDeRequest` con `dId` y `dCDC`
- **Implementación**: Solo envía `dCDC` (sin `dId`)

**Posible razón**: La implementación actual puede estar usando una versión más reciente del protocolo (v150) donde `dId` no es requerido, o puede ser un error.

### 2. Response con `dProtAut`

- **XSD**: No define `dProtAut` en `rEnviConsDeResponse`
- **Implementación**: Busca y parsea `dProtAut` de la respuesta

**Posible razón**: `dProtAut` puede ser un campo agregado en v150 o puede estar en un namespace diferente.

### 3. Nombre del Elemento

- **XSD**: `rEnviConsDeRequest` / `rEnviConsDeResponse`
- **Implementación**: `rEnviConsDE` (sin "Request"/"Response")

**Posible razón**: En SOAP 1.2, el elemento en Body puede tener un nombre diferente al definido en el XSD del tipo.

---

## 🎯 Casos de Uso

### 1. Consulta Directa por CDC

Cuando se tiene el CDC de un DE y se quiere verificar su estado sin conocer el `dProtConsLote`:

```python
result = client.consulta_de_por_cdc_raw(cdc="0123456789...")
if result.get("dCodRes") == "0422":
    print(f"DE aprobado, protocolo: {result.get('dProtAut')}")
```

### 2. Fallback para Lote Fuera de Ventana

Cuando un lote fue consultado después de 48 horas (`dCodResLot=0364`), se consulta cada DE individualmente:

```python
# En tools/consulta_lote_de.py
if codigo_respuesta == "0364":
    cdcs = get_cdcs_for_lote(dprot_cons_lote, artifacts_dir)
    for cdc in cdcs:
        result = client.consulta_de_por_cdc_raw(cdc)
        # Procesar resultado individual
```

### 3. Verificación de Estado sin Lote

Útil cuando:
- No se guardó el `dProtConsLote`
- Se quiere verificar el estado de un DE específico
- El lote ya no está disponible para consulta

---

## 📝 Notas Importantes

1. **No requiere `dProtConsLote`**: Esta operación consulta directamente por CDC, sin necesidad de conocer el número de lote.

2. **Útil para fallback**: Cuando `dCodResLot=0364` (lote fuera de ventana), esta es la única forma de consultar el estado de los DEs.

3. **Retorna XML completo del DE**: Si `dCodRes=0422`, el campo `xContenDE` contiene el XML completo del DE aprobado.

4. **Protocolo de autorización**: Si el DE está aprobado, `dProtAut` contiene el protocolo de autorización.

5. **Inconsistencia en URLs**: Hay una diferencia entre `config.py` (`consulta.wsdl`) y `soap_client.py` (`consulta-de.wsdl`). El código actual usa `consulta-de.wsdl`.

---

## 🔗 Referencias

- **XSD**: `schemas_sifen/WS_SiConsDE_v141.xsd`
- **Función**: `app/sifen_client/soap_client.py::consulta_de_por_cdc_raw()` (línea 3086)
- **Uso en fallback**: `tools/consulta_lote_de.py` (línea 1509)
- **Documentación**: `docs/OPERACIONES_SOAP_SIFEN.md`

---

**Última actualización**: 2025-01-XX

