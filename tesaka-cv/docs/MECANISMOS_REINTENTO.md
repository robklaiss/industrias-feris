# Mecanismos de Reintento y Loops de Envío/Consulta

## Resumen Ejecutivo

Este documento identifica **todos los mecanismos de reintento automático o loops** de envío/consulta en el repositorio, incluyendo condiciones, cantidad de intentos, delays, errores/códigos que los disparan, y si se ejecutan en CLI o server.

**⚠️ CRÍTICO**: **Ningún mecanismo reintenta con `dCodRes=0301`**. Todos los reintentos son solo para errores de conexión/red, NO para códigos de respuesta SIFEN.

---

## 1. REINTENTOS EN ENVÍO (siRecepLoteDE)

### 1.1 ❌ NO HAY REINTENTOS AUTOMÁTICOS EN ENVÍO

**Archivo**: `tools/send_sirecepde.py`, `web/main.py`

**Análisis**:
- El envío de lotes (`siRecepLoteDE`) **NO tiene reintentos automáticos**
- Si `dCodRes=0301` → se marca como error y **NO se reintenta**
- Si `dCodRes=0300` → se guarda y se consulta automáticamente (pero no se reenvía)

**Código relevante**:
- `web/sifen_status_mapper.py` línea 72: Si `codigo == "0301"` → retorna `STATUS_ERROR` (sin reintento)
- `web/main.py` línea 754: Si `dProtConsLote == 0` → **NO se consulta el lote** (no hay protocolo)

---

## 2. REINTENTOS EN CONSULTA DE LOTE (siConsLoteDE)

### 2.1 Reintento por `ConnectionResetError` (SOAP Client)

**Archivo**: `app/sifen_client/soap_client.py`  
**Función**: `consulta_lote_raw()` (líneas 2751-2848)  
**Ejecución**: Server (llamado desde web/CLI)

**Condición de reintento**:
```python
except ConnectionResetError as e:
    # Reintentar solo para ConnectionResetError (máximo 2 veces)
```

**Cantidad de intentos**: **2 reintentos** (total 3 intentos)

**Delay/sleep**:
```python
delays = [0.4, 0.8]  # 0.4s después del 1er fallo, 0.8s después del 2do
time.sleep(delays[attempt])
```

**Errores que lo disparan**:
- **Solo `ConnectionResetError`** (error de conexión TCP)
- **NO reintenta** por códigos de respuesta SIFEN (ej: 0361, 0362, 0364)
- **NO reintenta** por `dCodRes=0301` (este código es de recepción, no de consulta)

**Código específico** (líneas 2751-2848):
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
            result = client.service.siConsLoteDE(...)
            # ... parsear respuesta ...
            return parsed_result
        except ConnectionResetError:
            last_exception = e
            continue
        except Exception as retry_e:
            # Otro tipo de error en el reintento: lanzar el error original
            raise last_exception from retry_e
    
    # Si llegamos aquí, todos los reintentos fallaron
    raise SifenClientError(f"ConnectionResetError después de 2 reintentos: {last_exception}")
```

**⚠️ IMPORTANTE**: Este reintento **NO verifica `dCodRes`**. Solo reintenta si hay `ConnectionResetError` (error de red).

---

### 2.2 Reintento con urllib3 Retry (HTTP Adapter)

**Archivo**: `tools/consulta_lote_de.py`  
**Función**: `call_consulta_lote_raw()` (líneas 860-873)  
**Ejecución**: CLI (llamado desde `tools/consulta_lote_de.py`)

**Condición de reintento**:
```python
if URLLIB3_RETRY_AVAILABLE:
    retry = Retry(
        total=3,
        connect=3,
        read=3,
        backoff_factor=0.5,
        status_forcelist=[502, 503, 504],
        allowed_methods=frozenset(["GET", "POST"]),
        raise_on_status=False
    )
    adapter = HTTPAdapter(max_retries=retry, pool_connections=10, pool_maxsize=10)
