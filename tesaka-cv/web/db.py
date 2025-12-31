"""
Conexión a base de datos SQLite para TESAKA-SIFEN
"""
import sqlite3
from pathlib import Path
from typing import Optional, List, Dict, Any

# Ruta de la base de datos (mismo que app/db.py)
DB_PATH = Path(__file__).parent.parent / "tesaka.db"


def get_conn():
    """
    Obtiene una conexión a SQLite.
    Crea la tabla de_documents si no existe.
    """
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    
    # Crear tabla si no existe
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
            last_message TEXT
        )
    """)
    conn.commit()
    
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
        cursor.execute("""
            INSERT INTO de_documents (cdc, ruc_emisor, timbrado, de_xml, last_status)
            VALUES (?, ?, ?, ?, 'pending')
        """, (cdc, ruc_emisor, timbrado, de_xml))
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
    signed_xml: Optional[str] = None
) -> bool:
    """
    Actualiza el estado y respuesta de un documento después de enviarlo a SIFEN.
    
    Args:
        doc_id: ID del documento
        status: Nuevo estado (ej: 'sent', 'approved', 'rejected', 'error')
        code: Código de respuesta de SIFEN (opcional)
        message: Mensaje de respuesta de SIFEN (opcional)
        sirecepde_xml: XML de siRecepDE enviado (opcional)
        signed_xml: XML firmado (opcional)
    
    Returns:
        True si se actualizó correctamente, False si no se encontró el documento
    """
    try:
        conn = get_conn()
        cursor = conn.cursor()
        
        # Construir UPDATE dinámicamente según los campos proporcionados
        updates = ["last_status = ?"]
        params = [status]
        
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
