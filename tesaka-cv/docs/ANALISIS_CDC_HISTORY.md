# Análisis: Guardado/Recordatorio de CDC Enviados

## Resumen Ejecutivo

Este documento identifica dónde se guarda/recuerda que un CDC ya fue enviado, y propone un diseño mínimo para prevenir reenvíos del mismo CDC.

---

## 1. ESTRUCTURAS EXISTENTES

### 1.1 Tabla `de_documents` (web/db.py)

**Archivo**: `web/db.py` (líneas 47-63)  
**Propósito**: Almacena documentos electrónicos

**Estructura**:
```sql
CREATE TABLE IF NOT EXISTS de_documents (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    cdc TEXT UNIQUE NOT NULL,  -- ⭐ UNIQUE en CDC
    ruc_emisor TEXT NOT NULL,
    timbrado TEXT NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    de_xml TEXT NOT NULL,
    sirecepde_xml TEXT,
    signed_xml TEXT,
    last_status TEXT,
    last_code TEXT,
    last_message TEXT,
    d_prot_cons_lote TEXT,
    approved_at TEXT,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
)
```

**Campos relevantes**:
- ✅ `cdc TEXT UNIQUE NOT NULL`: **Impide CDC duplicados** (a nivel de BD)
- ✅ `last_status`, `last_code`, `last_message`: Guardan respuesta de SIFEN
- ✅ `d_prot_cons_lote`: Guarda protocolo de consulta de lote
- ❌ **NO guarda `sent_at`**: No hay timestamp de cuándo se envió
- ❌ **NO guarda `last_dCodRes` explícitamente**: Solo en `last_code` (genérico)

**Uso**:
- `insert_document()` (línea 139): Inserta documento con CDC único
- Si CDC duplicado → `sqlite3.IntegrityError` → se regenera con `numero_documento + 1` (línea 562-578 en `web/main.py`)

**Limitaciones**:
1. **Solo se inserta al crear documento**, NO al enviarlo
2. **NO previene reenvío del mismo CDC** si el documento ya existe
3. **NO guarda historial de envíos** (solo el último estado)
4. **Clave única es solo CDC**, no (RUC + CDC)

---

### 1.2 Tabla `sifen_lotes` (web/lotes_db.py)

**Archivo**: `web/lotes_db.py` (líneas 41-55)  
**Propósito**: Almacena lotes enviados a SIFEN

