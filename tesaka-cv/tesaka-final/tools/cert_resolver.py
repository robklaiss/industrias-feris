#!/usr/bin/env python3
"""
Utilidades para validar y registrar qué certificados se usan en runtime.

Separa claramente:
- Certificado de firma: para firma XML (XMLDSig)
- Certificado de mTLS: para autenticación TLS con SIFEN

Guarda artifacts con resolved_certs para evidencia.
"""
import os
import json
import logging
from pathlib import Path
from typing import Tuple, Dict, Any, Optional
from datetime import datetime

logger = logging.getLogger(__name__)


def validate_no_self_signed(cert_path: str, context: str) -> None:
    """
    Valida que el certificado NO sea self-signed.
    
    Args:
        cert_path: Ruta al archivo de certificado
        context: Contexto de uso ("firma" o "mTLS")
        
    Raises:
        RuntimeError: Si el certificado es self-signed
    """
    cert_basename = Path(cert_path).name.lower()
    
    # Detectar self-signed por nombre de archivo
    if "selfsigned" in cert_basename or "self_signed" in cert_basename:
        raise RuntimeError(
            f"❌ Certificado self-signed detectado en contexto {context}: {cert_path}\n"
            f"Los certificados self-signed solo pueden usarse como fixtures de tests unitarios.\n"
            f"Para {context}, use un certificado real emitido por SIFEN."
        )
    
    # Si está en el directorio certs/, también validar
    if "certs/" in cert_path.lower() or cert_path.startswith("certs/"):
        if "selfsigned" in cert_basename:
            raise RuntimeError(
                f"❌ Certificado self-signed en directorio certs/ usado para {context}: {cert_path}\n"
                f"Use un certificado real para producción/testing con SIFEN."
            )


def resolve_signing_cert() -> Tuple[str, str]:
    """
    Resuelve el certificado de firma XMLDSig.
    
    Prioridad:
    1. SIFEN_SIGN_P12_PATH / SIFEN_SIGN_P12_PASSWORD (explícito para firma)
    2. SIFEN_MTLS_P12_PATH / SIFEN_MTLS_P12_PASSWORD (fallback)
    3. SIFEN_CERT_PATH / SIFEN_CERT_PASSWORD (legacy)
    
    Returns:
        Tuple (cert_path, cert_password)
        
    Raises:
        RuntimeError: Si faltan variables o el certificado es self-signed
    """
    # 1. Preferir explícito de firma
    cert_path = os.getenv("SIFEN_SIGN_P12_PATH")
    cert_password = os.getenv("SIFEN_SIGN_P12_PASSWORD")
    
    if not cert_path:
        # 2. Fallback a mTLS (si es el mismo certificado)
        cert_path = os.getenv("SIFEN_MTLS_P12_PATH")
        cert_password = os.getenv("SIFEN_MTLS_P12_PASSWORD")
    
    if not cert_path:
        # 3. Legacy genérico
        cert_path = os.getenv("SIFEN_CERT_PATH")
        cert_password = os.getenv("SIFEN_CERT_PASSWORD")
    
    if not cert_path:
        raise RuntimeError(
            "❌ Falta certificado de firma. Configure una de:\n"
            "  - SIFEN_SIGN_P12_PATH + SIFEN_SIGN_P12_PASSWORD (recomendado)\n"
            "  - SIFEN_MTLS_P12_PATH + SIFEN_MTLS_P12_PASSWORD\n"
            "  - SIFEN_CERT_PATH + SIFEN_CERT_PASSWORD (legacy)"
        )
    
    if not cert_password:
        raise RuntimeError(
            f"❌ Falta contraseña para certificado de firma: {cert_path}\n"
            f"Configure la variable de contraseña correspondiente."
        )
    
    if not os.path.exists(cert_path):
        raise RuntimeError(f"❌ Certificado de firma no encontrado: {cert_path}")
    
    # Validar que no sea self-signed
    validate_no_self_signed(cert_path, "firma XML")
    
    logger.info(f"✅ Certificado de firma resuelto: {Path(cert_path).name}")
    return cert_path, cert_password


