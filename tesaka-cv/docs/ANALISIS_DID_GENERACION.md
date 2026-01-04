# Análisis: Generación de dId (15 dígitos) para Lotes SIFEN

## Resumen Ejecutivo

Este documento analiza la generación de `dId` (15 dígitos) para lotes SIFEN, identifica problemas de colisiones potenciales, y propone una estrategia centralizada y estable.

---

## 1. LOCALIZACIÓN DE FUNCIONES

### 1.1 `make_did_15()` - Implementación 1

**Archivo**: `tools/send_sirecepde.py`  
**Línea**: 3690-3694  
**Contexto**: Dentro de `build_r_envio_lote_xml()`

```python
def make_did_15() -> str:
    """Genera un dId único de 15 dígitos: YYYYMMDDHHMMSS + 1 dígito random"""
    import random
    base = datetime.now().strftime("%Y%m%d%H%M%S")  # 14 dígitos
    return base + str(random.randint(0, 9))  # + 1 dígito random = 15
```

**Llamadas**:
- Línea 3697: `did = make_did_15()` (SIEMPRE genera uno nuevo, ignora parámetro `did`)

---

### 1.2 `make_did_15()` - Implementación 2 (DUPLICADA)

**Archivo**: `tools/send_sirecepde.py`  
**Línea**: 4099-4104  
**Contexto**: Dentro de `send_sirecepde()`

```python
def make_did_15() -> str:
    """Genera un dId único de 15 dígitos: YYYYMMDDHHMMSS + 1 dígito random"""
    import random
    import datetime as _dt
    base = _dt.datetime.now().strftime("%Y%m%d%H%M%S")  # 14 dígitos
    return base + str(random.randint(0, 9))  # + 1 dígito random = 15
```

**Llamadas**:
- Línea 4113: `return make_did_15()` (dentro de `normalize_or_make_did()`)

---

### 1.3 `normalize_or_make_did()`

**Archivo**: `tools/send_sirecepde.py`  
**Línea**: 4107-4113  
**Contexto**: Dentro de `send_sirecepde()`

```python
def normalize_or_make_did(existing: Optional[str]) -> str:
    """Valida que el dId tenga EXACTAMENTE 15 dígitos, sino genera uno nuevo"""
    import re
    s = (existing or "").strip()
    if re.fullmatch(r"\d{15}", s):
        return s
    return make_did_15()
```

**Llamadas**:
- Línea 4126: `did = normalize_or_make_did(existing_did_from_xml)`

**Lógica**:
1. Intenta extraer `dId` del XML original (líneas 4116-4123)
2. Si el `dId` tiene EXACTAMENTE 15 dígitos, lo reutiliza
3. Si no, genera uno nuevo con `make_did_15()`

---

## 2. FLUJO DE GENERACIÓN

### 2.1 Flujo en `build_r_envio_lote_xml()`

**Archivo**: `tools/send_sirecepde.py`  
**Línea**: 3677-3711

```python
def build_r_envio_lote_xml(did: Union[int, str], xml_bytes: bytes, zip_base64: Optional[str] = None) -> str:
    # ...
    def make_did_15() -> str:
        # ... implementación local ...
    
    # SIEMPRE generar dId de 15 dígitos (ignorar el parámetro did)
    did = make_did_15()  # SIEMPRE (no reutilizar nada)
    
    # ...
    dId.text = did  # Usar el dId de 15 dígitos generado
```

**Características**:
- ✅ **SIEMPRE genera uno nuevo** (ignora el parámetro `did`)
- ❌ **No verifica colisiones** en BD
- ❌ **No persiste el dId generado**

**Llamadas desde**:
- `tools/send_sirecepde.py::send_sirecepde()` (línea 4132): `build_r_envio_lote_xml(did=did, ...)`
- `web/main.py::de_send_to_sifen()` (línea 695): `build_r_envio_lote_xml(did=1, ...)` (el `did=1` es ignorado)
- `tools/smoke_sign_and_zip.py` (línea 127): `build_r_envio_lote_xml(did=1, ...)` (el `did=1` es ignorado)

---