**Estructura**:
```sql
CREATE TABLE IF NOT EXISTS sifen_lotes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    env TEXT NOT NULL CHECK(env IN ('test', 'prod')),
    d_prot_cons_lote TEXT NOT NULL UNIQUE,  -- ⭐ UNIQUE en d_prot_cons_lote
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

**Campos relevantes**:
- ✅ `d_prot_cons_lote TEXT NOT NULL UNIQUE`: **Impide lotes duplicados**
- ✅ `last_cod_res_lot`, `last_msg_res_lot`: Guardan respuesta de consulta de lote
- ❌ **NO guarda CDCs individuales**: Solo guarda `d_prot_cons_lote` (protocolo del lote)
- ❌ **NO previene reenvío del mismo CDC**: Solo previene lotes duplicados

**Uso**:
- `create_lote()` (línea 81): Crea lote con `d_prot_cons_lote` único
- Si lote duplicado → `ValueError("Lote ya existe")` (línea 120)

**Limitaciones**:
1. **Solo guarda lotes**, no CDCs individuales
2. **NO previene reenvío del mismo CDC** en un lote diferente
3. **NO guarda historial de envíos por CDC**

---

### 1.3 Artifacts JSON (tools/send_sirecepde.py)

**Archivo**: `tools/send_sirecepde.py` (líneas 4350-4386)  
**Propósito**: Guardar CDCs para fallback automático (0364)

**Estructura**:
```python
lote_data = {
    "dProtConsLote": str(d_prot_cons_lote),
    "cdcs": cdcs,  # Lista de CDCs del lote
    "timestamp": timestamp,
    "dId": str(did),
}
lote_file = artifacts_dir / f"lote_enviado_{timestamp}.json"
```

**Campos relevantes**:
- ✅ Guarda lista de CDCs por lote
- ✅ Guarda `dProtConsLote` y timestamp
- ❌ **Solo para fallback**, no para prevenir reenvíos
- ❌ **No es consultable** de forma eficiente (archivos JSON dispersos)
- ❌ **No tiene índice** ni búsqueda rápida

**Uso**:
- Se guarda cuando se envía un lote exitosamente (`dProtConsLote > 0`)
- Se usa en `tools/consulta_lote_de.py` para fallback automático por CDC (cuando `dCodResLot=0364`)

**Limitaciones**:
1. **No es una base de datos**: Solo archivos JSON en disco
2. **No previene reenvíos**: Solo guarda historial para consulta
3. **No es consultable eficientemente**: Requiere leer múltiples archivos JSON

---

## 2. ANÁLISIS: ¿IMPIDE REENVÍO DEL MISMO CDC?

### 2.1 En Creación de Documento

**Archivo**: `web/main.py` (líneas 548-585)

**Flujo**:
1. Se extrae CDC del XML
2. Se intenta `insert_document(cdc, ...)`
3. Si CDC duplicado → `sqlite3.IntegrityError`
4. Se regenera CDC con `numero_documento + 1`
5. Se reintenta insertar

**Resultado**: ✅ **Impide CDC duplicado en creación**, pero:
- Solo funciona si el documento se crea desde la web
- NO funciona si el documento ya existe y se intenta reenviar
- NO previene reenvío del mismo CDC desde CLI

---

### 2.2 En Envío a SIFEN

**Archivo**: `web/main.py` (líneas 607-796), `tools/send_sirecepde.py` (línea 3912)

**Flujo**:
1. Se obtiene documento existente (por `doc_id` o `xml_path`)
2. Se construye y firma el lote
3. Se envía a SIFEN
4. Se actualiza estado: `update_document_status(doc_id, status, code, message, ...)`

**Resultado**: ❌ **NO impide reenvío del mismo CDC**
- No hay verificación antes de enviar
- No hay tabla que registre "este CDC ya fue enviado"
- El mismo CDC puede enviarse múltiples veces (causando `dCodRes=0301`)

---

### 2.3 En Creación de Lote

**Archivo**: `web/main.py` (líneas 764-795), `web/lotes_db.py` (línea 81)

**Flujo**:
1. Se recibe `dProtConsLote` de SIFEN
2. Se intenta `create_lote(env, d_prot_cons_lote, de_document_id)`
3. Si lote duplicado → `ValueError("Lote ya existe")`

**Resultado**: ✅ **Impide lotes duplicados**, pero:
- Solo previene lotes duplicados (mismo `dProtConsLote`)
- NO previene reenvío del mismo CDC en un lote diferente
- NO previene reenvío si `dProtConsLote=0` (no se crea lote)

---

## 3. PROBLEMA IDENTIFICADO

### 3.1 No Hay Prevención de Reenvío de CDC

**Escenario problemático**:
1. Usuario envía CDC `1234567890...` → `dCodRes=0301` (no encolado)
2. Usuario intenta reenviar el mismo CDC → **NO hay verificación**
3. SIFEN rechaza nuevamente con `dCodRes=0301` → spam a SIFEN

**Causa raíz**:
- La tabla `de_documents` tiene `cdc UNIQUE`, pero:
  - Solo se inserta al **crear** documento, no al **enviarlo**
  - Si el documento ya existe, se puede reenviar sin verificación
- No hay tabla que registre **historial de envíos por CDC**

---

## 4. PROPUESTA: Tabla `sifen_cdc_history`

### 4.1 Diseño Mínimo

**Ubicación**: `web/db.py` (agregar nueva tabla)

**Estructura propuesta**:
```sql
CREATE TABLE IF NOT EXISTS sifen_cdc_history (
    -- Clave compuesta: RUC + CDC (el mismo CDC puede existir para diferentes RUCs)
    ruc_emisor TEXT NOT NULL,
    cdc TEXT NOT NULL,
    
    -- Timestamps
    first_sent_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    last_sent_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    
    -- Respuesta de SIFEN (última)
    last_dCodRes TEXT,
    last_dMsgRes TEXT,
    last_dProtConsLote TEXT,
    
    -- Contadores
    send_count INTEGER DEFAULT 1,
    
    -- Metadata
    env TEXT NOT NULL CHECK(env IN ('test', 'prod')),
    last_dId TEXT,  -- dId del último envío
    
    -- Clave primaria compuesta
    PRIMARY KEY (ruc_emisor, cdc, env)
);

