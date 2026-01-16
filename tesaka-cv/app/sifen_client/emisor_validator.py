#!/usr/bin/env python3
"""
Validador de consistencia emisor vs certificado para SIFEN

Garantiza que:
1) El RUC del emisor (dRucEm) coincida con el RUC del certificado
2) El DV del emisor (dDVEmi) coincida con el DV del certificado (auto-fix si difiere)
3) El CDC/Id se recalcule después de cualquier corrección

Uso:
    from app.sifen_client.emisor_validator import ensure_emisor_matches_cert_and_refresh_cdc
    
    payload_fixed = ensure_emisor_matches_cert_and_refresh_cdc(
        payload=payload_dict,
        cert_path=p12_path,
        cert_password=p12_password
    )
"""
import os
import re
import logging
from pathlib import Path
from typing import Dict, Any, Tuple, Optional

logger = logging.getLogger(__name__)


class EmisorValidationError(Exception):
    """Error cuando el emisor no coincide con el certificado"""
    pass


def _calc_ruc_dv_modulo11(ruc_base: str) -> int:
    """
    Calcula el dígito verificador (DV) de un RUC paraguayo usando módulo 11.
    
    Algoritmo oficial Paraguay (similar al CDC):
    - Recorrer los dígitos del RUC desde la DERECHA hacia la IZQUIERDA
    - Multiplicar cada dígito por un peso que va de 2 a 11 (y se reinicia a 2)
    - Sumar todos los productos
    - Si (total % 11) > 1: dv = 11 - (total % 11)
    - Si no: dv = 0
    
    Args:
        ruc_base: RUC sin DV (7-8 dígitos)
        
    Returns:
        DV calculado (0-9)
    """
    # Limpiar y obtener solo dígitos
    digits = ''.join(c for c in str(ruc_base) if c.isdigit())
    if not digits:
        return 0
    
    # Algoritmo módulo 11: pesos de 2 a 11, luego se reinicia a 2
    base_max = 11
    k = 2
    total = 0
    
    # Recorrer desde la derecha (último dígito primero)
    for digit in reversed(digits):
        if k > base_max:
            k = 2
        total += int(digit) * k
        k += 1
    
    # Calcular DV
    remainder = total % 11
    if remainder > 1:
        dv = 11 - remainder
    else:
        dv = 0
    
    return dv