def resolve_mtls_cert() -> Tuple[str, Optional[str], bool]:
    """
    Resuelve el certificado mTLS para requests/urllib3.
    
    Returns:
        Tuple (cert_path, key_or_password, is_pem_mode)
        - Si es PEM: (cert_path, key_path, True)
        - Si es P12: (p12_path, password, False)
        
    Raises:
        RuntimeError: Si faltan variables o el certificado es self-signed
    """
    # 1. Modo PEM优先: SIFEN_CERT_PATH + SIFEN_KEY_PATH
    cert_path = os.getenv("SIFEN_CERT_PATH")
    key_path = os.getenv("SIFEN_KEY_PATH")
    
    if cert_path and key_path:
        if not os.path.exists(cert_path):
            raise RuntimeError(f"❌ Certificado PEM no encontrado: {cert_path}")
        if not os.path.exists(key_path):
            raise RuntimeError(f"❌ Key PEM no encontrada: {key_path}")
        
        # Validar que no sea self-signed
        validate_no_self_signed(cert_path, "mTLS PEM")
        validate_no_self_signed(key_path, "mTLS PEM")
        
        logger.info(f"✅ Certificado mTLS PEM resuelto: {Path(cert_path).name}, {Path(key_path).name}")
        return cert_path, key_path, True
    
    # 2. Modo P12: preferir explícito mTLS
    p12_path = os.getenv("SIFEN_MTLS_P12_PATH")
    p12_password = os.getenv("SIFEN_MTLS_P12_PASSWORD")
    
    if not p12_path:
        # Fallback a otros P12
        p12_path = os.getenv("SIFEN_SIGN_P12_PATH") or os.getenv("SIFEN_CERT_PATH")
    
    if not p12_path:
        raise RuntimeError(
            "❌ Falta certificado mTLS. Configure una de:\n"
            "  - Modo PEM: SIFEN_CERT_PATH + SIFEN_KEY_PATH\n"
            "  - Modo P12: SIFEN_MTLS_P12_PATH + SIFEN_MTLS_P12_PASSWORD"
        )
    
    if not p12_password:
        # Buscar password en otras variables
        p12_password = (
            os.getenv("SIFEN_MTLS_P12_PASSWORD") or
            os.getenv("SIFEN_SIGN_P12_PASSWORD") or
            os.getenv("SIFEN_CERT_PASSWORD")
        )
    
    if not p12_password:
        raise RuntimeError(
            f"❌ Falta contraseña para P12 mTLS: {p12_path}\n"
            f"Configure SIFEN_MTLS_P12_PASSWORD o similar."
        )
    
    if not os.path.exists(p12_path):
        raise RuntimeError(f"❌ Certificado P12 mTLS no encontrado: {p12_path}")
    
    # Validar que no sea self-signed
    validate_no_self_signed(p12_path, "mTLS P12")
    
    logger.info(f"✅ Certificado mTLS P12 resuelto: {Path(p12_path).name}")
    return p12_path, p12_password, False


def save_resolved_certs_artifact(signing_cert: Optional[str] = None,
                                 mtls_cert: Optional[str] = None,
                                 mtls_key: Optional[str] = None,
                                 mtls_mode: Optional[str] = None) -> str:
    """
    Guarda artifact con qué certificados se resolvieron en runtime.
    
    Args:
        signing_cert: Path al certificado de firma
        mtls_cert: Path al certificado mTLS
        mtls_key: Path a la key mTLS (si es modo PEM)
        mtls_mode: "PEM" o "P12"
        
    Returns:
        Path al archivo guardado
    """
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")[:-3]
    artifacts_dir = Path("artifacts")
    artifacts_dir.mkdir(exist_ok=True)
    
    artifact_path = artifacts_dir / f"resolved_certs_{timestamp}.json"
    
    resolved_info = {
        "timestamp": timestamp,
        "signing": {
            "p12_path": Path(signing_cert).name if signing_cert else None,
        },
        "mtls": {
            "mode": mtls_mode,
            "cert_path": Path(mtls_cert).name if mtls_cert else None,
            "key_path": Path(mtls_key).name if mtls_key else None,
            "p12_path": Path(mtls_cert).name if mtls_cert and mtls_mode == "P12" else None,
        },
        "environment": {
            "SIFEN_SIGN_P12_PATH": os.getenv("SIFEN_SIGN_P12_PATH"),
            "SIFEN_MTLS_P12_PATH": os.getenv("SIFEN_MTLS_P12_PATH"),
            "SIFEN_CERT_PATH": os.getenv("SIFEN_CERT_PATH"),
            "SIFEN_KEY_PATH": os.getenv("SIFEN_KEY_PATH"),
            # Sin passwords por seguridad
        }
    }
    
    artifact_path.write_text(json.dumps(resolved_info, indent=2), encoding='utf-8')
    logger.info(f"📝 Artifact de certificados guardado: {artifact_path}")
    
    return str(artifact_path)


def get_resolved_certs_info() -> Dict[str, Any]:
    """
    Obtiene información de certificados resueltos para logging.
    
    Returns:
        Dict con información resumida (sin paths completos)
    """
    try:
        signing_path, _ = resolve_signing_cert()
        mtls_path, mtls_key_or_pass, is_pem = resolve_mtls_cert()
        
        return {
            "signing_p12": Path(signing_path).name,
            "mtls_mode": "PEM" if is_pem else "P12",
            "mtls_cert": Path(mtls_path).name,
            "mtls_key": Path(mtls_key_or_pass).name if is_pem else None,
            "mtls_p12": Path(mtls_path).name if not is_pem else None,
        }
    except Exception as e:
        return {
            "error": str(e),
            "signing_p12": None,
            "mtls_mode": None,
            "mtls_cert": None,
            "mtls_key": None,
            "mtls_p12": None,
        }
