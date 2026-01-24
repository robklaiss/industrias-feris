"""
Módulo para manejo de contadores secuenciales de documentos SIFEN.
"""
import sqlite3
from datetime import datetime
from typing import Optional


def next_dnumdoc(
    conn: sqlite3.Connection,
    *,
    env: str,
    timbrado: str,
    est: str,
    punexp: str,
    tipode: str,
    requested: Optional[int],
) -> int:
    """
    Devuelve el próximo número (entero) y actualiza doc_counters en una transacción con lock.
    
    Reglas:
    - 1ra vez: usa requested si >0, sino 1
    - Con contador: si requested > last_num => requested, sino last_num + 1
    
    Args:
        conn: Conexión SQLite (debe estar abierta)
        env: Ambiente (test/prod)
        timbrado: Número de timbrado (8 dígitos)
        est: Establecimiento (3 dígitos)
        punexp: Punto de expedición (3 dígitos)
        tipode: Tipo de documento (ej: "1" para factura electrónica)
        requested: Número solicitado por el usuario (opcional)
        
    Returns:
        Próximo número de documento (entero)
        
    Raises:
        Exception: Si falla la transacción (se hace rollback automático)
    """
    conn.execute("BEGIN IMMEDIATE")
    try:
        row = conn.execute(
            """SELECT last_num FROM doc_counters
               WHERE env=? AND timbrado=? AND establecimiento=? AND punto_expedicion=? AND tipo_documento=?""",
            (env, timbrado, est, punexp, tipode),
        ).fetchone()

        if row is None:
            # Primera vez para esta serie
            if requested is not None and requested > 0:
                next_num = requested
            else:
                next_num = 1

            conn.execute(
                """INSERT INTO doc_counters(env,timbrado,establecimiento,punto_expedicion,tipo_documento,last_num,updated_at)
                   VALUES(?,?,?,?,?,?,?)""",
                (env, timbrado, est, punexp, tipode, next_num, datetime.now().isoformat()),
            )
        else:
            # Ya existe contador
            last_num = int(row[0])
            if requested is not None and requested > last_num:
                next_num = requested
            else:
                next_num = last_num + 1

            conn.execute(
                """UPDATE doc_counters
                   SET last_num=?, updated_at=?
                   WHERE env=? AND timbrado=? AND establecimiento=? AND punto_expedicion=? AND tipo_documento=?""",
                (next_num, datetime.now().isoformat(), env, timbrado, est, punexp, tipode),
            )

        conn.commit()
        return next_num
    except Exception:
        conn.rollback()
        raise

