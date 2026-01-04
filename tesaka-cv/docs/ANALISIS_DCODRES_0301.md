# Análisis: Manejo de dCodRes=0301 y Centralización de Política

## Resumen Ejecutivo

Este documento identifica todos los lugares donde se maneja `dCodRes=0301` y otros códigos de respuesta SIFEN, y propone un lugar único para centralizar la política de manejo (no reintentar, cooldown, logging).

---

## 1. COINCIDENCIAS ENCONTRADAS

### 1.1 Manejo Explícito de `dCodRes == "0301"`

#### 1.1.1 `web/sifen_status_mapper.py` (Líneas 72-74)
```python
# Si dCodRes != "0300" (ej 0301) o dProtConsLote == 0: ERROR/RECHAZADO
if codigo != "0300" or (d_prot_int is not None and d_prot_int == 0):
    # Mensaje específico para 0301
    if codigo == "0301":
        error_msg = mensaje or "Lote no encolado para procesamiento"
        return STATUS_ERROR, codigo, error_msg
    else:
        # Otro código de error
        return STATUS_ERROR, codigo, mensaje or "Error en recepción"
```

**Contexto completo** (líneas 33-88):
- Función: `map_recepcion_response_to_status()`
- Propósito: Mapea respuesta de recepción a estado de documento
- Acción: Retorna `STATUS_ERROR` con mensaje específico para 0301
- **NO hay lógica de reintento ni cooldown**

#### 1.1.2 `tools/send_sirecepde.py` (Líneas 4388-4394)
```python
# Advertencia para dCodRes=0301 con dProtConsLote=0
if codigo_respuesta == "0301":
    d_prot_cons_lote_val = response.get('d_prot_cons_lote')
    if d_prot_cons_lote_val is None or d_prot_cons_lote_val == 0 or str(d_prot_cons_lote_val) == "0":
        print(f"\n⚠️  ADVERTENCIA: SIFEN no encoló el lote (dCodRes=0301, dProtConsLote=0)")
        print(f"   Si estás re-enviando el mismo CDC, SIFEN puede no re-procesarlo.")
        print(f"   Generá un nuevo CDC (ej: cambiar nro factura y recalcular CDC/DV) para probar cambios.")
```

**Contexto completo** (líneas 4328-4400):
- Función: `send_sirecepde()` (CLI)
- Propósito: Imprime advertencia al usuario
- Acción: Solo logging/print, no bloquea ni reintenta
- **NO hay lógica de reintento ni cooldown**

#### 1.1.3 `web/document_status.py` (Línea 44)
```python
RECEPCION_ERROR_CODES = ["0301"]  # Lote no encolado
```

**Contexto completo** (líneas 40-49):
- Constante de módulo
- Propósito: Lista de códigos de error de recepción
- Uso: Referencia/documentación, no se usa en lógica activa

#### 1.1.4 `app/sifen_client/soap_client.py` (Línea 1372)
```python
codigo = (result.get("codigo_respuesta") or "").strip()
result["ok"] = codigo in ("0200", "0300", "0301", "0302")
```

**Contexto completo** (líneas 1334-1374):
- Función: `_parse_recepcion_response_from_xml()`
- Propósito: Parsea respuesta XML y determina si es "ok"
- Acción: Marca 0301 como "ok" (solo indica que es una respuesta válida, no éxito)
- **NO hay lógica de reintento ni cooldown**

#### 1.1.5 `tools/consulta_lote_de.py` (Líneas 1521-1522)
```python
elif cdc_cod_res in ("0201", "0301"):
    estado = "Rechazado"
```

**Contexto completo** (líneas 1518-1524):
- Función: Dentro de fallback automático por CDC (cuando `dCodResLot=0364`)
- Propósito: Determina estado de un DE individual consultado por CDC
- Acción: Marca como "Rechazado" si el código es 0201 o 0301
- **NO hay lógica de reintento ni cooldown**

---

### 1.2 Manejo de Otros Códigos de Respuesta

