"""
Gestión de base de datos para lotes SIFEN
"""
import sqlite3
from pathlib import Path
from typing import Optional, List, Dict, Any
from datetime import datetime

# Ruta de la base de datos (mismo que web/db.py)
DB_PATH = Path(__file__).parent.parent / "tesaka.db"

# Estados válidos para lotes
LOTE_STATUS_PENDING = "pending"
LOTE_STATUS_PROCESSING = "processing"
LOTE_STATUS_DONE = "done"
LOTE_STATUS_EXPIRED_WINDOW = "expired_window"
LOTE_STATUS_REQUIRES_CDC = "requires_cdc"
LOTE_STATUS_ERROR = "error"

VALID_STATUSES = [
    LOTE_STATUS_PENDING,
    LOTE_STATUS_PROCESSING,
    LOTE_STATUS_DONE,
    LOTE_STATUS_EXPIRED_WINDOW,
    LOTE_STATUS_REQUIRES_CDC,
    LOTE_STATUS_ERROR,
]


def get_conn():
    """
    Obtiene una conexión a SQLite.
    Crea la tabla sifen_lotes si no existe.
    """
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row

    # Crear tabla si no existe
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS sifen_lotes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            env TEXT NOT NULL CHECK(env IN ('test', 'prod')),
            d_prot_cons_lote TEXT NOT NULL UNIQUE,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            last_checked_at TIMESTAMP,
            last_cod_res_lot TEXT,
            last_msg_res_lot TEXT,
            last_response_xml TEXT,
            status TEXT NOT NULL DEFAULT 'pending' CHECK(status IN ('pending', 'processing', 'done', 'expired_window', 'requires_cdc', 'error')),
            attempts INTEGER DEFAULT 0,
            de_document_id INTEGER,
            FOREIGN KEY (de_document_id) REFERENCES de_documents(id)
        )
    """)
    # Índices para búsquedas frecuentes
    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_sifen_lotes_status 
        ON sifen_lotes(status)
    """)
    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_sifen_lotes_env_status 
        ON sifen_lotes(env, status)
    """)
    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_sifen_lotes_de_document_id 
        ON sifen_lotes(de_document_id)
    """)
    conn.commit()

    return conn


def _row_to_dict(row: sqlite3.Row) -> Optional[Dict[str, Any]]:
    """Convierte un Row de SQLite a dict"""
    if row is None:
        return None
    return dict(row)