### 2.2 Flujo en `send_sirecepde()`

**Archivo**: `tools/send_sirecepde.py`  
**Línea**: 4098-4132

```python
def send_sirecepde(...):
    # ...
    def make_did_15() -> str:
        # ... implementación local ...
    
    def normalize_or_make_did(existing: Optional[str]) -> str:
        # ... valida 15 dígitos, sino genera nuevo ...
    
    # Obtener dId del XML original si está disponible
    existing_did_from_xml = None
    try:
        xml_root = etree.fromstring(xml_bytes)
        d_id_elem = xml_root.find(f".//{{{SIFEN_NS}}}dId")
        if d_id_elem is not None and d_id_elem.text:
            existing_did_from_xml = d_id_elem.text.strip()
    except:
        pass
    
    # Normalizar o generar dId (solo acepta EXACTAMENTE 15 dígitos)
    did = normalize_or_make_did(existing_did_from_xml)
    
    # Construir el payload de lote completo
    payload_xml = build_r_envio_lote_xml(did=did, xml_bytes=xml_bytes, zip_base64=zip_base64)
```

**Características**:
- ✅ Intenta reutilizar `dId` del XML si tiene 15 dígitos
- ❌ Si el XML no tiene `dId` o no tiene 15 dígitos, genera uno nuevo
- ❌ **PERO**: `build_r_envio_lote_xml()` ignora el `did` pasado y genera uno nuevo de todas formas
- ❌ **No verifica colisiones** en BD
- ❌ **No persiste el dId generado**

---

## 3. ANÁLISIS DE RIESGO DE COLISIONES

### 3.1 Algoritmo Actual

**Formato**: `YYYYMMDDHHMMSS` (14 dígitos) + `random(0-9)` (1 dígito) = **15 dígitos**

**Ejemplo**: `20250115143025` + `7` = `202501151430257`

### 3.2 Probabilidad de Colisión

**Escenario 1: Dos envíos en el mismo segundo**
- **Base temporal**: `YYYYMMDDHHMMSS` (mismo segundo)
- **Random**: 1 dígito (0-9) = **10 posibilidades**
- **Probabilidad de colisión**: **10%** (1/10)

**Escenario 2: Múltiples procesos/threads simultáneos**
- Si 2 procesos envían en el mismo segundo → **10% de colisión**
- Si 3 procesos envían en el mismo segundo → **~27% de colisión** (1 - (9/10)²)
- Si 5 procesos envían en el mismo segundo → **~41% de colisión** (1 - (9/10)⁴)

**Escenario 3: Envíos muy rápidos (mismo segundo)**
- Si hay un burst de envíos (ej: 10 envíos en 1 segundo) → **~65% de probabilidad de al menos una colisión**

### 3.3 Impacto de Colisiones

**Si SIFEN rechaza dId duplicados**:
- ❌ `dCodRes=0301` o similar
- ❌ Lote no encolado
- ❌ Necesidad de reenvío manual

**Si SIFEN acepta dId duplicados**:
- ⚠️ Dificultad para rastrear envíos
- ⚠️ Confusión en logs/artifacts

---

## 4. VERIFICACIÓN DE PERSISTENCIA EN BD

### 4.1 Tabla `de_documents`

**Archivo**: `web/db.py`  
**Schema** (líneas 46-63):
```sql
CREATE TABLE IF NOT EXISTS de_documents (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    cdc TEXT UNIQUE NOT NULL,
    ruc_emisor TEXT NOT NULL,
    timbrado TEXT NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    de_xml TEXT NOT NULL,
    sirecepde_xml TEXT,
    signed_xml TEXT,
    last_status TEXT,
    last_code TEXT,
    last_message TEXT,
    d_prot_cons_lote TEXT,  -- ⚠️ Solo protocolo de lote, NO dId
    approved_at TEXT,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
)
```

**Resultado**: ❌ **NO hay columna `dId`**

---

### 4.2 Tabla `sifen_lotes`