```

**Cantidad de intentos**: **3 intentos totales** (2 reintentos)

**Delay/sleep**: **Backoff exponencial** con `backoff_factor=0.5`
- Intento 1: 0s
- Intento 2: 0.5s
- Intento 3: 1.0s

**Errores que lo disparan**:
- **Solo errores HTTP 5xx**: `502 Bad Gateway`, `503 Service Unavailable`, `504 Gateway Timeout`
- **NO reintenta** por códigos de respuesta SIFEN (ej: 0361, 0362, 0364)
- **NO reintenta** por `dCodRes=0301` (este código es de recepción, no de consulta)
- **NO reintenta** por errores HTTP 4xx (ej: 400 Bad Request)

**Código específico** (líneas 860-873):
```python
if URLLIB3_RETRY_AVAILABLE:
    retry = Retry(
        total=3,
        connect=3,
        read=3,
        backoff_factor=0.5,
        status_forcelist=[502, 503, 504],
        allowed_methods=frozenset(["GET", "POST"]),
        raise_on_status=False
    )
    adapter = HTTPAdapter(max_retries=retry, pool_connections=10, pool_maxsize=10)
else:
    adapter = HTTPAdapter(pool_connections=10, pool_maxsize=10)
```

**⚠️ IMPORTANTE**: Este reintento es a nivel HTTP (urllib3), **NO a nivel de aplicación**. No verifica `dCodRes`.

---

### 2.3 Reintento con Backoff Manual (lote_checker)

**Archivo**: `app/sifen_client/lote_checker.py`  
**Función**: `check_lote_status()` (líneas 152-222)  
**Ejecución**: Server (llamado desde `web/main.py::_check_lote_status_async()`)

**Condición de reintento**:
```python
# Detectar errores de conexión transitorios
is_connection_error = (
    isinstance(e, (ConnectionError, OSError)) or
    "connection reset" in error_str or
    "connection aborted" in error_str or
    "connection refused" in error_str or
    "reset by peer" in error_str or
    error_type in ("ConnectionError", "ConnectionResetError", "OSError")
)

if is_connection_error:
    if attempt < 2:  # No es el último intento
        wait_time = backoff_times[attempt]
        time.sleep(wait_time)
        continue
```

**Cantidad de intentos**: **3 intentos totales** (2 reintentos)

**Delay/sleep**: **Backoff manual**:
```python
backoff_times = [0.5, 1.5, 3.0]  # 0.5s después del 1er fallo, 1.5s después del 2do
```

**Errores que lo disparan**:
- **Solo errores de conexión**: `ConnectionError`, `OSError`, `ConnectionResetError`
- Strings en mensaje: "connection reset", "connection aborted", "connection refused", "reset by peer"
- **NO reintenta** por códigos de respuesta SIFEN (ej: 0361, 0362, 0364)
- **NO reintenta** por `dCodRes=0301` (este código es de recepción, no de consulta)

**Código específico** (líneas 158-222):
```python
# Backoff: 0.5s, 1.5s, 3s
backoff_times = [0.5, 1.5, 3.0]
last_error = None

for attempt in range(3):
    try:
        xml_response = call_consulta_lote_raw(...)
        break  # Éxito, salir del loop
    except Exception as e:
        # Detectar errores de conexión transitorios
        is_connection_error = (
            isinstance(e, (ConnectionError, OSError)) or
            "connection reset" in error_str or
            "connection aborted" in error_str or
            "connection refused" in error_str or
            "reset by peer" in error_str or
            error_type in ("ConnectionError", "ConnectionResetError", "OSError")
        )
        
        if is_connection_error:
            last_error = e
            if attempt < 2:  # No es el último intento
                wait_time = backoff_times[attempt]
                logger.warning(f"Error de conexión transitorio (intento {attempt + 1}/3): {e}. Reintentando en {wait_time}s...")
                time.sleep(wait_time)
                continue
            else:
                # Último intento falló, lanzar error
                raise
        else:
            # Otro tipo de error, no reintentar
            raise
