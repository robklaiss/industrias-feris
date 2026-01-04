# Operaciones SOAP de SIFEN (excluyendo siRecepLoteDE)

Este documento lista todas las operaciones SOAP de SIFEN disponibles en el repositorio, excluyendo `siRecepLoteDE` (que ya está implementado).

---

## 1. siConsRUC - Consulta de RUC

**Propósito**: Verificar habilitación y estado de un RUC sin enviar un DE.

**WSDL URLs**:
- **Test**: `https://sifen-test.set.gov.py/de/ws/consultas/consulta-ruc.wsdl`
- **Prod**: `https://sifen.set.gov.py/de/ws/consultas/consulta-ruc.wsdl`

**Operación SOAP**: `siConsRUC`

**Request XML** (`rEnviConsRUC`):
```xml
<rEnviConsRUC xmlns="http://ekuatia.set.gov.py/sifen/xsd">
    <dId>202501151430257</dId>
    <dRUCCons>80012345</dRUCCons>
</rEnviConsRUC>
```

**Response XML** (`rResEnviConsRUC`):
```xml
<rResEnviConsRUC xmlns="http://ekuatia.set.gov.py/sifen/xsd">
    <dCodRes>0502</dCodRes>
    <dMsgRes>Éxito</dMsgRes>
    <xContRUC>
        <dRUCCons>80012345</dRUCCons>
        <dRazCons>Razón Social del Contribuyente</dRazCons>
        <dCodEstCons>001</dCodEstCons>
        <dDesEstCons>Activo</dDesEstCons>
        <dRUCFactElec>1</dRUCFactElec>  <!-- 1 = Habilitado para FE -->
    </xContRUC>
</rResEnviConsRUC>
```

**Códigos de respuesta**:
- `0500`: RUC inexistente
- `0501`: Sin permiso para consultar
- `0502`: Éxito (RUC encontrado)
- `0460`: Mensaje excede tamaño máximo (1000 KB)

**Función wrapper**: ❌ **NO IMPLEMENTADA**

**Estado**: Configurado en `app/sifen_client/config.py` pero sin función wrapper en `soap_client.py`.

**XSD disponible**: `schemas_sifen/WS_SiConsRUC_v141.xsd`

**Ejemplo de uso propuesto**:
```python
from app.sifen_client.config import get_sifen_config
from app.sifen_client.soap_client import SoapClient

config = get_sifen_config(env="test")
with SoapClient(config) as client:
    # TODO: Implementar consulta_ruc()
    result = client.consulta_ruc(ruc="80012345", did=1)
    # Retorna: {
    #     "dCodRes": "0502",
    #     "dMsgRes": "Éxito",
    #     "ruc": "80012345",
    #     "razon_social": "...",
    #     "estado": "001",
    #     "descripcion_estado": "Activo",
    #     "habilitado_facturacion_electronica": True
    # }
```

**Información retornada**:
- RUC consultado
- Razón social
- Código de estado (`dCodEstCons`)
- Descripción del estado (`dDesEstCons`)
- Habilitación para facturación electrónica (`dRUCFactElec`: "1" = habilitado, "0" = no habilitado)

**Nota**: Esta operación permite verificar si un RUC está habilitado para facturación electrónica **sin enviar un DE**.

---

## 2. siConsDE - Consulta de DE por CDC

**Propósito**: Consultar un Documento Electrónico específico por su CDC (Código de Control).

**WSDL URLs**:
- **Test**: `https://sifen-test.set.gov.py/de/ws/consultas/consulta.wsdl`
- **Prod**: `https://sifen.set.gov.py/de/ws/consultas/consulta.wsdl`

**Operación SOAP**: `rEnviConsDE` (directo en Body, sin wrapper)

**Request XML**:
```xml
<rEnviConsDE xmlns="http://ekuatia.set.gov.py/sifen/xsd">
    <dCDC>01234567890123456789012345678901234567890123</dCDC>
</rEnviConsDE>
```

**Response XML**:
```xml
<rResEnviConsDE xmlns="http://ekuatia.set.gov.py/sifen/xsd">
    <dCodRes>0422</dCodRes>
    <dMsgRes>CDC encontrado</dMsgRes>
    <dProtAut>1234567890</dProtAut>
    <xContDE>
        <!-- XML completo del DE -->
    </xContDE>
</rResEnviConsDE>
```

**Códigos de respuesta**:
- `0420`: DE no existe o no está aprobado
- `0422`: CDC encontrado (DE aprobado)
- `0424`: CDC no encontrado