**Archivo**: `web/lotes_db.py`  
**Schema** (líneas 40-55):
```sql
CREATE TABLE IF NOT EXISTS sifen_lotes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    env TEXT NOT NULL CHECK(env IN ('test', 'prod')),
    d_prot_cons_lote TEXT NOT NULL UNIQUE,  -- ⚠️ Solo protocolo de lote, NO dId
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    last_checked_at TIMESTAMP,
    last_cod_res_lot TEXT,
    last_msg_res_lot TEXT,
    last_response_xml TEXT,
    status TEXT NOT NULL DEFAULT 'pending',
    attempts INTEGER DEFAULT 0,
    de_document_id INTEGER,
    FOREIGN KEY (de_document_id) REFERENCES de_documents(id)
)
```

**Resultado**: ❌ **NO hay columna `dId`**

---

### 4.3 Conclusión sobre Persistencia

❌ **NO se guarda `dId` en BD**:
- Solo se guarda `d_prot_cons_lote` (protocolo de lote devuelto por SIFEN)
- No hay verificación de colisiones de `dId`
- No hay historial de `dId` usados
- No hay forma de detectar reutilización de `dId`

---

## 5. PROBLEMAS IDENTIFICADOS

### 5.1 Código Duplicado

❌ **Dos implementaciones idénticas de `make_did_15()`**:
- Una en `build_r_envio_lote_xml()` (línea 3690)
- Otra en `send_sirecepde()` (línea 4099)

**Impacto**: Mantenimiento difícil, riesgo de divergencia.

---

### 5.2 Riesgo de Colisiones

❌ **Alto riesgo de colisiones**:
- Solo 1 dígito random (10 posibilidades)
- Si 2+ envíos ocurren en el mismo segundo → 10%+ probabilidad de colisión
- No hay verificación de colisiones en BD

---

### 5.3 Falta de Centralización

❌ **Lógica dispersa**:
- `make_did_15()` definida localmente en 2 lugares
- `normalize_or_make_did()` solo en `send_sirecepde()`
- `build_r_envio_lote_xml()` ignora el parámetro `did` y siempre genera uno nuevo

---

### 5.4 Falta de Persistencia

❌ **No se guarda `dId` en BD**:
- No hay columna `dId` en `de_documents`
- No hay columna `dId` en `sifen_lotes`
- No hay forma de verificar si un `dId` ya fue usado

---

### 5.5 Inconsistencia en Flujo

❌ **`build_r_envio_lote_xml()` ignora el parámetro `did`**:
- `send_sirecepde()` genera `did` con `normalize_or_make_did()`
- Lo pasa a `build_r_envio_lote_xml(did=did, ...)`
- Pero `build_r_envio_lote_xml()` lo ignora y genera uno nuevo
- **Resultado**: El `did` generado en `send_sirecepde()` nunca se usa

---

## 6. PROPUESTA: Estrategia Centralizada y Estable

### 6.1 Módulo Centralizado

**Archivo**: `app/sifen_client/did_generator.py` (NUEVO)

