"""
Módulo para consultar estado de lotes SIFEN
"""
import os
import logging
from typing import Dict, Any, Optional
from pathlib import Path
import sys

# Agregar tools al path para importar call_consulta_lote_raw
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from requests import Session

logger = logging.getLogger(__name__)

# Importar función de consulta desde tools
try:
    from tools.consulta_lote_de import call_consulta_lote_raw, p12_to_pem_files
except ImportError:
    logger.error("No se pudo importar call_consulta_lote_raw desde tools.consulta_lote_de")
    raise


def validate_prot_cons_lote(prot: str) -> bool:
    """
    Valida que dProtConsLote sea solo dígitos.

    Args:
        prot: Número de lote a validar

    Returns:
        True si es válido, False si no
    """
    if not prot:
        return False
    return prot.strip().isdigit()


def parse_lote_response(xml_response: str) -> Dict[str, Any]:
    """
    Parsea la respuesta XML de consulta de lote para extraer dCodResLot y dMsgResLot.

    Args:
        xml_response: XML de respuesta como string

    Returns:
        Dict con:
            - cod_res_lot: Código de respuesta (ej: "0361", "0362", "0364")
            - msg_res_lot: Mensaje de respuesta
            - ok: True si el parsing fue exitoso
    """
    result = {
        "cod_res_lot": None,
        "msg_res_lot": None,
        "ok": False,
    }

    try:
        from lxml import etree

        root = etree.fromstring(xml_response.encode("utf-8"))

        def find_text(xpath_expr: str) -> Optional[str]:
            try:
                nodes = root.xpath(xpath_expr)
                if nodes:
                    val = nodes[0].text
                    return val.strip() if val else None
            except Exception:
                return None
            return None

        # Buscar dCodResLot y dMsgResLot por local-name
        result["cod_res_lot"] = find_text('//*[local-name()="dCodResLot"]')
        result["msg_res_lot"] = find_text('//*[local-name()="dMsgResLot"]')

        result["ok"] = True

    except Exception as e:
        logger.warning(f"Error al parsear respuesta XML de lote: {e}")
        result["ok"] = False

    return result


def check_lote_status(
    env: str,
    prot: str,
    p12_path: Optional[str] = None,
    p12_password: Optional[str] = None,
    timeout: int = 30,
) -> Dict[str, Any]:
    """
    Consulta el estado de un lote en SIFEN usando SOAP RAW.

    Args:
        env: Ambiente ('test' o 'prod')
        prot: dProtConsLote (debe ser solo dígitos)
        p12_path: Ruta al certificado P12 (opcional, usa env vars si no se proporciona)
        p12_password: Contraseña del P12 (opcional, usa env vars si no se proporciona)
        timeout: Timeout HTTP en segundos

    Returns:
        Dict con:
            - success: True si la consulta fue exitosa
            - cod_res_lot: Código de respuesta (ej: "0361", "0362", "0364")
            - msg_res_lot: Mensaje de respuesta
            - response_xml: XML completo de respuesta
            - error: Mensaje de error si falló

    Raises:
        ValueError: Si prot no es válido (no es solo dígitos)
    """
    # Validar prot
    if not validate_prot_cons_lote(prot):
        raise ValueError(
            f"dProtConsLote debe ser solo dígitos. Valor recibido: '{prot}'"
        )

    # Resolver certificado desde env vars si no se proporciona - usar helper unificado
    if not p12_path or not p12_password:
        from app.sifen_client.config import get_cert_path_and_password
        env_cert_path, env_cert_password = get_cert_path_and_password()
        p12_path = p12_path or env_cert_path
        p12_password = p12_password or env_cert_password

    if not p12_path or not p12_password:
        return {
            "success": False,
            "error": "Faltan certificado P12 o contraseña. Configure SIFEN_CERT_PATH y SIFEN_CERT_PASSWORD",
        }

    # Convertir P12 a PEM temporales
    cert_pair = None
    try:
        cert_pair = p12_to_pem_files(p12_path, p12_password)

        # Crear sesión con mTLS
        session = Session()
        session.cert = (cert_pair.cert_path, cert_pair.key_path)
        session.verify = True

        # Consultar lote
        logger.info(f"Consultando lote {prot} en ambiente {env}")
        xml_response = call_consulta_lote_raw(
            session=session, env=env, prot=prot, timeout=timeout
        )

        # Parsear respuesta
        parsed = parse_lote_response(xml_response)

        result = {
            "success": True,
            "cod_res_lot": parsed.get("cod_res_lot"),
            "msg_res_lot": parsed.get("msg_res_lot"),
            "response_xml": xml_response,
        }

        return result

    except Exception as e:
        logger.error(f"Error al consultar lote {prot}: {e}")
        return {
            "success": False,
            "error": str(e),
            "response_xml": None,
        }
    finally:
        # Limpiar archivos PEM temporales
        if cert_pair:
            try:
                os.unlink(cert_pair.cert_path)
                os.unlink(cert_pair.key_path)
            except Exception as e:
                logger.warning(f"Error al limpiar archivos PEM temporales: {e}")


def determine_status_from_cod_res_lot(cod_res_lot: Optional[str]) -> str:
    """
    Determina el estado del lote basado en el código de respuesta.

    Args:
        cod_res_lot: Código de respuesta (ej: "0361", "0362", "0364")

    Returns:
        Estado: 'processing', 'done', 'expired_window', 'requires_cdc', o 'error'
    """
    # Importar estados desde lotes_db (evitar import circular)
    LOTE_STATUS_PROCESSING = "processing"
    LOTE_STATUS_DONE = "done"
    LOTE_STATUS_EXPIRED_WINDOW = "expired_window"
    LOTE_STATUS_REQUIRES_CDC = "requires_cdc"
    LOTE_STATUS_ERROR = "error"

    if not cod_res_lot:
        return LOTE_STATUS_ERROR

    cod_res_lot = cod_res_lot.strip()

    # Códigos según documentación SIFEN
    if cod_res_lot == "0361":
        # Lote en procesamiento
        return LOTE_STATUS_PROCESSING
    elif cod_res_lot == "0362":
        # Lote procesado exitosamente
        return LOTE_STATUS_DONE
    elif cod_res_lot == "0364":
        # Ventana de 48h expirada (en TEST), requiere consulta por CDC
        return LOTE_STATUS_REQUIRES_CDC
    else:
        # Otros códigos (errores u otros estados)
        return LOTE_STATUS_ERROR