```

**⚠️ IMPORTANTE**: Este reintento **NO verifica `dCodRes`**. Solo reintenta si hay errores de conexión.

---

## 3. LOOPS DE POLLING/CONSULTA

### 3.1 Loop Infinito de Polling (`follow_lote.py`)

**Archivo**: `tools/follow_lote.py`  
**Función**: `main()` (líneas 319-361)  
**Ejecución**: CLI

**Condición de loop**:
```python
while True:
    attempt += 1
    print(f"\n=== CONSULTA #{attempt} ===")
    rc = run_consulta_lote(args.env, prot, args.wsdl_file, args.wsdl_cache_dir)
    # ... procesar respuesta ...
    
    if looks_concluded(d_cod_lot, d_msg_lot):
        print("\n✅ Lote concluido (según dCodResLot/dMsgResLot).")
        sys.exit(0)
    
    if args.once:
        sys.exit(0)
    
    elapsed = time.time() - start
    if elapsed >= args.timeout:
        print(f"\n⏱️  Timeout alcanzado ({args.timeout}s).")
        sys.exit(4)
    
    time.sleep(max(1, args.interval))
```

**Cantidad de intentos**: **Infinito** (hasta que el lote concluya o se alcance timeout)

**Delay/sleep**: **Intervalo configurable** (default: 5 segundos)
```python
time.sleep(max(1, args.interval))  # default: 5s
```

**Condición de salida**:
- **Lote concluido**: `dCodResLot == "0362"` o mensaje contiene "concluido"
- **Timeout**: `elapsed >= args.timeout` (default: 180s)
- **Flag `--once`**: Ejecuta solo 1 consulta

**Errores/códigos que lo disparan**:
- **NO verifica `dCodRes` de recepción** (solo consulta lote)
- **Solo verifica `dCodResLot`** de consulta:
  - `0362` → lote concluido → **sale del loop**
  - `0361` → lote en procesamiento → **continúa el loop**
  - `0364` → consulta extemporánea → **continúa el loop** (pero requiere consulta por CDC)

**Código específico** (líneas 319-361):
```python
while True:
    attempt += 1
    print(f"\n=== CONSULTA #{attempt} ===")
    rc = run_consulta_lote(args.env, prot, args.wsdl_file, args.wsdl_cache_dir)
    
    cons_json = pick_latest_consulta_json(args.artifacts_dir)
    if cons_json:
        cons_data = load_json(cons_json)
        d_fec, d_cod_lot, d_msg_lot, docs = summarize_consulta_lote(cons_data)
        
        if looks_concluded(d_cod_lot, d_msg_lot):
            print("\n✅ Lote concluido (según dCodResLot/dMsgResLot).")
            sys.exit(0)
    
    if args.once:
        sys.exit(0)
    
    elapsed = time.time() - start
    if elapsed >= args.timeout:
        print(f"\n⏱️  Timeout alcanzado ({args.timeout}s).")
        sys.exit(4)
    
    time.sleep(max(1, args.interval))
```

**⚠️ IMPORTANTE**: Este loop **NO reintenta envíos**. Solo consulta el estado del lote periódicamente. **NO verifica `dCodRes=0301`** (ese código es de recepción, no de consulta).

---

### 3.2 Loop de Polling Automático (`poll_sifen_lotes.py`)

**Archivo**: `tools/poll_sifen_lotes.py`  
**Función**: `poll_lotes()` (líneas 135-202)  
**Ejecución**: CLI (diseñado para cron)

**Condición de loop**:
```python
while True:
    iteration += 1
    logger.info(f"--- Iteración {iteration} ---")
    
    # Obtener lotes pendientes
    lotes = get_lotes_pending_check(env=env, max_attempts=max_attempts)
    
    if not lotes:
        logger.info("No hay lotes pendientes de consulta")
        if once:
            break
        time.sleep(current_interval)
        continue
    
    # Procesar cada lote
    for lote in lotes:
        process_lote(lote, env)
    
    if once:
        break
    
    # Esperar antes de la siguiente iteración
    # Aumentar intervalo gradualmente (backoff) hasta max_interval_seconds
    time.sleep(current_interval)
    current_interval = min(current_interval * 1.1, max_interval_seconds)
