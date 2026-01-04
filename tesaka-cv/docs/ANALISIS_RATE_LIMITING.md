# Análisis: Rate Limiting / Throttling por RUC o Ambiente

## Resumen Ejecutivo

Este documento identifica si existe rate limiting/throttling por RUC o por ambiente (test/prod), y propone un throttle simple con persistencia del último envío por RUC si no existe.

---

## 1. BÚSQUEDA DE MECANISMOS EXISTENTES

### 1.1 Búsqueda de Palabras Clave

#### 1.1.1 "throttle", "rate limit", "ratelimit"
**Resultado**: ❌ **NO encontrado**
- Solo referencia en `docs/SIFEN_INTEGRATION_PLAN.md` línea 355: `[ ] Límites de tasa (rate limits)` (pendiente, no implementado)

#### 1.1.2 "semaphore", "lock", "mutex", "queue"
**Resultado**: ❌ **NO encontrado**
- Solo referencias a "blocked" (sign_blocked_reason.txt) que es para dependencias faltantes, no rate limiting

#### 1.1.3 "token bucket", "bucket", "sliding window", "fixed window"
**Resultado**: ❌ **NO encontrado**

#### 1.1.4 "no más de N envíos por minuto", "máximo envío", "limit send"
**Resultado**: ❌ **NO encontrado**

#### 1.1.5 "sleep", "delay", "cooldown" por RUC
**Resultado**: ❌ **NO encontrado**
- Los únicos `sleep` encontrados son:
  - Reintentos por errores de conexión (no es rate limiting)
  - Loops de polling (no es rate limiting)

---

### 1.2 Análisis de Código

#### 1.2.1 `app/sifen_client/soap_client.py::recepcion_lote()`
**Líneas**: 1707-2237

**Análisis**:
- ❌ **NO hay rate limiting** antes de enviar
- ❌ **NO hay throttle** por RUC o ambiente
- ❌ **NO hay sleep** fijo entre envíos
- ✅ Solo validaciones de tamaño y estructura XML

**Código relevante**:
```python
def recepcion_lote(self, xml_renvio_lote: str, dump_http: bool = False) -> Dict[str, Any]:
    service = "siRecepLoteDE"
    
    # Validaciones
    self._validate_size(service, xml_renvio_lote)
    # ... validaciones XML ...
    
    # POST HTTP (sin throttle)
    resp = session.post(post_url, data=soap_bytes, headers=headers_final, ...)
```

#### 1.2.2 `web/main.py::de_send_to_sifen()`
**Líneas**: 607-796

**Análisis**:
- ❌ **NO hay rate limiting** antes de llamar `recepcion_lote()`
- ❌ **NO hay throttle** por RUC
- ❌ **NO hay verificación** de último envío por RUC

**Código relevante** (línea 712):
```python
# Enviar lote a SIFEN (solo si preflight pasó)
response = client.recepcion_lote(payload_xml)  # ⚠️ Sin throttle
```

#### 1.2.3 `tools/send_sirecepde.py::send_sirecepde()`
**Líneas**: 3912-4640

**Análisis**:
- ❌ **NO hay rate limiting** antes de llamar `recepcion_lote()`
- ❌ **NO hay throttle** por RUC
- ❌ **NO hay verificación** de último envío por RUC

**Código relevante** (línea 4310):
```python
with SoapClient(config) as client:
    response = client.recepcion_lote(payload_xml, dump_http=dump_http)  # ⚠️ Sin throttle
```

---

## 2. CONCLUSIÓN: NO HAY RATE LIMITING

### 2.1 Estado Actual

❌ **NO existe ningún mecanismo de rate limiting/throttling**:
- ❌ No hay throttle por RUC
- ❌ No hay throttle por ambiente (test/prod)
- ❌ No hay sleep fijo entre envíos
- ❌ No hay token bucket
- ❌ No hay semáforos
- ❌ No hay colas
- ❌ No hay verificación de "último envío por RUC"

### 2.2 Riesgo

**Problema potencial**:
- Si múltiples usuarios/envíos automáticos envían simultáneamente desde el mismo RUC → **spam a SIFEN**
- SIFEN puede rechazar con `dCodRes=0301` o rate limit propio
- No hay protección local contra envíos demasiado frecuentes

---

## 3. PROPUESTA: Throttle Simple por RUC

### 3.1 Diseño Mínimo

**Ubicación**: Nueva tabla en `web/db.py` + función de throttle