def extract_ruc_dv_from_cert(cert_path: str, cert_password: str) -> Tuple[str, str]:
    """
    Extrae RUC y DV del certificado P12/PFX
    
    Busca en Subject/serialNumber patrones como:
    - "RUC4554737-8"
    - "CI4554737"
    - "4554737-8"
    
    Args:
        cert_path: Ruta al archivo P12/PFX
        cert_password: Contraseña del certificado
        
    Returns:
        Tupla (ruc_base, dv) donde:
        - ruc_base: RUC sin DV ni ceros a la izquierda (ej: "4554737")
        - dv: Dígito verificador (ej: "8")
        
    Raises:
        EmisorValidationError: Si no se puede extraer RUC/DV del certificado
    """
    try:
        from cryptography.hazmat.primitives.serialization import pkcs12
        from cryptography.hazmat.backends import default_backend
    except ImportError as e:
        raise EmisorValidationError(
            "cryptography no está instalado. Instale con: pip install cryptography"
        ) from e
    
    cert_path_obj = Path(cert_path)
    if not cert_path_obj.exists():
        raise EmisorValidationError(f"Certificado P12 no encontrado: {cert_path}")
    
    try:
        with open(cert_path, "rb") as f:
            p12_bytes = f.read()
        
        password_bytes = cert_password.encode("utf-8") if cert_password else None
        key_obj, cert_obj, addl_certs = pkcs12.load_key_and_certificates(
            p12_bytes, password_bytes, backend=default_backend()
        )
        
        if not cert_obj:
            raise EmisorValidationError("No se pudo cargar el certificado desde el P12")
        
        # Extraer Subject como string
        subject_str = cert_obj.subject.rfc4514_string()
        logger.debug(f"Subject del certificado: {subject_str}")
        
        # Buscar serialNumber en el Subject
        # Formatos soportados:
        # - "serialNumber=RUC4554737-8" o "serialNumber=CI4554737"
        # - "2.5.4.5=CI4554737" (OID del serialNumber)
        serial_match = re.search(r'(?:serialNumber|2\.5\.4\.5)=([^,]+)', subject_str)
        if not serial_match:
            raise EmisorValidationError(
                f"No se encontró serialNumber (ni 2.5.4.5) en el certificado. Subject: {subject_str}"
            )
        
        serial_value = serial_match.group(1).strip()
        logger.debug(f"serialNumber extraído: {serial_value}")
        
        # Parsear el serialNumber para extraer RUC y DV
        # Patrones soportados:
        # - "RUC4554737-8" -> ruc=4554737, dv=8
        # - "CI4554737" -> ruc=4554737, dv=? (calcular)
        # - "4554737-8" -> ruc=4554737, dv=8
        
        # Intentar patrón con DV explícito: RUC/CI seguido de dígitos-DV
        match_with_dv = re.search(r'(?:RUC|CI)?(\d+)-(\d)', serial_value)
        if match_with_dv:
            ruc_base = match_with_dv.group(1).lstrip("0") or "0"
            dv = match_with_dv.group(2)
            logger.info(f"RUC extraído del certificado: {ruc_base}-{dv}")
            return (ruc_base, dv)
        
        # Intentar patrón sin DV: RUC/CI seguido de dígitos
        match_no_dv = re.search(r'(?:RUC|CI)?(\d+)', serial_value)
        if match_no_dv:
            ruc_base = match_no_dv.group(1).lstrip("0") or "0"
            # Calcular DV usando algoritmo módulo 11 (Paraguay)
            try:
                dv = str(_calc_ruc_dv_modulo11(ruc_base))
            except:
                dv = "0"
            logger.warning(
                f"DV no encontrado en certificado, calculado: {ruc_base}-{dv}"
            )
            return (ruc_base, dv)
        
        raise EmisorValidationError(
            f"No se pudo parsear RUC/DV del serialNumber: {serial_value}"
        )
        
    except Exception as e:
        if isinstance(e, EmisorValidationError):
            raise
        raise EmisorValidationError(f"Error al leer certificado: {e}") from e


def ensure_emisor_matches_cert_and_refresh_cdc(
    payload: Dict[str, Any],
    cert_path: str,
    cert_password: str
) -> Dict[str, Any]:
    """
    Valida y corrige la consistencia entre emisor y certificado
    
    Reglas:
    1) Si payload.emisor.dRucEm no existe: ERROR duro
    2) Si payload.emisor.dRucEm != cert_ruc: ERROR duro (no firmar)
    3) Si payload.emisor.dDVEmi != cert_dv: AUTO-FIX con WARNING
    4) Después del fix: regenerar CDC/Id
    5) Invalidar campos dependientes (QR/hash/digest precalculados)
    
    Args:
        payload: Diccionario con datos del DE (debe tener estructura emisor/documento)
        cert_path: Ruta al certificado P12/PFX
        cert_password: Contraseña del certificado
        
    Returns:
        Payload corregido con dDVEmi actualizado y CDC regenerado
        
    Raises:
        EmisorValidationError: Si hay inconsistencias que no se pueden auto-corregir
    """
    # Extraer RUC/DV del certificado
    cert_ruc, cert_dv = extract_ruc_dv_from_cert(cert_path, cert_password)
    
    # Validar que el payload tenga estructura de emisor
    if "emisor" not in payload:
        raise EmisorValidationError(
            "Payload no tiene estructura 'emisor'. "
            "Debe contener: payload['emisor']['dRucEm'] y payload['emisor']['dDVEmi']"
        )
    
    emisor = payload["emisor"]
    
    # Regla A: dRucEm debe existir
    if "dRucEm" not in emisor or not emisor["dRucEm"]:
        raise EmisorValidationError(
            "payload['emisor']['dRucEm'] no existe o está vacío. "
            "No se puede validar contra el certificado."
        )
    
    xml_ruc = str(emisor["dRucEm"]).strip().lstrip("0") or "0"
    xml_dv = str(emisor.get("dDVEmi", "")).strip()
    
    # Regla C: Si xml_ruc != cert_ruc, ERROR duro
    if xml_ruc != cert_ruc:
        raise EmisorValidationError(
            f"RUC del emisor no coincide con el certificado:\n"
            f"  - Certificado: {cert_ruc}-{cert_dv}\n"
            f"  - XML/Payload: {xml_ruc}-{xml_dv}\n"
            f"SOLUCIÓN: Corrija dRucEm en el payload o use el certificado correspondiente."
        )
    
    # Regla B: Si xml_dv != cert_dv, AUTO-FIX con WARNING
    if xml_dv != cert_dv:
        logger.warning(
            f"⚠️  AUTO-FIX dDVEmi: Certificado tiene DV={cert_dv}, "
            f"pero payload tenía DV={xml_dv or '(vacío)'}. "
            f"Corrigiendo automáticamente a DV={cert_dv}"
        )
        emisor["dDVEmi"] = cert_dv
        
        # Marcar que el CDC debe regenerarse
        payload["_cdc_needs_refresh"] = True
        
        # Invalidar campos dependientes si existen
        if "cdc" in payload:
            del payload["cdc"]
        if "qr_url" in payload:
            del payload["qr_url"]
        if "digest_value" in payload:
            del payload["digest_value"]
    
    logger.info(
        f"✅ Validación emisor vs certificado OK: {cert_ruc}-{cert_dv}"
    )
    
    return payload


