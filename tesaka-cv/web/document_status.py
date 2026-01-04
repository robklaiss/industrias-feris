"""
Constantes y utilidades para estados de documentos SIFEN.

Estados válidos:
- SIGNED_LOCAL: Documento firmado localmente, pendiente de envío a SIFEN
- SENT_TO_SIFEN: Documento enviado a SIFEN (siRecepLoteDE/siRecepDE), recibido
- PENDING_SIFEN: Enviado y recibido por SIFEN, esperando validación/aprobación
- APPROVED: Aprobado por SIFEN (solo cuando consulta devuelve aprobación con fecha/hora)
- REJECTED: Rechazado por SIFEN (con código y mensaje de rechazo)
- ERROR: Error en el proceso (configuración, red, etc.)
"""
from typing import Optional

# Estados válidos
STATUS_SIGNED_LOCAL = "signed_local"
STATUS_SENT_TO_SIFEN = "sent_to_sifen"
STATUS_PENDING_SIFEN = "pending_sifen"
STATUS_APPROVED = "approved"
STATUS_REJECTED = "rejected"
STATUS_ERROR = "error"

VALID_STATUSES = [
    STATUS_SIGNED_LOCAL,
    STATUS_SENT_TO_SIFEN,
    STATUS_PENDING_SIFEN,
    STATUS_APPROVED,
    STATUS_REJECTED,
    STATUS_ERROR,
]

# Mensajes para UI
STATUS_MESSAGES = {
    STATUS_SIGNED_LOCAL: "FIRMADO LOCALMENTE: pendiente de envío a SIFEN.",
    STATUS_SENT_TO_SIFEN: "ENVIADO A SIFEN: recibido, en espera de validación/aprobación.",
    STATUS_PENDING_SIFEN: "ENVIADO A SIFEN: en espera de validación/aprobación.",
    STATUS_APPROVED: "APROBADO POR SIFEN: DE emitido y autorizado.",
    STATUS_REJECTED: "RECHAZADO POR SIFEN",
    STATUS_ERROR: "ERROR: problema en el proceso.",
}

# Mapeo de códigos de respuesta SIFEN a estados
# Códigos de recepción (siRecepLoteDE / siRecepDE)
RECEPCION_OK_CODES = ["0300"]  # Lote recibido con éxito
RECEPCION_ERROR_CODES = ["0301"]  # Lote no encolado

# Códigos de consulta de lote (siConsLoteDE)
CONSULTA_LOTE_PENDING = ["0361"]  # Lote en procesamiento
CONSULTA_LOTE_DONE = ["0362"]  # Procesamiento concluido
CONSULTA_LOTE_ERROR = ["0360", "0364"]  # Lote inexistente, consulta extemporánea

# Códigos de consulta de DE (siConsDE)
CONSULTA_DE_APPROVED = ["0422"]  # CDC encontrado (DE aprobado)
CONSULTA_DE_NOT_FOUND = ["0420"]  # DE no existe o no está aprobado


def get_status_message(status: str, code: Optional[str] = None, message: Optional[str] = None, approved_at: Optional[str] = None) -> str:
    """
    Obtiene el mensaje de estado para mostrar en UI.
    
    Args:
        status: Estado del documento
        code: Código de respuesta SIFEN (opcional)
        message: Mensaje de respuesta SIFEN (opcional)
        approved_at: Fecha/hora de aprobación (opcional)
        
    Returns:
        Mensaje formateado para mostrar
    """
    base_msg = STATUS_MESSAGES.get(status, f"Estado: {status}")
    
    if status == STATUS_APPROVED and approved_at:
        return f"{base_msg} (Aprobado el {approved_at})"
    
    if status == STATUS_REJECTED:
        if code and message:
            return f"{base_msg}: {code} - {message}"
        elif code:
            return f"{base_msg}: {code}"
        elif message:
            return f"{base_msg}: {message}"
    
    return base_msg


def is_final_status(status: str) -> bool:
    """
    Indica si un estado es final (no puede cambiar).
    
    Returns:
        True si el estado es final (APPROVED, REJECTED)
        ERROR NO es final, permite reintentos
    """
    return status in [STATUS_APPROVED, STATUS_REJECTED]


def can_transition_to(from_status: str, to_status: str) -> bool:
    """
    Valida si una transición de estado es válida.
    
    Returns:
        True si la transición es válida
    """
    # Estados finales no pueden cambiar (excepto ERROR que permite reintentos)
    if is_final_status(from_status):
        return False
    
    # Transiciones válidas
    valid_transitions = {
        STATUS_SIGNED_LOCAL: [STATUS_SENT_TO_SIFEN, STATUS_ERROR],
        STATUS_SENT_TO_SIFEN: [STATUS_PENDING_SIFEN, STATUS_ERROR],
        STATUS_PENDING_SIFEN: [STATUS_APPROVED, STATUS_REJECTED, STATUS_ERROR],
        # ERROR permite reintentar: puede volver a SENT_TO_SIFEN o PENDING_SIFEN
        STATUS_ERROR: [STATUS_SENT_TO_SIFEN, STATUS_PENDING_SIFEN, STATUS_APPROVED, STATUS_REJECTED],
    }
    
    allowed = valid_transitions.get(from_status, [])
    return to_status in allowed