#### 1.2.1 `dCodRes == "0300"` (Éxito)
**Archivo**: `web/sifen_status_mapper.py` (Línea 66)
```python
# Si dCodRes == "0300" y dProtConsLote > 0: ENVIADO/ENCOLADO
if codigo == "0300" and d_prot_int and d_prot_int > 0:
    return STATUS_SENT_TO_SIFEN, codigo, mensaje or "Lote recibido por SIFEN"
```

#### 1.2.2 `dCodRes == "0160"` (XML Mal Formado)
**Archivo**: `app/sifen_client/soap_client.py` (Líneas 2740-2745)
```python
elif codigo == "0160":
    # XML Mal Formado: no reintentar, devolver error inmediato
    error_msg = f"Error 0160 (XML Mal Formado) en consulta lote. Mensaje: {parsed_result.get('mensaje', 'N/A')}"
    if debug_enabled:
        error_msg += f"\nResponse guardado en artifacts/consulta_last_response.xml"
    raise SifenClientError(error_msg)
```

**Contexto**: Función `consulta_lote_raw()` - **NO reintenta** con 0160

#### 1.2.3 `dCodRes == "1264"` (RUC inválido)
**Archivo**: `tools/send_sirecepde.py` (Línea 4424)
```python
if codigo_respuesta == "1264" and artifacts_dir:
    # Manejo específico para RUC inválido
```

---

### 1.3 Strings de Mensajes Relacionados

#### 1.3.1 "Lote no encolado"
**Archivo**: `web/sifen_status_mapper.py` (Línea 73)
```python
error_msg = mensaje or "Lote no encolado para procesamiento"
```

**Archivo**: `tools/send_sirecepde.py` (Línea 4392)
```python
print(f"\n⚠️  ADVERTENCIA: SIFEN no encoló el lote (dCodRes=0301, dProtConsLote=0)")
```

**Archivo**: `docs/SIFEN_BEST_PRACTICES.md` (Línea 121)
```markdown
| `0301` | Lote no encolado | El lote NO será procesado. Verificar motivos de rechazo/bloqueo |
```

---

### 1.4 Lógica de Reintento Existente

#### 1.4.1 Reintento por `ConnectionResetError`
**Archivo**: `app/sifen_client/soap_client.py` (Líneas 2751-2760)
```python
except ConnectionResetError as e:
    # Reintentar solo para ConnectionResetError (máximo 2 veces)
    delays = [0.4, 0.8]
    last_exception = e
    for attempt in range(2):
        try:
            time.sleep(delays[attempt] if attempt < len(delays) else delays[-1])
            logger.debug(f"ConnectionResetError en consulta lote, reintentando {attempt + 1}/2...")
            # Reintentar la llamada
```

**Contexto**: Solo para errores de conexión, NO para códigos de respuesta SIFEN

#### 1.4.2 Retry con urllib3 (consulta_lote_de.py)
**Archivo**: `tools/consulta_lote_de.py` (Líneas 861-871)
```python
if URLLIB3_RETRY_AVAILABLE:
    retry = Retry(
        total=3,
        backoff_factor=0.5,
        status_forcelist=[500, 502, 503, 504],
    )
    adapter = HTTPAdapter(max_retries=retry, pool_connections=10, pool_maxsize=10)
```

**Contexto**: Solo para errores HTTP 5xx, NO para códigos de respuesta SIFEN

---

## 2. PROBLEMAS IDENTIFICADOS

### 2.1 Dispersión de Lógica
- **5 lugares diferentes** manejan `dCodRes=0301` de forma independiente
- No hay política centralizada de:
  - **No reintentar** con 0301
  - **Cooldown** antes de reintentar (si se implementa en el futuro)
  - **Logging estructurado** de errores 0301

### 2.2 Falta de Consistencia
- `soap_client.py` marca 0301 como "ok" (línea 1372) pero no es éxito real
- `sifen_status_mapper.py` retorna `STATUS_ERROR` para 0301 (correcto)
- `send_sirecepde.py` solo imprime advertencia (no bloquea)

### 2.3 Sin Política de Reintento
- **NO hay lógica** que evite reintentar automáticamente con 0301
- Si un usuario/envío automático reintenta, puede generar spam a SIFEN
- No hay cooldown ni backoff exponencial