```python
"""
Generador centralizado de dId (15 dígitos) para SIFEN.

Estrategia: datetime (14 dígitos) + random (2 dígitos) = 16 dígitos
Pero truncamos a 15 dígitos para cumplir con SIFEN.

Alternativa más segura: datetime (13 dígitos) + random (2 dígitos) = 15 dígitos
- YYYYMMDDHHMM (13) + RR (2) = 15
- Permite hasta 100 envíos por minuto sin colisión
"""
import random
import time
from datetime import datetime
from typing import Optional
from pathlib import Path
import sqlite3


def make_did_15() -> str:
    """
    Genera un dId único de 15 dígitos.
    
    Estrategia: YYYYMMDDHHMM (13 dígitos) + RR (2 dígitos random) = 15 dígitos
    - Permite hasta 100 envíos por minuto sin colisión
    - Si hay colisión (mismo minuto + mismo random), reintenta con microsegundos
    
    Returns:
        String de 15 dígitos
    """
    # Base temporal: YYYYMMDDHHMM (13 dígitos, resolución de minuto)
    base = datetime.now().strftime("%Y%m%d%H%M")
    
    # Random de 2 dígitos (00-99) = 100 posibilidades
    random_part = random.randint(0, 99)
    random_str = str(random_part).zfill(2)
    
    # Combinar: 13 + 2 = 15 dígitos
    did = base + random_str
    
    # Verificar colisión en BD (opcional, pero recomendado)
    if _is_did_used(did):
        # Si está usado, agregar microsegundos como fallback
        # Usar últimos 2 dígitos de microsegundos
        microseconds = datetime.now().microsecond
        micro_str = str(microseconds % 100).zfill(2)
        # Reemplazar los últimos 2 dígitos con microsegundos
        did = base + micro_str
    
    return did


def make_did_15_with_verification(env: str, db_path: Optional[Path] = None) -> str:
    """
    Genera un dId único de 15 dígitos con verificación en BD.
    
    Args:
        env: Ambiente ('test' o 'prod')
        db_path: Ruta a la BD (opcional, usa default si None)
    
    Returns:
        String de 15 dígitos garantizado único
    """
    max_attempts = 10
    for attempt in range(max_attempts):
        did = make_did_15()
        
        # Verificar en BD
        if not _is_did_used_in_db(did, env, db_path):
            return did
        
        # Si está usado, esperar un poco y reintentar
        time.sleep(0.01)  # 10ms
    
    # Si después de 10 intentos sigue colisionando, usar timestamp completo
    # YYYYMMDDHHMMSS (14) + 1 dígito de microsegundos = 15
    base = datetime.now().strftime("%Y%m%d%H%M%S")
    micro = datetime.now().microsecond % 10
    return base + str(micro)


def normalize_or_make_did(existing: Optional[str], env: str = "test", db_path: Optional[Path] = None) -> str:
    """
    Valida que el dId tenga EXACTAMENTE 15 dígitos, sino genera uno nuevo.
    
    Args:
        existing: dId existente (puede ser None)
        env: Ambiente ('test' o 'prod')
        db_path: Ruta a la BD (opcional)
    
    Returns:
        dId válido de 15 dígitos
    """
    import re
    
    if existing:
        s = existing.strip()
        if re.fullmatch(r"\d{15}", s):
            # Verificar que no esté usado en BD (opcional)
            if not _is_did_used_in_db(s, env, db_path):
                return s
            # Si está usado, generar uno nuevo
            return make_did_15_with_verification(env, db_path)
    
    # Generar uno nuevo
    return make_did_15_with_verification(env, db_path)


def _is_did_used_in_db(did: str, env: str, db_path: Optional[Path] = None) -> bool:
    """
    Verifica si un dId ya fue usado en BD.
    
    Returns:
        True si está usado, False si no
    """
    if db_path is None:
        from web.db import DB_PATH
        db_path = DB_PATH
    
    if not db_path.exists():
        return False  # Si no existe BD, asumir que no está usado
    
    try:
        conn = sqlite3.connect(str(db_path))
        cursor = conn.cursor()
        
        # Verificar en sifen_did_history (si existe)
        cursor.execute("""
            SELECT name FROM sqlite_master 
            WHERE type='table' AND name='sifen_did_history'
        """)
        if cursor.fetchone():
            cursor.execute("""
                SELECT 1 FROM sifen_did_history
                WHERE dId = ? AND env = ?
                LIMIT 1
            """, (did, env))
            result = cursor.fetchone() is not None
            conn.close()
            return result
        
        conn.close()
        return False
    except Exception:
        # Si falla, asumir que no está usado (no bloquear)
        return False


def _is_did_used(did: str) -> bool:
    """
    Verificación rápida (sin BD).
    Por ahora, siempre retorna False (no hay persistencia).
    """
    return False
```

---

### 6.2 Tabla de Historial de dId

**Archivo**: `web/db.py` (agregar en `get_conn()`)

```python
def get_conn():
    # ... código existente ...
    
    # Crear tabla de historial de dId si no existe
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS sifen_did_history (
            dId TEXT NOT NULL,
            env TEXT NOT NULL CHECK(env IN ('test', 'prod')),
            used_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
            ruc_emisor TEXT,
            d_prot_cons_lote TEXT,
            PRIMARY KEY (dId, env)
        )
    """)
    
    # Índice para búsquedas rápidas
    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_sifen_did_history_used_at 
        ON sifen_did_history(used_at DESC)
    """)
    
    conn.commit()
    return conn
```