**Función wrapper**: ✅ **IMPLEMENTADA**

**Archivo**: `app/sifen_client/soap_client.py`  
**Función**: `consulta_de_por_cdc_raw(cdc: str, dump_http: bool = False)` (línea 3086)

**Ejemplo de uso**:
```python
from app.sifen_client.config import get_sifen_config
from app.sifen_client.soap_client import SoapClient

config = get_sifen_config(env="test")
with SoapClient(config) as client:
    result = client.consulta_de_por_cdc_raw(
        cdc="01234567890123456789012345678901234567890123",
        dump_http=True
    )
    # Retorna: {
    #     "http_status": 200,
    #     "raw_xml": "...",
    #     "dCodRes": "0422",
    #     "dMsgRes": "CDC encontrado",
    #     "dProtAut": "1234567890",
    #     "sent_headers": {...},  # si dump_http=True
    #     "sent_xml": "...",      # si dump_http=True
    #     "received_headers": {...},  # si dump_http=True
    #     "received_body_preview": "..."  # si dump_http=True
    # }
```

**CLI disponible**: No hay CLI específico, pero se usa en `tools/consulta_lote_de.py` como fallback para `dCodResLot=0364`.

---

## 3. siConsLoteDE - Consulta de Lote

**Propósito**: Consultar el estado de procesamiento de un lote recibido.

**WSDL URLs**:
- **Test**: `https://sifen-test.set.gov.py/de/ws/consultas-lote/consulta-lote.wsdl`
- **Prod**: `https://sifen.set.gov.py/de/ws/consultas-lote/consulta-lote.wsdl`

**Operación SOAP**: `siConsLoteDE` (wrapper) → `rEnviConsLoteDe` (body)

**Request XML**:
```xml
<rEnviConsLoteDe xmlns="http://ekuatia.set.gov.py/sifen/xsd">
    <dId>202501151430257</dId>
    <dProtConsLote>1234567890</dProtConsLote>
</rEnviConsLoteDe>
```

**Response XML**:
```xml
<rResEnviConsLoteDe xmlns="http://ekuatia.set.gov.py/sifen/xsd">
    <dCodResLot>0362</dCodResLot>
    <dMsgResLot>Procesamiento concluido</dMsgResLot>
    <dEstRes>001</dEstRes>
    <!-- ... más campos ... -->
</rResEnviConsLoteDe>
```

**Códigos de respuesta**:
- `0360`: Número de lote inexistente
- `0361`: Lote en procesamiento
- `0362`: Procesamiento concluido
- `0364`: Consulta extemporánea (lote consultado después de 48 horas)

**Función wrapper**: ✅ **IMPLEMENTADA**

**Archivo**: `app/sifen_client/soap_client.py`  
**Funciones**:
- `consulta_lote_de(dprot_cons_lote: str, did: int = 1)` (línea 2564) - WSDL-driven con zeep
- `consulta_lote_raw(dprot_cons_lote: str, did: int = 1, dump_http: bool = False)` (línea 2945) - SOAP 1.2 manual

**Ejemplo de uso**:
```python
from app.sifen_client.config import get_sifen_config
from app.sifen_client.soap_client import SoapClient

config = get_sifen_config(env="test")
with SoapClient(config) as client:
    result = client.consulta_lote_raw(
        dprot_cons_lote="1234567890",
        did=1,
        dump_http=True
    )
```

**CLI disponible**: `tools/consulta_lote_de.py`
```bash
python -m tools.consulta_lote_de --env test --prot 1234567890 --dump-http
```

---

## 4. siRecepDE - Recepción Síncrona (Individual)

**Propósito**: Enviar un DE individual de forma síncrona (no por lote).

**WSDL URLs**:
- **Test**: `https://sifen-test.set.gov.py/de/ws/sync/recibe.wsdl`
- **Prod**: `https://sifen.set.gov.py/de/ws/sync/recibe.wsdl`

**Operación SOAP**: `siRecepDE`

**Función wrapper**: ❌ **NO IMPLEMENTADA**

**Estado**: Configurado en `app/sifen_client/config.py` pero sin función wrapper.

**Nota**: El repositorio usa principalmente `siRecepLoteDE` (recepción asíncrona por lotes), que es el método recomendado.

---

## 5. Evento - Eventos de DE

**Propósito**: Enviar eventos relacionados con DEs (anulaciones, etc.).