### 2.4 Logging Inconsistente
- Algunos lugares usan `print()`, otros no loguean
- No hay logging estructurado (nivel, contexto, métricas)

---

## 3. PROPUESTA: CENTRALIZACIÓN

### 3.1 Nuevo Módulo: `app/sifen_client/response_policy.py`

**Ubicación**: `tesaka-cv/app/sifen_client/response_policy.py`

**Propósito**: Centralizar toda la política de manejo de códigos de respuesta SIFEN

**Funcionalidades**:
1. **Definición de códigos** (constantes)
2. **Política de reintento** (qué códigos NO reintentar)
3. **Cooldown/backoff** (si se implementa reintento)
4. **Logging estructurado** (nivel, contexto, métricas)

### 3.2 Estructura Propuesta

```python
"""
Política centralizada para manejo de códigos de respuesta SIFEN.

Este módulo centraliza:
- Definición de códigos de respuesta
- Política de reintento (qué códigos NO reintentar)
- Cooldown/backoff (si se implementa reintento)
- Logging estructurado
"""

from typing import Dict, Optional, Tuple, List
from enum import Enum
import logging
import time
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)


class SifenResponseCode(Enum):
    """Códigos de respuesta SIFEN organizados por categoría."""
    
    # Recepción (siRecepLoteDE / siRecepDE)
    RECEPCION_OK = "0300"  # Lote recibido con éxito
    RECEPCION_NO_ENCOLADO = "0301"  # Lote no encolado (NO reintentar)
    RECEPCION_EN_PROCESO = "0302"  # En proceso
    
    # Consulta Lote (siConsLoteDE)
    CONSULTA_LOTE_PENDING = "0361"  # Lote en procesamiento
    CONSULTA_LOTE_DONE = "0362"  # Procesamiento concluido
    CONSULTA_LOTE_NOT_FOUND = "0360"  # Lote inexistente
    CONSULTA_LOTE_EXTRANEOUS = "0364"  # Consulta extemporánea
    
    # Errores críticos (NO reintentar)
    XML_MAL_FORMADO = "0160"  # XML Mal Formado (NO reintentar)
    RUC_INVALIDO = "1264"  # RUC inválido (NO reintentar)
    
    # DE individual (consulta por CDC)
    DE_APROBADO = "0200"  # DE aprobado
    DE_RECHAZADO = "0201"  # DE rechazado


class RetryPolicy:
    """Política de reintento para códigos de respuesta SIFEN."""
    
    # Códigos que NO deben reintentarse (hard fail)
    NO_RETRY_CODES: List[str] = [
        SifenResponseCode.RECEPCION_NO_ENCOLADO.value,  # 0301
        SifenResponseCode.XML_MAL_FORMADO.value,  # 0160
        SifenResponseCode.RUC_INVALIDO.value,  # 1264
    ]
    
    # Códigos que pueden reintentarse (con cooldown)
    RETRYABLE_CODES: List[str] = [
        SifenResponseCode.CONSULTA_LOTE_PENDING.value,  # 0361 (esperar y consultar de nuevo)
    ]
    
    @classmethod
    def should_retry(cls, codigo: Optional[str], attempt: int = 0, max_attempts: int = 3) -> Tuple[bool, Optional[float]]:
        """
        Determina si se debe reintentar basado en el código de respuesta.
        
        Args:
            codigo: Código de respuesta SIFEN (ej: "0301", "0160")
            attempt: Número de intento actual (0-indexed)
            max_attempts: Número máximo de intentos permitidos
            
        Returns:
            Tupla (should_retry, cooldown_seconds)
            - should_retry: True si se debe reintentar
            - cooldown_seconds: Segundos a esperar antes de reintentar (None si no reintentar)
        """
        if not codigo:
            return False, None
        
        codigo = codigo.strip()
        
        # Hard fail: NO reintentar
        if codigo in cls.NO_RETRY_CODES:
            return False, None
        
        # Ya se alcanzó el máximo de intentos
        if attempt >= max_attempts:
            return False, None
        
        # Retryable: calcular cooldown exponencial
        if codigo in cls.RETRYABLE_CODES:
            # Backoff exponencial: 10s, 20s, 40s
            cooldown = 10 * (2 ** attempt)
            return True, cooldown
        
        # Por defecto: NO reintentar (código desconocido)
        return False, None


class ResponseMessage:
    """Mensajes estándar para códigos de respuesta SIFEN."""
    
    MESSAGES: Dict[str, str] = {
        SifenResponseCode.RECEPCION_OK.value: "Lote recibido por SIFEN",
        SifenResponseCode.RECEPCION_NO_ENCOLADO.value: "Lote no encolado para procesamiento",
        SifenResponseCode.XML_MAL_FORMADO.value: "XML Mal Formado",
        SifenResponseCode.RUC_INVALIDO.value: "RUC inválido",
        SifenResponseCode.CONSULTA_LOTE_PENDING.value: "Lote en procesamiento",
        SifenResponseCode.CONSULTA_LOTE_DONE.value: "Procesamiento concluido",
        SifenResponseCode.CONSULTA_LOTE_NOT_FOUND.value: "Lote inexistente",
        SifenResponseCode.CONSULTA_LOTE_EXTRANEOUS.value: "Consulta extemporánea (más de 48h)",
    }
    
    @classmethod
    def get_message(cls, codigo: Optional[str], default: Optional[str] = None) -> str:
        """Obtiene mensaje estándar para un código de respuesta."""
        if not codigo:
            return default or "Código de respuesta no disponible"
        codigo = codigo.strip()
        return cls.MESSAGES.get(codigo, default or f"Error {codigo}")


class ResponseLogger:
    """Logger estructurado para códigos de respuesta SIFEN."""
    
    @staticmethod
    def log_recepcion_response(
        codigo: Optional[str],
        mensaje: Optional[str],
        d_prot_cons_lote: Optional[str],
        operation: str = "siRecepLoteDE",
        extra_context: Optional[Dict] = None
    ):
        """
        Log estructurado para respuesta de recepción.
        
        Args:
            codigo: Código de respuesta (ej: "0301")
            mensaje: Mensaje de respuesta
            d_prot_cons_lote: Protocolo de consulta de lote
            operation: Operación SOAP (siRecepLoteDE, siRecepDE)
            extra_context: Contexto adicional (dId, timestamp, etc.)
        """
        extra = extra_context or {}
        extra.update({
            "sifen_code": codigo,
            "sifen_message": mensaje,
            "d_prot_cons_lote": d_prot_cons_lote,
            "operation": operation,
        })
        
        # Determinar nivel de log
        if codigo == SifenResponseCode.RECEPCION_NO_ENCOLADO.value:
            # 0301: ERROR (no encolado)
            logger.error(
                f"SIFEN {operation}: Lote no encolado (dCodRes=0301, dProtConsLote={d_prot_cons_lote})",
                extra=extra
            )
        elif codigo == SifenResponseCode.RECEPCION_OK.value and d_prot_cons_lote:
            # 0300 con protocolo: INFO (éxito)
            logger.info(
                f"SIFEN {operation}: Lote recibido (dCodRes=0300, dProtConsLote={d_prot_cons_lote})",
                extra=extra
            )
        elif codigo == SifenResponseCode.RECEPCION_OK.value:
            # 0300 sin protocolo: WARNING (modo directo)
            logger.warning(
                f"SIFEN {operation}: DE recibido sin protocolo (dCodRes=0300)",
                extra=extra
            )
        else:
            # Otro código: WARNING
            logger.warning(
                f"SIFEN {operation}: Respuesta inesperada (dCodRes={codigo})",
                extra=extra
            )
    
    @staticmethod
    def log_no_retry(codigo: str, reason: str, context: Optional[Dict] = None):
        """Log cuando se decide NO reintentar."""
        extra = context or {}
        extra.update({
            "sifen_code": codigo,
            "no_retry_reason": reason,
        })
        logger.warning(
            f"SIFEN: NO se reintentará (dCodRes={codigo}, razón: {reason})",
            extra=extra
        )


# Funciones de conveniencia para uso en otros módulos

def should_retry_recepcion(codigo: Optional[str], attempt: int = 0) -> Tuple[bool, Optional[float]]:
    """
    Determina si se debe reintentar una recepción basado en dCodRes.
    
    IMPORTANTE: Para dCodRes=0301, siempre retorna (False, None) (NO reintentar).
    
    Args:
        codigo: Código de respuesta (ej: "0301")
        attempt: Número de intento actual
        
    Returns:
        Tupla (should_retry, cooldown_seconds)
    """
    return RetryPolicy.should_retry(codigo, attempt, max_attempts=0)  # Recepción: no reintentar por defecto


def get_recepcion_message(codigo: Optional[str], mensaje_sifen: Optional[str] = None) -> str:
    """Obtiene mensaje estándar para código de recepción."""
    return ResponseMessage.get_message(codigo, default=mensaje_sifen)
```