-- Índices para búsquedas frecuentes
CREATE INDEX IF NOT EXISTS idx_sifen_cdc_history_cdc 
ON sifen_cdc_history(cdc);

CREATE INDEX IF NOT EXISTS idx_sifen_cdc_history_ruc_cdc 
ON sifen_cdc_history(ruc_emisor, cdc);

CREATE INDEX IF NOT EXISTS idx_sifen_cdc_history_last_sent 
ON sifen_cdc_history(last_sent_at DESC);
```

**Justificación del diseño**:
1. **Clave compuesta `(ruc_emisor, cdc, env)`**:
   - El mismo CDC puede existir para diferentes RUCs (diferentes emisores)
   - Diferentes ambientes (test/prod) pueden tener el mismo CDC
   - Previene reenvío del mismo CDC por el mismo RUC en el mismo ambiente

2. **`first_sent_at` y `last_sent_at`**:
   - `first_sent_at`: Primera vez que se envió este CDC
   - `last_sent_at`: Última vez que se intentó enviar
   - Permite calcular cooldown (ej: no reenviar si se envió hace < 5 minutos)

3. **`last_dCodRes`, `last_dMsgRes`, `last_dProtConsLote`**:
   - Guarda la última respuesta de SIFEN
   - Permite verificar si el último envío fue exitoso (`0300`) o fallido (`0301`)
   - Permite decidir si se debe reenviar o no

4. **`send_count`**:
   - Contador de cuántas veces se intentó enviar este CDC
   - Útil para métricas y alertas (si `send_count > 3` → posible problema)

5. **`env`**:
   - Diferencia entre test y prod
   - Permite tener historial separado por ambiente

---

### 4.2 Funciones de API

**Archivo**: `web/db.py` (agregar nuevas funciones)

#### 4.2.1 `record_cdc_sent()`

```python
def record_cdc_sent(
    ruc_emisor: str,
    cdc: str,
    env: str,
    dCodRes: Optional[str] = None,
    dMsgRes: Optional[str] = None,
    dProtConsLote: Optional[str] = None,
    dId: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Registra o actualiza el historial de envío de un CDC.
    
    Si el CDC ya existe, actualiza last_sent_at, send_count, y campos de respuesta.
    Si no existe, crea un nuevo registro con first_sent_at = last_sent_at.
    
    Returns:
        Dict con información del registro (first_sent_at, last_sent_at, send_count, etc.)
    """
    conn = get_conn()
    cursor = conn.cursor()
    
    # Verificar si ya existe
    cursor.execute("""
        SELECT first_sent_at, last_sent_at, send_count
        FROM sifen_cdc_history
        WHERE ruc_emisor = ? AND cdc = ? AND env = ?
    """, (ruc_emisor, cdc, env))
    existing = cursor.fetchone()
    
    if existing:
        # Actualizar registro existente
        first_sent_at = existing[0]
        old_send_count = existing[2]
        new_send_count = old_send_count + 1
        
        cursor.execute("""
            UPDATE sifen_cdc_history
            SET 
                last_sent_at = CURRENT_TIMESTAMP,
                send_count = ?,
                last_dCodRes = ?,
                last_dMsgRes = ?,
                last_dProtConsLote = ?,
                last_dId = ?
            WHERE ruc_emisor = ? AND cdc = ? AND env = ?
        """, (new_send_count, dCodRes, dMsgRes, dProtConsLote, dId, ruc_emisor, cdc, env))
    else:
        # Crear nuevo registro
        cursor.execute("""
            INSERT INTO sifen_cdc_history (
                ruc_emisor, cdc, env,
                first_sent_at, last_sent_at,
                last_dCodRes, last_dMsgRes, last_dProtConsLote, last_dId,
                send_count
            )
            VALUES (?, ?, ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP, ?, ?, ?, ?, 1)
        """, (ruc_emisor, cdc, env, dCodRes, dMsgRes, dProtConsLote, dId))
        first_sent_at = None
    
    conn.commit()
    
    # Obtener registro actualizado
    cursor.execute("""
        SELECT * FROM sifen_cdc_history
        WHERE ruc_emisor = ? AND cdc = ? AND env = ?
    """, (ruc_emisor, cdc, env))
    row = cursor.fetchone()
    conn.close()
    
    return _row_to_dict(row) if row else None
```

#### 4.2.2 `get_cdc_history()`

```python
def get_cdc_history(
    ruc_emisor: str,
    cdc: str,
    env: str,
) -> Optional[Dict[str, Any]]:
    """
    Obtiene el historial de envío de un CDC.
    
    Returns:
        Dict con historial o None si no existe
    """
    conn = get_conn()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT * FROM sifen_cdc_history
        WHERE ruc_emisor = ? AND cdc = ? AND env = ?
    """, (ruc_emisor, cdc, env))
    row = cursor.fetchone()
    conn.close()
    return _row_to_dict(row) if row else None