**Estructura propuesta**:
```sql
CREATE TABLE IF NOT EXISTS sifen_ruc_throttle (
    -- Clave: RUC + ambiente
    ruc_emisor TEXT NOT NULL,
    env TEXT NOT NULL CHECK(env IN ('test', 'prod')),
    
    -- Timestamp del último envío
    last_sent_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    
    -- Contador de envíos (útil para métricas)
    send_count INTEGER DEFAULT 1,
    
    -- Clave primaria compuesta
    PRIMARY KEY (ruc_emisor, env)
);

-- Índice para búsquedas rápidas
CREATE INDEX IF NOT EXISTS idx_sifen_ruc_throttle_last_sent 
ON sifen_ruc_throttle(last_sent_at DESC);
```

**Justificación**:
- **Clave compuesta `(ruc_emisor, env)`**: Diferentes ambientes pueden tener diferentes límites
- **`last_sent_at`**: Timestamp del último envío (para calcular tiempo transcurrido)
- **`send_count`**: Contador de envíos (útil para métricas y alertas)

---

### 3.2 Función de Throttle

**Archivo**: `web/db.py` (agregar nuevas funciones)

#### 3.2.1 `check_and_update_ruc_throttle()`

```python
def check_and_update_ruc_throttle(
    ruc_emisor: str,
    env: str,
    min_seconds_between_sends: int = 10,  # Default: 10 segundos entre envíos
) -> Tuple[bool, Optional[float], Optional[str]]:
    """
    Verifica si se permite enviar basado en throttle por RUC.
    Si se permite, actualiza el timestamp del último envío.
    
    Args:
        ruc_emisor: RUC del emisor
        env: Ambiente ('test' o 'prod')
        min_seconds_between_sends: Segundos mínimos entre envíos (default: 10)
    
    Returns:
        Tupla (allow, wait_seconds, reason)
        - allow: True si se permite enviar, False si no
        - wait_seconds: Segundos a esperar si no se permite (None si se permite)
        - reason: Razón si no se permite (None si se permite)
    """
    if not ruc_emisor or not env:
        # Si no se puede determinar RUC, permitir (no crítico)
        return True, None, None
    
    conn = get_conn()
    cursor = conn.cursor()
    
    # Obtener último envío
    cursor.execute("""
        SELECT last_sent_at, send_count
        FROM sifen_ruc_throttle
        WHERE ruc_emisor = ? AND env = ?
    """, (ruc_emisor, env))
    row = cursor.fetchone()
    
    if row:
        # Ya existe registro
        last_sent_str = row[0]
        send_count = row[1]
        
        # Parsear timestamp
        try:
            from datetime import datetime
            last_sent = datetime.fromisoformat(last_sent_str.replace("Z", "+00:00"))
            now = datetime.utcnow()
            elapsed = (now - last_sent.replace(tzinfo=None)).total_seconds()
        except Exception:
            # Si falla el parsing, permitir (no crítico)
            elapsed = min_seconds_between_sends + 1
        
        if elapsed < min_seconds_between_sends:
            # Throttle activo: no permitir
            wait_seconds = min_seconds_between_sends - elapsed
            reason = f"Throttle activo: último envío hace {elapsed:.1f}s (mínimo {min_seconds_between_sends}s entre envíos)"
            conn.close()
            return False, wait_seconds, reason
        
        # Permitir: actualizar timestamp y contador
        cursor.execute("""
            UPDATE sifen_ruc_throttle
            SET 
                last_sent_at = CURRENT_TIMESTAMP,
                send_count = send_count + 1
            WHERE ruc_emisor = ? AND env = ?
        """, (ruc_emisor, env))
    else:
        # Primer envío: crear registro
        cursor.execute("""
            INSERT INTO sifen_ruc_throttle (ruc_emisor, env, last_sent_at, send_count)
            VALUES (?, ?, CURRENT_TIMESTAMP, 1)
        """, (ruc_emisor, env))
    
    conn.commit()
    conn.close()
    return True, None, None
```

#### 3.2.2 `get_ruc_throttle_info()`

```python
def get_ruc_throttle_info(ruc_emisor: str, env: str) -> Optional[Dict[str, Any]]:
    """
    Obtiene información de throttle para un RUC.
    
    Returns:
        Dict con last_sent_at, send_count, o None si no existe
    """
    conn = get_conn()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT last_sent_at, send_count
        FROM sifen_ruc_throttle
        WHERE ruc_emisor = ? AND env = ?
    """, (ruc_emisor, env))
    row = cursor.fetchone()
    conn.close()
    
    if row:
        return {
            "last_sent_at": row[0],
            "send_count": row[1],
        }
    return None
```

