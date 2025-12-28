"""
Utilidades y funciones auxiliares para el sistema
"""
from typing import Dict, List, Optional, Tuple
from .db import get_db


def get_contract_balance(contract_id: int) -> Dict[int, float]:
    """
    Calcula el saldo disponible por producto de un contrato
    Retorna dict: {contract_item_id: saldo_disponible}
    """
    conn = get_db()
    cursor = conn.cursor()
    
    # Obtener items del contrato
    cursor.execute("""
        SELECT id, cantidad_total FROM contract_items
        WHERE contract_id = ?
    """, (contract_id,))
    contract_items = {row['id']: row['cantidad_total'] for row in cursor.fetchall()}
    
    # Calcular cantidad ya usada en OCs vinculadas
    cursor.execute("""
        SELECT contract_item_id, SUM(cantidad) as total_used
        FROM purchase_order_items
        WHERE contract_item_id IN ({})
        GROUP BY contract_item_id
    """.format(','.join(map(str, contract_items.keys()))) if contract_items else "SELECT 1 WHERE 0")
    
    used = {row['contract_item_id']: row['total_used'] for row in cursor.fetchall()}
    conn.close()
    
    # Calcular saldos
    balances = {}
    for item_id, total in contract_items.items():
        used_amount = used.get(item_id, 0.0)
        balances[item_id] = max(0.0, total - used_amount)
    
    return balances


def get_po_item_balance(po_item_id: int) -> float:
    """
    Calcula el saldo disponible de un item de orden de compra
    Retorna: saldo_disponible (cantidad - cantidad ya entregada)
    """
    conn = get_db()
    cursor = conn.cursor()
    
    # Obtener cantidad de la OC
    cursor.execute("SELECT cantidad FROM purchase_order_items WHERE id = ?", (po_item_id,))
    po_item = cursor.fetchone()
    if not po_item:
        conn.close()
        return 0.0
    
    cantidad_oc = po_item['cantidad']
    
    # Calcular cantidad ya entregada
    cursor.execute("""
        SELECT COALESCE(SUM(cantidad), 0) as total_delivered
        FROM delivery_note_items
        WHERE source_po_item_id = ?
    """, (po_item_id,))
    
    delivered = cursor.fetchone()['total_delivered']
    conn.close()
    
    return max(0.0, cantidad_oc - delivered)


def get_next_delivery_note_number() -> int:
    """Obtiene el siguiente número de nota de entrega"""
    conn = get_db()
    cursor = conn.cursor()
    
    cursor.execute("SELECT MAX(numero_nota) as max_num FROM delivery_notes")
    result = cursor.fetchone()
    conn.close()
    
    max_num = result['max_num'] if result['max_num'] is not None else 0
    return max_num + 1


def get_next_remission_number(prefix: str) -> str:
    """Obtiene el siguiente número de remisión"""
    conn = get_db()
    cursor = conn.cursor()
    
    # Obtener número base de configuración
    cursor.execute("SELECT value FROM system_config WHERE key = 'remission_base_number'")
    base_row = cursor.fetchone()
    base_number = int(base_row['value']) if base_row else 1
    
    # Buscar el siguiente disponible
    while True:
        numero = f"{prefix}{base_number:06d}"
        cursor.execute("SELECT id FROM remissions WHERE numero_remision = ?", (numero,))
        if not cursor.fetchone():
            # Actualizar número base para próximo uso
            cursor.execute("""
                UPDATE system_config 
                SET value = ? 
                WHERE key = 'remission_base_number'
            """, (str(base_number + 1),))
            conn.commit()
            conn.close()
            return numero
        base_number += 1


def get_next_invoice_number() -> str:
    """Obtiene el siguiente número de factura"""
    conn = get_db()
    cursor = conn.cursor()
    
    # Obtener número base de configuración
    cursor.execute("SELECT value FROM system_config WHERE key = 'invoice_base_number'")
    base_row = cursor.fetchone()
    base_number = int(base_row['value']) if base_row else 1
    
    # Buscar el siguiente disponible
    while True:
        numero = f"FAC-{base_number:06d}"
        cursor.execute("SELECT id FROM sales_invoices WHERE numero = ?", (numero,))
        if not cursor.fetchone():
            # Actualizar número base para próximo uso
            cursor.execute("""
                UPDATE system_config 
                SET value = ? 
                WHERE key = 'invoice_base_number'
            """, (str(base_number + 1),))
            conn.commit()
            conn.close()
            return numero
        base_number += 1


def validate_po_item_quantities(po_items: List[Dict], contract_id: Optional[int] = None) -> Tuple[bool, List[str]]:
    """
    Valida que las cantidades de items de OC no excedan el contrato
    Retorna: (es_valido, lista_errores)
    """
    if not contract_id:
        return True, []
    
    errors = []
    balances = get_contract_balance(contract_id)
    
    for item in po_items:
        contract_item_id = item.get('contract_item_id')
        cantidad = item.get('cantidad', 0)
        
        if contract_item_id and contract_item_id in balances:
            available = balances[contract_item_id]
            if cantidad > available:
                producto = item.get('producto', 'Desconocido')
                errors.append(
                    f"Producto '{producto}': cantidad solicitada ({cantidad}) "
                    f"excede saldo disponible del contrato ({available})"
                )
    
    return len(errors) == 0, errors


def validate_delivery_note_quantities(dn_items: List[Dict]) -> Tuple[bool, List[str]]:
    """
    Valida que las cantidades de items de nota de entrega no excedan la OC
    Retorna: (es_valido, lista_errores)
    """
    errors = []
    
    for item in dn_items:
        po_item_id = item.get('source_po_item_id')
        cantidad = item.get('cantidad', 0)
        
        if po_item_id:
            available = get_po_item_balance(po_item_id)
            if cantidad > available:
                producto = item.get('producto', 'Desconocido')
                errors.append(
                    f"Producto '{producto}': cantidad solicitada ({cantidad}) "
                    f"excede saldo disponible de la OC ({available})"
                )
    
    return len(errors) == 0, errors


def get_config_value(key: str, default: str = "") -> str:
    """Obtiene un valor de configuración del sistema"""
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT value FROM system_config WHERE key = ?", (key,))
    row = cursor.fetchone()
    conn.close()
    return row['value'] if row else default


def set_config_value(key: str, value: str):
    """Establece un valor de configuración del sistema"""
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO system_config (key, value) 
        VALUES (?, ?)
        ON CONFLICT(key) DO UPDATE SET value = ?
    """, (key, value, value))
    conn.commit()
    conn.close()