def create_lote(
    env: str,
    d_prot_cons_lote: str,
    de_document_id: Optional[int] = None,
) -> int:
    """
    Crea un nuevo registro de lote.

    Args:
        env: Ambiente ('test' o 'prod')
        d_prot_cons_lote: Número de lote devuelto por SIFEN
        de_document_id: ID del documento relacionado (opcional)

    Returns:
        ID del lote creado

    Raises:
        ValueError: Si d_prot_cons_lote no es solo dígitos
        sqlite3.IntegrityError: Si el lote ya existe
    """
    # Validar que d_prot_cons_lote sea solo dígitos
    if not d_prot_cons_lote or not d_prot_cons_lote.strip().isdigit():
        raise ValueError(
            f"dProtConsLote debe ser solo dígitos. Valor recibido: '{d_prot_cons_lote}'"
        )

    try:
        conn = get_conn()
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO sifen_lotes (env, d_prot_cons_lote, de_document_id, status)
            VALUES (?, ?, ?, ?)
        """, (env, d_prot_cons_lote.strip(), de_document_id, LOTE_STATUS_PENDING))
        lote_id = cursor.lastrowid
        conn.commit()
        conn.close()
        return lote_id
    except sqlite3.IntegrityError as e:
        conn.close()
        raise ValueError(f"Lote ya existe: {d_prot_cons_lote}") from e
    except Exception as e:
        conn.close()
        raise ConnectionError(f"Error al crear lote: {e}") from e


def update_lote_status(
    lote_id: int,
    status: str,
    cod_res_lot: Optional[str] = None,
    msg_res_lot: Optional[str] = None,
    response_xml: Optional[str] = None,
) -> bool:
    """
    Actualiza el estado de un lote después de consultarlo.

    Args:
        lote_id: ID del lote
        status: Nuevo estado
        cod_res_lot: Código de respuesta del lote (opcional)
        msg_res_lot: Mensaje de respuesta del lote (opcional)
        response_xml: XML de respuesta completo (opcional)

    Returns:
        True si se actualizó correctamente, False si no se encontró
    """
    if status not in VALID_STATUSES:
        raise ValueError(f"Estado inválido: {status}. Válidos: {VALID_STATUSES}")

    try:
        conn = get_conn()
        cursor = conn.cursor()

        updates = ["status = ?", "last_checked_at = CURRENT_TIMESTAMP", "attempts = attempts + 1"]
        params = [status]

        if cod_res_lot is not None:
            updates.append("last_cod_res_lot = ?")
            params.append(cod_res_lot)

        if msg_res_lot is not None:
            updates.append("last_msg_res_lot = ?")
            params.append(msg_res_lot)

        if response_xml is not None:
            updates.append("last_response_xml = ?")
            params.append(response_xml)

        params.append(lote_id)

        cursor.execute(
            f"""
            UPDATE sifen_lotes
            SET {', '.join(updates)}
            WHERE id = ?
            """,
            params,
        )

        updated = cursor.rowcount > 0
        conn.commit()
        conn.close()
        return updated
    except Exception as e:
        conn.close()
        raise ConnectionError(f"Error al actualizar estado del lote: {e}") from e


def get_lote(lote_id: int) -> Optional[Dict[str, Any]]:
    """
    Obtiene un lote por ID con todos sus campos.

    Returns:
        Lote con todos los campos o None si no existe
    """
    try:
        conn = get_conn()
        cursor = conn.cursor()
        cursor.execute("""
            SELECT *
            FROM sifen_lotes
            WHERE id = ?
        """, (lote_id,))
        row = cursor.fetchone()
        conn.close()
        return _row_to_dict(row) if row else None
    except Exception as e:
        conn.close()
        raise ConnectionError(f"Error al obtener lote: {e}") from e


def get_lote_by_prot(env: str, d_prot_cons_lote: str) -> Optional[Dict[str, Any]]:
    """
    Obtiene un lote por ambiente y número de lote.

    Returns:
        Lote con todos los campos o None si no existe
    """
    try:
        conn = get_conn()
        cursor = conn.cursor()
        cursor.execute("""
            SELECT *
            FROM sifen_lotes
            WHERE env = ? AND d_prot_cons_lote = ?
        """, (env, d_prot_cons_lote))
        row = cursor.fetchone()
        conn.close()
        return _row_to_dict(row) if row else None
    except Exception as e:
        conn.close()
        raise ConnectionError(f"Error al obtener lote: {e}") from e


def list_lotes(
    env: Optional[str] = None,
    status: Optional[str] = None,
    limit: int = 50,
) -> List[Dict[str, Any]]:
    """
    Lista lotes con filtros opcionales.

    Args:
        env: Filtrar por ambiente (opcional)
        status: Filtrar por estado (opcional)
        limit: Límite de resultados

    Returns:
        Lista de lotes ordenados por id DESC (últimos primero)
    """
    try:
        conn = get_conn()
        cursor = conn.cursor()

        query = "SELECT * FROM sifen_lotes WHERE 1=1"
        params = []

        if env:
            query += " AND env = ?"
            params.append(env)

        if status:
            query += " AND status = ?"
            params.append(status)

        query += " ORDER BY id DESC LIMIT ?"
        params.append(limit)

        cursor.execute(query, params)
        rows = cursor.fetchall()
        conn.close()
        return [_row_to_dict(row) for row in rows]
    except Exception as e:
        conn.close()
        raise ConnectionError(f"Error al listar lotes: {e}") from e


def get_lotes_pending_check(
    env: Optional[str] = None,
    max_attempts: Optional[int] = None,
) -> List[Dict[str, Any]]:
    """
    Obtiene lotes que necesitan ser consultados (pending o processing).

    Args:
        env: Filtrar por ambiente (opcional)
        max_attempts: Máximo número de intentos (opcional)

    Returns:
        Lista de lotes que necesitan consulta
    """
    try:
        conn = get_conn()
        cursor = conn.cursor()

        query = """
            SELECT * FROM sifen_lotes
            WHERE status IN ('pending', 'processing')
        """
        params = []

        if env:
            query += " AND env = ?"
            params.append(env)

        if max_attempts is not None:
            query += " AND attempts < ?"
            params.append(max_attempts)

        query += " ORDER BY created_at ASC"

        cursor.execute(query, params)
        rows = cursor.fetchall()
        conn.close()
        return [_row_to_dict(row) for row in rows]
    except Exception as e:
        conn.close()
        raise ConnectionError(f"Error al obtener lotes pendientes: {e}") from e