---

## 4. MIGRACIÓN PROPUESTA

### 4.1 Archivos a Modificar

1. **`web/sifen_status_mapper.py`**:
   - Importar `get_recepcion_message()` y `ResponseLogger`
   - Reemplazar mensaje hardcodeado por `get_recepcion_message("0301")`
   - Agregar logging estructurado

2. **`tools/send_sirecepde.py`**:
   - Importar `should_retry_recepcion()` y `ResponseLogger`
   - Reemplazar print por `ResponseLogger.log_recepcion_response()`
   - Agregar check de reintento (aunque por ahora siempre retorne False)

3. **`app/sifen_client/soap_client.py`**:
   - Importar `RetryPolicy.NO_RETRY_CODES`
   - Verificar antes de marcar como "ok" si el código está en NO_RETRY_CODES

4. **`web/main.py`**:
   - Importar `should_retry_recepcion()` y `ResponseLogger`
   - Agregar check de reintento antes de guardar en BD
   - Agregar logging estructurado

### 4.2 Orden de Implementación

1. **Fase 1**: Crear `response_policy.py` con estructura básica
2. **Fase 2**: Migrar `sifen_status_mapper.py` (mensajes y logging)
3. **Fase 3**: Migrar `send_sirecepde.py` (logging)
4. **Fase 4**: Migrar `soap_client.py` (verificación de NO_RETRY_CODES)
5. **Fase 5**: Migrar `main.py` (check de reintento y logging)