**WSDL URLs**:
- **Test**: `https://sifen-test.set.gov.py/de/ws/eventos/evento.wsdl`
- **Prod**: `https://sifen.set.gov.py/de/ws/eventos/evento.wsdl`

**Operación SOAP**: Desconocida (requiere inspección del WSDL)

**Función wrapper**: ❌ **NO IMPLEMENTADA**

**Estado**: Configurado en `app/sifen_client/config.py` pero sin función wrapper.

---

## Resumen de Implementación

| Operación | WSDL Configurado | Función Wrapper | CLI Disponible | Verifica Habilitación |
|-----------|------------------|-----------------|----------------|----------------------|
| **siConsRUC** | ✅ | ❌ | ❌ | ✅ **SÍ** (RUC habilitado para FE) |
| **siConsDE** | ✅ | ✅ | ⚠️ (fallback) | ❌ |
| **siConsLoteDE** | ✅ | ✅ | ✅ | ❌ |
| **siRecepDE** | ✅ | ❌ | ❌ | ❌ |
| **Evento** | ✅ | ❌ | ❌ | ❌ |

---

## Recomendación para Verificar Habilitación

**Para verificar habilitación sin enviar un DE, usar `siConsRUC`**:

### Ventajas:
1. ✅ No requiere enviar un DE
2. ✅ Retorna información del RUC:
   - Estado del contribuyente
   - Habilitación para facturación electrónica (`dRUCFactElec`)
   - Razón social
3. ✅ Operación de solo lectura (no modifica estado)

### Limitaciones:
- ❌ **NO IMPLEMENTADA** en el repositorio actual
- ⚠️ Solo verifica RUC, no timbrado/establecimiento/punto específicos

### Implementación Propuesta:

```python
# app/sifen_client/soap_client.py

def consulta_ruc(self, ruc: str, did: Optional[int] = None, dump_http: bool = False) -> Dict[str, Any]:
    """
    Consulta estado y habilitación de un RUC (siConsRUC).
    
    Args:
        ruc: RUC a consultar (sin DV, solo números)
        did: dId opcional (si None, se genera automáticamente)
        dump_http: Si True, retorna también sent_headers y sent_xml
        
    Returns:
        Dict con:
        - dCodRes: Código de respuesta
        - dMsgRes: Mensaje de respuesta
        - ruc: RUC consultado
        - razon_social: Razón social (si dCodRes=0502)
        - estado_codigo: Código de estado (si dCodRes=0502)
        - estado_descripcion: Descripción del estado (si dCodRes=0502)
        - habilitado_fe: True si está habilitado para FE (si dCodRes=0502)
    """
    # Construir SOAP 1.2 con rEnviConsRUC
    # POST a consulta-ruc.wsdl
    # Parsear rResEnviConsRUC
    # Retornar dict estructurado
```

### Ejemplo de Uso Propuesto:

```python
from app.sifen_client.config import get_sifen_config
from app.sifen_client.soap_client import SoapClient

config = get_sifen_config(env="test")
with SoapClient(config) as client:
    result = client.consulta_ruc(ruc="80012345")
    
    if result["dCodRes"] == "0502":
        print(f"RUC: {result['ruc']}")
        print(f"Razón Social: {result['razon_social']}")
        print(f"Estado: {result['estado_descripcion']}")
        print(f"Habilitado para FE: {result['habilitado_fe']}")
    elif result["dCodRes"] == "0500":
        print("RUC inexistente")
    elif result["dCodRes"] == "0501":
        print("Sin permiso para consultar")
```

---

## Notas sobre Verificación de Timbrado/Establecimiento/Punto

**⚠️ IMPORTANTE**: No se encontró una operación SOAP específica para verificar:
- Timbrado habilitado
- Establecimiento válido
- Punto de expedición válido

**Alternativas**:
1. **Usar `siConsRUC`** para verificar que el RUC está habilitado para FE
2. **Enviar un DE de prueba** (con `siRecepLoteDE`) y verificar la respuesta
3. **Consultar documentación oficial** para ver si existe una operación de consulta de timbrado

---

## Referencias

- **Configuración**: `app/sifen_client/config.py` (líneas 104-121)
- **Cliente SOAP**: `app/sifen_client/soap_client.py`
- **XSD siConsRUC**: `schemas_sifen/WS_SiConsRUC_v141.xsd`
- **Documentación SIFEN**: `docs/SIFEN_BEST_PRACTICES.md`

---

**Última actualización**: 2025-01-XX

