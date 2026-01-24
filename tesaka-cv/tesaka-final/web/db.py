"""
Conexión a base de datos SQLite para TESAKA-SIFEN
"""
import sqlite3
from pathlib import Path
from typing import Optional, List, Dict, Any
from datetime import datetime

# Ruta de la base de datos (mismo que app/db.py)
DB_PATH = Path(__file__).parent.parent / "tesaka.db"


def ensure_tables(conn: sqlite3.Connection):
    """
    Asegura que todas las tablas necesarias existan.
    Crea doc_counters si no existe.
    """
    cursor = conn.cursor()
    
    # Crear tabla de contadores si no existe
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS doc_counters (
            env TEXT NOT NULL,
            timbrado TEXT NOT NULL,
            establecimiento TEXT NOT NULL,
            punto_expedicion TEXT NOT NULL,
            tipo_documento TEXT NOT NULL,
            last_num INTEGER NOT NULL DEFAULT 0,
            updated_at TEXT NOT NULL DEFAULT (datetime('now')),
            PRIMARY KEY (env, timbrado, establecimiento, punto_expedicion, tipo_documento)
        )
    """)
    conn.commit()


def get_conn():
    """
    Obtiene una conexión a SQLite.
    Crea las tablas necesarias si no existen.
    """
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    
    # Crear tabla de documentos si no existe
    cursor = conn.cursor()
    cursor.execute("""
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
            d_prot_cons_lote TEXT,
            approved_at TEXT,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    
    # Migración: agregar columnas nuevas si no existen (SQLite no soporta ALTER COLUMN)
    # IMPORTANTE: SQLite no permite DEFAULT con expresiones no-constantes en ALTER TABLE ADD COLUMN
    # Por lo tanto, agregamos columnas SIN DEFAULT y luego hacemos backfill
    cursor.execute("PRAGMA table_info(de_documents)")
    existing_columns = [row[1] for row in cursor.fetchall()]
    
    columns_added = False
    
    if "d_prot_cons_lote" not in existing_columns:
        cursor.execute("ALTER TABLE de_documents ADD COLUMN d_prot_cons_lote TEXT")
        columns_added = True
    
    if "approved_at" not in existing_columns:
        cursor.execute("ALTER TABLE de_documents ADD COLUMN approved_at TEXT")
        columns_added = True
    
    if "updated_at" not in existing_columns:
        # Agregar SIN DEFAULT (SQLite no permite DEFAULT no-constante en ALTER TABLE)
        cursor.execute("ALTER TABLE de_documents ADD COLUMN updated_at TEXT")
        columns_added = True
    
    # Backfill: setear updated_at para filas existentes que no lo tengan
    # Usar CURRENT_TIMESTAMP en UPDATE está permitido (no es DEFAULT en ALTER TABLE)
    if columns_added:
        cursor.execute("""
            UPDATE de_documents 
            SET updated_at = COALESCE(updated_at, CURRENT_TIMESTAMP)
            WHERE updated_at IS NULL
        """)
    
    conn.commit()
    
    # Asegurar que todas las tablas existan
    ensure_tables(conn)
    
    return conn


def _row_to_dict(row: sqlite3.Row) -> Dict[str, Any]:
    """Convierte un Row de SQLite a dict"""
    if row is None:
        return None
    return dict(row)


def list_documents(limit: int = 50) -> List[Dict[str, Any]]:
    """
    Lista documentos ordenados por id DESC (últimos primero).
    
    Returns:
        Lista de documentos con: id, cdc, timbrado, created_at, last_status
    """
    try:
        conn = get_conn()
        cursor = conn.cursor()
        cursor.execute("""
            SELECT 
                id,
                cdc,
                timbrado,
                created_at,
                last_status
            FROM de_documents
            ORDER BY id DESC
            LIMIT ?
        """, (limit,))
        rows = cursor.fetchall()
        conn.close()
        return [_row_to_dict(row) for row in rows]
    except Exception as e:
        # Re-raise con contexto para mejor debugging
        raise ConnectionError(f"Error al consultar SQLite: {e}") from e