---

## 5. BENEFICIOS

### 5.1 Centralización
- **Un solo lugar** para definir política de reintento
- **Un solo lugar** para mensajes estándar
- **Un solo lugar** para logging estructurado

### 5.2 Consistencia
- Todos los módulos usan la misma política
- Mensajes consistentes en toda la aplicación
- Logging estructurado facilita análisis y debugging

### 5.3 Mantenibilidad
- Cambios en política se hacen en un solo lugar
- Fácil agregar nuevos códigos de respuesta
- Fácil ajustar cooldown/backoff si se implementa reintento

### 5.4 Extensibilidad
- Fácil agregar métricas (contadores, histogramas)
- Fácil agregar alertas (si 0301 ocurre frecuentemente)
- Fácil implementar cooldown/backoff en el futuro

---

## 6. RESUMEN DE COINCIDENCIAS

| Archivo | Línea | Tipo | Acción Actual |
|---------|-------|------|---------------|
| `web/sifen_status_mapper.py` | 72-74 | Manejo 0301 | Retorna STATUS_ERROR |
| `tools/send_sirecepde.py` | 4389-4394 | Manejo 0301 | Print advertencia |
| `web/document_status.py` | 44 | Constante | Lista de códigos error |
| `app/sifen_client/soap_client.py` | 1372 | Parseo | Marca 0301 como "ok" |
| `tools/consulta_lote_de.py` | 1521-1522 | Manejo 0301 | Marca como "Rechazado" |
| `app/sifen_client/soap_client.py` | 2740-2745 | Manejo 0160 | NO reintenta (hard fail) |

---

**Última actualización**: 2025-01-XX  
**Versión**: 1.0