---

### 3.3 Integración en Flujo de Envío

#### 3.3.1 En `web/main.py::de_send_to_sifen()`

**Agregar ANTES de `client.recepcion_lote()`** (línea ~712):

```python
# Extraer RUC del documento
ruc_emisor = document.get('ruc_emisor')

# Throttle por RUC (si está disponible)
if ruc_emisor:
    from web.db import check_and_update_ruc_throttle
    
    # Configurar throttle (10 segundos entre envíos por defecto)
    throttle_seconds = int(os.getenv("SIFEN_THROTTLE_SECONDS", "10"))
    
    allow, wait_seconds, reason = check_and_update_ruc_throttle(
        ruc_emisor=ruc_emisor,
        env=env,
        min_seconds_between_sends=throttle_seconds,
    )
    
    if not allow:
        error_msg = f"BLOQUEADO: {reason}. Esperar {wait_seconds:.1f}s antes de reenviar."
        db.update_document_status(doc_id, status="error", message=error_msg)
        return RedirectResponse(
            url=f"/de/{doc_id}?error=1&throttle={int(wait_seconds)}",
            status_code=303
        )
    
    # Si se permite pero hay que esperar un poco, hacer sleep (opcional)
    # Por ahora, solo bloqueamos si el throttle está activo

# Enviar lote a SIFEN (solo si throttle pasó)
response = client.recepcion_lote(payload_xml)
```

#### 3.3.2 En `tools/send_sirecepde.py::send_sirecepde()`

**Agregar ANTES de `client.recepcion_lote()`** (línea ~4310):

```python
# Extraer RUC del XML
ruc_emisor = None
try:
    xml_root = etree.fromstring(xml_bytes)
    # Buscar RUC (dRucEm)
    ruc_elem = xml_root.find(f".//{{{SIFEN_NS_URI}}}dRucEm")
    if ruc_elem is None:
        ruc_elem = xml_root.find(".//dRucEm")
    if ruc_elem is not None:
        ruc_emisor = ruc_elem.text.strip()
except Exception:
    # Si no se puede extraer, continuar sin throttle (no crítico)
    pass

# Throttle por RUC (si está disponible)
if ruc_emisor:
    try:
        sys.path.insert(0, str(Path(__file__).parent.parent))
        from web.db import check_and_update_ruc_throttle
        
        # Configurar throttle (10 segundos entre envíos por defecto)
        throttle_seconds = int(os.getenv("SIFEN_THROTTLE_SECONDS", "10"))
        
        allow, wait_seconds, reason = check_and_update_ruc_throttle(
            ruc_emisor=ruc_emisor,
            env=env,
            min_seconds_between_sends=throttle_seconds,
        )
        
        if not allow:
            return {
                "success": False,
                "error": f"BLOQUEADO: {reason}. Esperar {wait_seconds:.1f}s antes de reenviar.",
                "error_type": "ThrottleBlocked",
                "wait_seconds": wait_seconds,
            }
    except Exception as e:
        # Si falla el throttle, continuar sin bloquear (no crítico)
        if debug_enabled:
            print(f"⚠️  Error al verificar throttle: {e}")

# Enviar lote a SIFEN (solo si throttle pasó)
with SoapClient(config) as client:
    response = client.recepcion_lote(payload_xml, dump_http=dump_http)
```

---

### 3.4 Configuración

**Variable de entorno**:
```env
# Throttle por RUC (segundos mínimos entre envíos)
SIFEN_THROTTLE_SECONDS=10  # Default: 10 segundos
```

**Recomendaciones**:
- **Test**: 10 segundos (permite pruebas rápidas)
- **Prod**: 30-60 segundos (más conservador, evita spam)

---

## 4. ALTERNATIVA: Throttle Más Sofisticado

### 4.1 Token Bucket (Opcional)

Si se necesita un throttle más sofisticado (ej: "máximo 10 envíos por minuto"), se puede implementar token bucket:

```python
def check_token_bucket_throttle(
    ruc_emisor: str,
    env: str,
    max_tokens: int = 10,  # Máximo 10 envíos
    refill_seconds: int = 60,  # Por minuto
) -> Tuple[bool, Optional[float], Optional[str]]:
    """
    Implementa token bucket: permite hasta max_tokens envíos en refill_seconds.
    
    Returns:
        Tupla (allow, wait_seconds, reason)
    """
    # Implementación con tabla sifen_ruc_throttle:
    # - tokens: INTEGER (tokens disponibles)
    # - last_refill_at: TIMESTAMP (última vez que se rellenaron tokens)
    # - Lógica: si tokens > 0, permitir y decrementar; si tokens == 0, calcular cuándo se rellenará
    pass
```

**Por ahora, el throttle simple (sleep fijo) es suficiente**.

---

## 5. BENEFICIOS

### 5.1 Prevención de Spam

✅ **Impide envíos demasiado frecuentes** desde el mismo RUC  
✅ **Protege contra rate limiting de SIFEN** (si SIFEN tiene límites propios)  
✅ **Reduce riesgo de `dCodRes=0301`** por envíos demasiado rápidos

### 5.2 Simplicidad

✅ **Implementación simple**: Solo tabla + función de verificación  
✅ **Configurable**: Variable de entorno `SIFEN_THROTTLE_SECONDS`  
✅ **No bloqueante**: Si no se puede extraer RUC, continúa sin bloquear

### 5.3 Métricas

✅ **Contador de envíos**: `send_count` permite ver cuántas veces se envió desde un RUC  
✅ **Timestamp del último envío**: Permite calcular frecuencia de envíos

---

## 6. MIGRACIÓN

### 6.1 Script de Migración

**Archivo**: `web/db.py` (agregar en `get_conn()`)

```python
def get_conn():
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    
    # ... crear otras tablas ...
    
    # Crear tabla sifen_ruc_throttle si no existe
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS sifen_ruc_throttle (
            ruc_emisor TEXT NOT NULL,
            env TEXT NOT NULL CHECK(env IN ('test', 'prod')),
            last_sent_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
            send_count INTEGER DEFAULT 1,
            PRIMARY KEY (ruc_emisor, env)
        )
    """)
    
    # Crear índice
    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_sifen_ruc_throttle_last_sent 
        ON sifen_ruc_throttle(last_sent_at DESC)
    """)
    
    conn.commit()
    return conn
```

---

## 7. RESUMEN

### 7.1 Estado Actual

❌ **NO existe rate limiting/throttling**:
- No hay throttle por RUC
- No hay throttle por ambiente
- No hay sleep fijo entre envíos
- No hay verificación de último envío por RUC

### 7.2 Propuesta

✅ **Nueva tabla `sifen_ruc_throttle`**:
- Clave: `(ruc_emisor, env)`
- Campos: `last_sent_at`, `send_count`
- Función: `check_and_update_ruc_throttle()` (verifica y actualiza)

✅ **Integración**:
- En `web/main.py::de_send_to_sifen()`: Verificar antes de `client.recepcion_lote()`
- En `tools/send_sirecepde.py::send_sirecepde()`: Verificar antes de `client.recepcion_lote()`

✅ **Configuración**:
- Variable de entorno: `SIFEN_THROTTLE_SECONDS=10` (default: 10 segundos)

---

## 8. PUNTO DE INTEGRACIÓN RECOMENDADO

### 8.1 Ubicación Exacta

**Archivo**: `web/main.py`  
**Línea**: ~711 (justo antes de `client.recepcion_lote(payload_xml)`)  
**Contexto**: Después de preflight, antes de enviar HTTP

**Código sugerido**:
```python
# Throttle por RUC (antes de enviar)
ruc_emisor = document.get('ruc_emisor')
if ruc_emisor:
    from web.db import check_and_update_ruc_throttle
    throttle_seconds = int(os.getenv("SIFEN_THROTTLE_SECONDS", "10"))
    allow, wait_seconds, reason = check_and_update_ruc_throttle(
        ruc_emisor=ruc_emisor,
        env=env,
        min_seconds_between_sends=throttle_seconds,
    )
    if not allow:
        error_msg = f"BLOQUEADO: {reason}"
        db.update_document_status(doc_id, status="error", message=error_msg)
        return RedirectResponse(url=f"/de/{doc_id}?error=1", status_code=303)

# Enviar lote a SIFEN (solo si throttle pasó)
response = client.recepcion_lote(payload_xml)
```

---

**Última actualización**: 2025-01-XX  
**Versión**: 1.0