def insert_document(cdc: str, ruc_emisor: str, timbrado: str, de_xml: str) -> int:
    """
    Inserta un nuevo documento en la base de datos.
    
    Returns:
        ID del documento insertado
    """
    try:
        conn = get_conn()
        cursor = conn.cursor()
        # Importar constantes de estado
        from .document_status import STATUS_SIGNED_LOCAL
        
        # Setear updated_at desde Python (formato ISO UTC con Z, sin microsegundos)
        updated_at = datetime.utcnow().replace(microsecond=0).isoformat() + "Z"
        
        cursor.execute("""
            INSERT INTO de_documents (cdc, ruc_emisor, timbrado, de_xml, last_status, updated_at)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (cdc, ruc_emisor, timbrado, de_xml, STATUS_SIGNED_LOCAL, updated_at))
        doc_id = cursor.lastrowid
        conn.commit()
        conn.close()
        return doc_id
    except sqlite3.IntegrityError as e:
        # Unique violation (CDC duplicado)
        conn.close()
        raise ConnectionError(f"CDC duplicado: {e}") from e
    except Exception as e:
        conn.close()
        # Re-raise con contexto
        raise ConnectionError(f"Error al insertar documento en SQLite: {e}") from e


def get_document(doc_id: int) -> Optional[Dict[str, Any]]:
    """
    Obtiene un documento por ID con todos sus campos.
    
    Returns:
        Documento con todos los campos o None si no existe
    """
    try:
        conn = get_conn()
        cursor = conn.cursor()
        cursor.execute("""
            SELECT *
            FROM de_documents
            WHERE id = ?
        """, (doc_id,))
        row = cursor.fetchone()
        conn.close()
        return _row_to_dict(row) if row else None
    except Exception as e:
        conn.close()
        # Re-raise con contexto
        raise ConnectionError(f"Error al obtener documento de SQLite: {e}") from e


def update_document_status(
    doc_id: int,
    status: str,
    code: Optional[str] = None,
    message: Optional[str] = None,
    sirecepde_xml: Optional[str] = None,
    signed_xml: Optional[str] = None,
    d_prot_cons_lote: Optional[str] = None,
    approved_at: Optional[str] = None
) -> bool:
    """
    Actualiza el estado y respuesta de un documento después de enviarlo a SIFEN.
    
    Args:
        doc_id: ID del documento
        status: Nuevo estado (debe ser uno de los estados válidos de document_status)
        code: Código de respuesta de SIFEN (opcional)
        message: Mensaje de respuesta de SIFEN (opcional)
        sirecepde_xml: XML de siRecepDE enviado (opcional)
        signed_xml: XML firmado (opcional)
        d_prot_cons_lote: Número de protocolo de consulta de lote (opcional)
        approved_at: Fecha/hora de aprobación por SIFEN (opcional, formato ISO)
    
    Returns:
        True si se actualizó correctamente, False si no se encontró el documento
    """
    try:
        conn = get_conn()
        cursor = conn.cursor()
        
        # Construir UPDATE dinámicamente según los campos proporcionados
        # Setear updated_at desde Python (formato ISO UTC con Z, sin microsegundos)
        updated_at = datetime.utcnow().replace(microsecond=0).isoformat() + "Z"
        updates = ["last_status = ?", "updated_at = ?"]
        params = [status, updated_at]
        
        if code is not None:
            updates.append("last_code = ?")
            params.append(code)
        
        if message is not None:
            updates.append("last_message = ?")
            params.append(message)
        
        if sirecepde_xml is not None:
            updates.append("sirecepde_xml = ?")
            params.append(sirecepde_xml)
        
        if signed_xml is not None:
            updates.append("signed_xml = ?")
            params.append(signed_xml)
        
        if d_prot_cons_lote is not None:
            updates.append("d_prot_cons_lote = ?")
            params.append(d_prot_cons_lote)
        
        if approved_at is not None:
            updates.append("approved_at = ?")
            params.append(approved_at)
        
        params.append(doc_id)
        
        cursor.execute(f"""
            UPDATE de_documents
            SET {', '.join(updates)}
            WHERE id = ?
        """, params)
        
        updated = cursor.rowcount > 0
        conn.commit()
        conn.close()
        return updated
    except Exception as e:
        conn.close()
        raise ConnectionError(f"Error al actualizar estado del documento: {e}") from e
