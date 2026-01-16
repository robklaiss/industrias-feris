"""
Utilidades para inspeccionar dCarQR en documentos SIFEN.

Diseñado para validar coherencia entre la URL del QR y el modo de validación
(test vs prod) antes de enviar el XML al Prevalidador.
"""

from __future__ import annotations

import xml.etree.ElementTree as ET
from typing import Dict, Optional, Tuple
from urllib.parse import urlparse, parse_qsl

SIFEN_NS = "http://ekuatia.set.gov.py/sifen/xsd"


def _local_name(tag: Optional[str]) -> Optional[str]:
    if tag is None:
        return None
    if tag.startswith("{"):
        return tag.split("}", 1)[1]
    return tag


def extract_dcar_qr(xml_content: str) -> Optional[str]:
    """
    Extrae el texto del nodo dCarQR desde un XML rDE/rLoteDE.

    Returns:
        Cadena con la URL del QR (sin desescapar) o None si no existe.
    """
    try:
        root = ET.fromstring(xml_content)
    except ET.ParseError:
        return None

    for elem in root.iter():
        if _local_name(elem.tag) == "dCarQR" and elem.text:
            return elem.text.strip()
    return None


def detect_qr_env(qr_url: Optional[str]) -> str:
    """
    Determina el ambiente del QR a partir de la URL.

    Returns:
        "TEST", "PROD" o "UNKNOWN".
    """
    if not qr_url:
        return "UNKNOWN"
    url_lower = qr_url.lower()
    if "/consultas-test/" in url_lower:
        return "TEST"
    if "/consultas-prod/" in url_lower:
        return "PROD"
    if "/consultas/qr" in url_lower:
        # En la práctica, /consultas/qr es PROD (sin sufijo '-test')
        return "PROD"
    return "UNKNOWN"


def extract_qr_params(qr_url: Optional[str]) -> Tuple[Dict[str, str], Optional[str]]:
    """
    Obtiene los parámetros del QR como dict y la URL base.
    """
    if not qr_url:
        return {}, None
    parsed = urlparse(qr_url.replace("&amp;", "&"))
    params = dict(parse_qsl(parsed.query, keep_blank_values=True))
    base_url = (
        f"{parsed.scheme}://{parsed.netloc}{parsed.path}"
        if parsed.scheme and parsed.netloc
        else parsed.path
    )
    return params, base_url