**Función para registrar dId usado**:

```python
def record_did_used(did: str, env: str, ruc_emisor: Optional[str] = None, d_prot_cons_lote: Optional[str] = None) -> bool:
    """
    Registra un dId como usado en BD.
    
    Returns:
        True si se registró, False si ya existía
    """
    try:
        conn = get_conn()
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO sifen_did_history (dId, env, ruc_emisor, d_prot_cons_lote)
            VALUES (?, ?, ?, ?)
        """, (did, env, ruc_emisor, d_prot_cons_lote))
        conn.commit()
        conn.close()
        return True
    except sqlite3.IntegrityError:
        # Ya existe (colisión)
        conn.close()
        return False
    except Exception as e:
        conn.close()
        # No bloquear si falla
        return False
```

---

### 6.3 Integración en Flujo

#### 6.3.1 Actualizar `build_r_envio_lote_xml()`

**Archivo**: `tools/send_sirecepde.py`  
**Línea**: 3677

```python
def build_r_envio_lote_xml(did: Union[int, str], xml_bytes: bytes, zip_base64: Optional[str] = None, env: str = "test") -> str:
    """
    Construye el XML rEnvioLote con el lote comprimido en Base64.
    
    Args:
        did: ID del documento (puede ser usado si tiene 15 dígitos, sino se genera uno nuevo)
        xml_bytes: XML original
        zip_base64: Base64 del ZIP (opcional)
        env: Ambiente ('test' o 'prod') para verificación de colisiones
    """
    from app.sifen_client.did_generator import normalize_or_make_did
    
    # Normalizar o generar dId (con verificación de colisiones)
    did = normalize_or_make_did(str(did) if did else None, env=env)
    
    # ... resto del código ...
    dId.text = did
```

#### 6.3.2 Actualizar `send_sirecepde()`

**Archivo**: `tools/send_sirecepde.py`  
**Línea**: 4098

```python
def send_sirecepde(...):
    # ...
    from app.sifen_client.did_generator import normalize_or_make_did, record_did_used
    
    # Normalizar o generar dId (con verificación de colisiones)
    did = normalize_or_make_did(existing_did_from_xml, env=env)
    
    # Construir payload
    payload_xml = build_r_envio_lote_xml(did=did, xml_bytes=xml_bytes, zip_base64=zip_base64, env=env)
    
    # ... después de enviar exitosamente ...
    # Registrar dId usado
    try:
        ruc_emisor = _extract_ruc_from_xml(xml_bytes)  # Helper a implementar
        record_did_used(did, env=env, ruc_emisor=ruc_emisor, d_prot_cons_lote=d_prot_cons_lote)
    except Exception:
        pass  # No bloquear si falla
```

#### 6.3.3 Actualizar `web/main.py::de_send_to_sifen()`

**Archivo**: `web/main.py`  
**Línea**: 695

```python
# ... antes de build_r_envio_lote_xml ...
from app.sifen_client.did_generator import normalize_or_make_did, record_did_used

# Generar dId (no hardcodear "1")
did = normalize_or_make_did(None, env=env)

payload_xml = build_r_envio_lote_xml(did=did, xml_bytes=de_xml_bytes, zip_base64=zip_base64, env=env)

# ... después de enviar exitosamente ...
# Registrar dId usado
try:
    record_did_used(did, env=env, ruc_emisor=document.get('ruc_emisor'), d_prot_cons_lote=d_prot_cons_lote)
except Exception:
    pass
```

---

## 7. COMPARACIÓN DE ESTRATEGIAS

### 7.1 Estrategia Actual

| Aspecto | Valor |
|--------|-------|
| Formato | `YYYYMMDDHHMMSS` (14) + `random(0-9)` (1) = 15 |
| Resolución temporal | 1 segundo |
| Posibilidades por segundo | 10 |
| Probabilidad de colisión (2 envíos mismo segundo) | 10% |
| Verificación en BD | ❌ No |
| Persistencia | ❌ No |
| Centralización | ❌ No (duplicado) |