```

#### 4.2.3 `should_allow_resend()`

```python
def should_allow_resend(
    ruc_emisor: str,
    cdc: str,
    env: str,
    cooldown_seconds: int = 300,  # 5 minutos por defecto
) -> Tuple[bool, Optional[str]]:
    """
    Determina si se debe permitir reenvío de un CDC.
    
    Args:
        ruc_emisor: RUC del emisor
        cdc: CDC a verificar
        env: Ambiente (test/prod)
        cooldown_seconds: Segundos mínimos entre envíos (default: 300 = 5 min)
    
    Returns:
        Tupla (allow, reason)
        - allow: True si se permite reenvío, False si no
        - reason: Razón si no se permite (opcional)
    """
    history = get_cdc_history(ruc_emisor, cdc, env)
    
    if not history:
        # Nunca se envió → permitir
        return True, None
    
    # Verificar cooldown
    last_sent = datetime.fromisoformat(history["last_sent_at"].replace("Z", "+00:00"))
    now = datetime.utcnow()
    elapsed = (now - last_sent.replace(tzinfo=None)).total_seconds()
    
    if elapsed < cooldown_seconds:
        return False, f"Cooldown activo: último envío hace {elapsed:.0f}s (mínimo {cooldown_seconds}s)"
    
    # Verificar último código de respuesta
    last_dCodRes = history.get("last_dCodRes")
    if last_dCodRes == "0301":
        # Lote no encolado → no tiene sentido reenviar inmediatamente
        # Pero permitir si pasó el cooldown (puede ser un problema temporal)
        return True, None
    
    # Permitir reenvío
    return True, None
```

---

### 4.3 Integración en Flujo de Envío

#### 4.3.1 En `web/main.py::de_send_to_sifen()`

**Agregar antes de enviar** (línea ~683):
```python
# Verificar si se permite reenvío
from web.db import should_allow_resend, record_cdc_sent

# Extraer RUC y CDC del documento
ruc_emisor = document.get('ruc_emisor')
cdc = document.get('cdc')