```

**Cantidad de intentos**: **Infinito** (hasta que no haya lotes pendientes o se use `--once`)

**Delay/sleep**: **Backoff exponencial gradual**
```python
current_interval = interval_seconds  # default: 60s
# Aumentar intervalo gradualmente (backoff) hasta max_interval_seconds
time.sleep(current_interval)
current_interval = min(current_interval * 1.1, max_interval_seconds)  # max: 300s
```

**Condición de salida**:
- **Flag `--once`**: Ejecuta solo 1 iteración (útil para cron)
- **No hay lotes pendientes**: Continúa el loop pero espera antes de la siguiente iteración

**Errores/códigos que lo disparan**:
- **NO verifica `dCodRes` de recepción** (solo consulta lotes)
- **Solo consulta lotes** en estado `pending` o `processing`
- **NO reintenta envíos** con `dCodRes=0301`

**Código específico** (líneas 172-202):
```python
while True:
    iteration += 1
    logger.info(f"--- Iteración {iteration} ---")
    
    # Obtener lotes pendientes
    lotes = get_lotes_pending_check(env=env, max_attempts=max_attempts)
    
    if not lotes:
        logger.info("No hay lotes pendientes de consulta")
        if once:
            break
        time.sleep(current_interval)
        continue
    
    logger.info(f"Encontrados {len(lotes)} lotes pendientes")
    
    # Procesar cada lote
    processed = 0
    for lote in lotes:
        if process_lote(lote, env):
            processed += 1
    
    logger.info(f"Procesados {processed}/{len(lotes)} lotes")
    
    if once:
        break
    
    # Esperar antes de la siguiente iteración
    # Aumentar intervalo gradualmente (backoff) hasta max_interval_seconds
    time.sleep(current_interval)
    current_interval = min(current_interval * 1.1, max_interval_seconds)
```

**⚠️ IMPORTANTE**: Este loop **NO reintenta envíos**. Solo consulta el estado de lotes periódicamente. **NO verifica `dCodRes=0301`** (ese código es de recepción, no de consulta).

---

## 4. REINTENTOS EN OTROS CONTEXTOS

### 4.1 Reintento por CDC Duplicado (Base de Datos)

**Archivo**: `web/main.py`  
**Función**: `de_create()` (líneas 540-570)  
**Ejecución**: Server (endpoint web)

**Condición de reintento**:
```python
# Si hay unique violation por CDC, reintentar con numero_documento + 1
max_retries = 2
for attempt in range(max_retries):
    try:
        db.insert_document(...)
        return RedirectResponse(...)
    except ConnectionError as e:
        # Verificar si es error de unique violation (CDC duplicado)
        if "unique" in error_str or "duplicate" in error_str or "cdc duplicado" in error_str:
            # CDC duplicado: regenerar con numero_documento incrementado
            if attempt < max_retries - 1:
                numero_documento = str(num_doc_int + 1).zfill(len(numero_documento))
                # Regenerar DE con nuevo número
                continue
```

**Cantidad de intentos**: **2 intentos totales** (1 reintento)

**Delay/sleep**: **Sin delay** (reintento inmediato)

**Errores que lo disparan**:
- **Solo errores de BD**: `ConnectionError` con mensaje que contiene "unique", "duplicate", o "cdc duplicado"
- **NO reintenta** por códigos de respuesta SIFEN
- **NO reintenta** por `dCodRes=0301`

**⚠️ IMPORTANTE**: Este reintento es para **evitar CDC duplicados en BD**, NO para reintentar envíos a SIFEN.

---

### 4.2 Loops Infinitos en Utilidades (NO relacionados con SIFEN)

**Archivo**: `app/utils.py`  
**Funciones**: `get_next_remission_number()`, `get_next_invoice_number()` (líneas 97-140)

**Condición de loop**:
```python
while True:
    numero = f"{prefix}{base_number:06d}"
    cursor.execute("SELECT id FROM remissions WHERE numero_remision = ?", (numero,))
    if not cursor.fetchone():
        return numero
    base_number += 1