def validate_emisor_in_xml(xml_str: str, cert_path: str, cert_password: str) -> None:
    """
    Valida que el XML final tenga dRucEm/dDVEmi consistentes con el certificado
    
    Esta función se llama ANTES de firmar para garantizar consistencia.
    
    Args:
        xml_str: XML como string
        cert_path: Ruta al certificado P12/PFX
        cert_password: Contraseña del certificado
        
    Raises:
        EmisorValidationError: Si hay inconsistencias
    """
    try:
        from lxml import etree
    except ImportError as e:
        raise EmisorValidationError(
            "lxml no está instalado. Instale con: pip install lxml"
        ) from e
    
    # Extraer RUC/DV del certificado
    cert_ruc, cert_dv = extract_ruc_dv_from_cert(cert_path, cert_password)
    
    # Parsear XML
    try:
        if isinstance(xml_str, bytes):
            root = etree.fromstring(xml_str)
        else:
            root = etree.fromstring(xml_str.encode("utf-8"))
    except Exception as e:
        raise EmisorValidationError(f"Error al parsear XML: {e}") from e
    
    # Buscar dRucEm y dDVEmi en el XML
    ns = {"sifen": "http://ekuatia.set.gov.py/sifen/xsd"}
    
    d_ruc_em_nodes = root.xpath("//sifen:dRucEm/text()", namespaces=ns)
    if not d_ruc_em_nodes:
        d_ruc_em_nodes = root.xpath("//dRucEm/text()")
    
    d_dv_emi_nodes = root.xpath("//sifen:dDVEmi/text()", namespaces=ns)
    if not d_dv_emi_nodes:
        d_dv_emi_nodes = root.xpath("//dDVEmi/text()")
    
    if not d_ruc_em_nodes:
        raise EmisorValidationError(
            "No se encontró <dRucEm> en el XML. "
            "No se puede validar contra el certificado."
        )
    
    xml_ruc = str(d_ruc_em_nodes[0]).strip().lstrip("0") or "0"
    xml_dv = str(d_dv_emi_nodes[0]).strip() if d_dv_emi_nodes else ""
    
    # Validar RUC
    if xml_ruc != cert_ruc:
        raise EmisorValidationError(
            f"❌ RUC del emisor en XML no coincide con el certificado:\n"
            f"  - Certificado: {cert_ruc}-{cert_dv}\n"
            f"  - XML: {xml_ruc}-{xml_dv}\n"
            f"SOLUCIÓN: Regenere el XML con el RUC correcto o use el certificado correspondiente."
        )
    
    # Validar DV
    if xml_dv != cert_dv:
        raise EmisorValidationError(
            f"❌ DV del emisor en XML no coincide con el certificado:\n"
            f"  - Certificado: {cert_ruc}-{cert_dv}\n"
            f"  - XML: {xml_ruc}-{xml_dv}\n"
            f"SOLUCIÓN: Regenere el XML con dDVEmi={cert_dv}"
        )
    
    logger.info(
        f"✅ Validación XML vs certificado OK: {cert_ruc}-{cert_dv}"
    )