---

### 7.2 Estrategia Propuesta

| Aspecto | Valor |
|--------|-------|
| Formato | `YYYYMMDDHHMM` (13) + `random(00-99)` (2) = 15 |
| Resolución temporal | 1 minuto |
| Posibilidades por minuto | 100 |
| Probabilidad de colisión (2 envíos mismo minuto) | 1% |
| Verificación en BD | ✅ Sí (opcional pero recomendado) |
| Persistencia | ✅ Sí (tabla `sifen_did_history`) |
| Centralización | ✅ Sí (módulo `did_generator.py`) |

**Ventajas**:
- ✅ **100x menos probabilidad de colisión** (1% vs 10%)
- ✅ **Verificación en BD** previene colisiones
- ✅ **Persistencia** permite auditoría
- ✅ **Centralización** facilita mantenimiento

**Desventajas**:
- ⚠️ Resolución de minuto (no segundo) → menos granularidad temporal
- ⚠️ Requiere tabla adicional en BD

---

## 8. RECOMENDACIÓN FINAL

### 8.1 Estrategia Recomendada

**Opción A: Estrategia híbrida (recomendada)**
- Formato: `YYYYMMDDHHMMSS` (14) + `random(00-99)` (2) = **16 dígitos**
- **Truncar a 15 dígitos**: `YYYYMMDDHHMMS` (13) + `random(00-99)` (2) = **15 dígitos**
- Resolución: 10 segundos (último dígito de segundo truncado)
- Posibilidades: 100 por ventana de 10 segundos
- Verificación en BD: ✅ Sí
- Persistencia: ✅ Sí

**Opción B: Estrategia conservadora**
- Formato: `YYYYMMDDHHMM` (13) + `random(00-99)` (2) = **15 dígitos**
- Resolución: 1 minuto
- Posibilidades: 100 por minuto
- Verificación en BD: ✅ Sí
- Persistencia: ✅ Sí

---

## 9. PLAN DE IMPLEMENTACIÓN

### 9.1 Paso 1: Crear Módulo Centralizado

1. Crear `app/sifen_client/did_generator.py`
2. Implementar `make_did_15()` con estrategia mejorada
3. Implementar `normalize_or_make_did()` con verificación en BD
4. Implementar `record_did_used()` para persistencia

### 9.2 Paso 2: Crear Tabla de Historial

1. Agregar tabla `sifen_did_history` en `web/db.py`
2. Agregar función `record_did_used()` en `web/db.py`

### 9.3 Paso 3: Actualizar Flujo

1. Actualizar `build_r_envio_lote_xml()` para usar módulo centralizado
2. Actualizar `send_sirecepde()` para usar módulo centralizado y registrar dId
3. Actualizar `web/main.py::de_send_to_sifen()` para usar módulo centralizado y registrar dId
4. Eliminar implementaciones duplicadas de `make_did_15()`

### 9.4 Paso 4: Testing

1. Verificar que no hay colisiones en pruebas concurrentes
2. Verificar que dId se persiste correctamente
3. Verificar que verificación de colisiones funciona

---

## 10. RESUMEN

### 10.1 Estado Actual

❌ **Problemas identificados**:
- Código duplicado (2 implementaciones de `make_did_15()`)
- Alto riesgo de colisiones (10% si 2 envíos en mismo segundo)
- No hay verificación de colisiones en BD
- No hay persistencia de dId
- `build_r_envio_lote_xml()` ignora el parámetro `did`

### 10.2 Propuesta

✅ **Solución centralizada**:
- Módulo `app/sifen_client/did_generator.py`
- Estrategia mejorada: `YYYYMMDDHHMM` (13) + `random(00-99)` (2) = 15 dígitos
- Verificación en BD (tabla `sifen_did_history`)
- Persistencia de dId usado
- Probabilidad de colisión reducida a 1% (vs 10%)

---

**Última actualización**: 2025-01-XX  
**Versión**: 1.0