```

**Propósito**: Buscar el siguiente número disponible (no duplicado) en BD

**⚠️ IMPORTANTE**: Estos loops **NO están relacionados con SIFEN**. Son para generar números únicos en BD.

---

## 5. RESUMEN: ¿0301 DISPARA REINTENTO?

### ❌ NO: `dCodRes=0301` NO DISPARA NINGÚN REINTENTO

**Análisis completo**:

1. **Envío (siRecepLoteDE)**:
   - Si `dCodRes=0301` → `STATUS_ERROR` → **NO se reintenta**
   - Si `dProtConsLote=0` → **NO se consulta el lote** (no hay protocolo)

2. **Consulta de Lote (siConsLoteDE)**:
   - Los reintentos son solo para errores de conexión (`ConnectionResetError`, `ConnectionError`, `OSError`)
   - **NO reintentan** por códigos de respuesta SIFEN (ej: 0361, 0362, 0364)
   - **NO reintentan** por `dCodRes=0301` (ese código es de recepción, no de consulta)

3. **Loops de Polling**:
   - Solo consultan el estado del lote periódicamente
   - **NO reintentan envíos** con `dCodRes=0301`
   - Solo verifican `dCodResLot` (código de consulta, no de recepción)

---

## 6. TABLA RESUMEN

| Mecanismo | Archivo | Función | Intentos | Delay | Errores que Disparan | ¿0301 Dispara? | Ejecución |
|-----------|---------|---------|----------|-------|---------------------|----------------|-----------|
| **Reintento ConnectionResetError** | `soap_client.py` | `consulta_lote_raw()` | 3 (2 reintentos) | 0.4s, 0.8s | `ConnectionResetError` | ❌ NO | Server/CLI |
| **Reintento urllib3 Retry** | `consulta_lote_de.py` | `call_consulta_lote_raw()` | 3 (2 reintentos) | 0.5s, 1.0s (backoff) | HTTP 502, 503, 504 | ❌ NO | CLI |
| **Reintento Backoff Manual** | `lote_checker.py` | `check_lote_status()` | 3 (2 reintentos) | 0.5s, 1.5s, 3.0s | `ConnectionError`, `OSError` | ❌ NO | Server |
| **Loop Polling Infinito** | `follow_lote.py` | `main()` | Infinito | 5s (configurable) | `dCodResLot != 0362` | ❌ NO | CLI |
| **Loop Polling Automático** | `poll_sifen_lotes.py` | `poll_lotes()` | Infinito | 60s-300s (backoff) | Lotes pendientes | ❌ NO | CLI (cron) |
| **Reintento CDC Duplicado** | `main.py` | `de_create()` | 2 (1 reintento) | 0s | Error BD "unique" | ❌ NO | Server |

---

## 7. RECOMENDACIONES

### 7.1 Política Actual (Correcta)

✅ **NO reintentar con `dCodRes=0301`** es la política correcta:
- `0301` significa "Lote no encolado" → el lote NO será procesado
- Reintentar no tiene sentido → el lote seguirá sin encolarse
- Reintentar puede generar spam a SIFEN

### 7.2 Mejoras Sugeridas

1. **Centralizar política de reintento**:
   - Crear `app/sifen_client/response_policy.py` (ver `docs/ANALISIS_DCODRES_0301.md`)
   - Definir explícitamente qué códigos NO deben reintentarse

2. **Logging estructurado**:
   - Log cuando se decide NO reintentar por `dCodRes=0301`
   - Métricas de frecuencia de `0301` para detectar problemas

3. **Cooldown antes de reenvío manual**:
   - Si un usuario intenta reenviar manualmente después de `0301`, sugerir cooldown
   - Evitar spam a SIFEN por reenvíos manuales frecuentes

---

**Última actualización**: 2025-01-XX  
**Versión**: 1.0