if ruc_emisor and cdc:
    allow, reason = should_allow_resend(ruc_emisor, cdc, env, cooldown_seconds=300)
    if not allow:
        error_msg = f"BLOQUEADO: No se permite reenvío del CDC {cdc[:20]}... {reason}"
        db.update_document_status(doc_id, status="error", message=error_msg)
        return RedirectResponse(url=f"/de/{doc_id}?error=1", status_code=303)

# ... continuar con envío ...

# Después de recibir respuesta (línea ~741):
# Registrar envío en historial
if ruc_emisor and cdc:
    record_cdc_sent(
        ruc_emisor=ruc_emisor,
        cdc=cdc,
        env=env,
        dCodRes=d_cod_res,
        dMsgRes=d_msg_res,
        dProtConsLote=d_prot_cons_lote,
        dId=str(did) if 'did' in locals() else None,
    )
```

#### 4.3.2 En `tools/send_sirecepde.py::send_sirecepde()`

**Agregar antes de enviar** (línea ~4032):
```python
# Extraer RUC y CDC del XML
from web.db import should_allow_resend, record_cdc_sent

try:
    xml_root = etree.fromstring(xml_bytes)
    # Buscar RUC y CDC
    ruc_emisor = None
    cdc = None
    
    # Buscar RUC (dRucEm o similar)
    ruc_elem = xml_root.find(".//{http://ekuatia.set.gov.py/sifen/xsd}dRucEm")
    if ruc_elem is None:
        ruc_elem = xml_root.find(".//dRucEm")
    if ruc_elem is not None:
        ruc_emisor = ruc_elem.text.strip()
    
    # Buscar CDC (DE@Id)
    de_elem = xml_root.find(".//{http://ekuatia.set.gov.py/sifen/xsd}DE")
    if de_elem is None:
        de_elem = xml_root.find(".//DE")
    if de_elem is not None:
        cdc = de_elem.get("Id") or de_elem.get("id")
    
    if ruc_emisor and cdc:
        allow, reason = should_allow_resend(ruc_emisor, cdc, env, cooldown_seconds=300)
        if not allow:
            return {
                "success": False,
                "error": f"BLOQUEADO: No se permite reenvío del CDC {cdc[:20]}... {reason}",
                "error_type": "ResendBlocked"
            }
except Exception:
    # Si no se puede extraer, continuar (no crítico)
    pass

# ... continuar con envío ...

# Después de recibir respuesta (línea ~4345):
# Registrar envío en historial
if ruc_emisor and cdc:
    try:
        record_cdc_sent(
            ruc_emisor=ruc_emisor,
            cdc=cdc,
            env=env,
            dCodRes=codigo_respuesta,
            dMsgRes=response.get('mensaje'),
            dProtConsLote=d_prot_cons_lote,
            dId=str(did) if 'did' in locals() else None,
        )
    except Exception as e:
        # No crítico si falla el registro
        if debug_enabled:
            print(f"⚠️  Error al registrar CDC en historial: {e}")
```

---

## 5. BENEFICIOS

### 5.1 Prevención de Reenvíos

✅ **Impide reenvío del mismo CDC** dentro del cooldown (default: 5 minutos)  
✅ **Registra historial completo** de envíos por CDC  
✅ **Permite métricas** (cuántas veces se intentó enviar un CDC)

### 5.2 Diagnóstico

✅ **Historial de respuestas**: Ver qué `dCodRes` se recibió la última vez  
✅ **Detección de problemas**: Si `send_count > 3` → posible problema con el CDC  
✅ **Cooldown inteligente**: No reenviar inmediatamente después de `0301`

### 5.3 Compatibilidad

✅ **No rompe flujo existente**: Solo agrega verificación opcional  
✅ **Backward compatible**: Si no se puede extraer RUC/CDC, continúa sin bloquear  
✅ **Mismo esquema de BD**: SQLite, mismo archivo `tesaka.db`

---

## 6. MIGRACIÓN

### 6.1 Script de Migración

**Archivo**: `web/db.py` (agregar en `get_conn()`)

```python
def get_conn():
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    
    # ... crear otras tablas ...
    
    # Crear tabla sifen_cdc_history si no existe
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS sifen_cdc_history (
            ruc_emisor TEXT NOT NULL,
            cdc TEXT NOT NULL,
            first_sent_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
            last_sent_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
            last_dCodRes TEXT,
            last_dMsgRes TEXT,
            last_dProtConsLote TEXT,
            send_count INTEGER DEFAULT 1,
            env TEXT NOT NULL CHECK(env IN ('test', 'prod')),
            last_dId TEXT,
            PRIMARY KEY (ruc_emisor, cdc, env)
        )
    """)
    
    # Crear índices
    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_sifen_cdc_history_cdc 
        ON sifen_cdc_history(cdc)
    """)
    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_sifen_cdc_history_ruc_cdc 
        ON sifen_cdc_history(ruc_emisor, cdc)
    """)
    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_sifen_cdc_history_last_sent 
        ON sifen_cdc_history(last_sent_at DESC)
    """)
    
    conn.commit()
    return conn
```

### 6.2 Backfill de Datos Existentes

**Script opcional**: `tools/backfill_cdc_history.py`

```python
"""
Script para poblar sifen_cdc_history con datos existentes de de_documents.
"""
from web.db import get_conn, record_cdc_sent
from lxml import etree

def backfill_from_documents():
    """Pobla sifen_cdc_history desde de_documents existentes."""
    conn = get_conn()
    cursor = conn.cursor()
    
    # Obtener documentos que fueron enviados (tienen last_code)
    cursor.execute("""
        SELECT id, cdc, ruc_emisor, last_code, last_message, d_prot_cons_lote
        FROM de_documents
        WHERE last_code IS NOT NULL
    """)
    
    for row in cursor.fetchall():
        doc_id = row[0]
        cdc = row[1]
        ruc_emisor = row[2]
        last_code = row[3]
        last_message = row[4]
        d_prot_cons_lote = row[5]
        
        # Determinar ambiente (asumir 'test' por defecto, o desde env var)
        env = os.getenv("SIFEN_ENV", "test")
        
        # Registrar en historial
        try:
            record_cdc_sent(
                ruc_emisor=ruc_emisor,
                cdc=cdc,
                env=env,
                dCodRes=last_code,
                dMsgRes=last_message,
                dProtConsLote=d_prot_cons_lote,
            )
            print(f"✅ Registrado: CDC {cdc[:20]}... (doc_id={doc_id})")
        except Exception as e:
            print(f"❌ Error al registrar CDC {cdc[:20]}...: {e}")
    
    conn.close()

if __name__ == "__main__":
    backfill_from_documents()
```

---

## 7. RESUMEN

### 7.1 Estructuras Existentes

| Estructura | Ubicación | Impide Reenvío CDC? | Guarda Historial? |
|------------|-----------|---------------------|-------------------|
| `de_documents.cdc UNIQUE` | `web/db.py` | ❌ Solo en creación | ❌ Solo último estado |
| `sifen_lotes.d_prot_cons_lote UNIQUE` | `web/lotes_db.py` | ❌ Solo lotes | ❌ Solo último estado |
| `lote_enviado_*.json` | `artifacts/` | ❌ Solo para fallback | ✅ Pero no consultable |

### 7.2 Propuesta

✅ **Nueva tabla `sifen_cdc_history`**:
- Clave: `(ruc_emisor, cdc, env)` → **Impide reenvío del mismo CDC por el mismo RUC**
- Campos: `first_sent_at`, `last_sent_at`, `last_dCodRes`, `last_dProtConsLote`, `send_count`
- Funciones: `record_cdc_sent()`, `get_cdc_history()`, `should_allow_resend()`
- Integración: Verificación antes de enviar, registro después de recibir respuesta

---

**Última actualización**: 2025-01-XX  
**Versión**: 1.0

