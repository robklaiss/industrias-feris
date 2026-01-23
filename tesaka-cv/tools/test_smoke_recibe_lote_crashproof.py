#!/usr/bin/env python3
"""
Versión crash-proof del smoke test con retries y artifacts completos.

Este script:
1. Reintenta en errores de red (RemoteDisconnected, ConnectionError, etc.)
2. Guarda artifacts incluso si falla (request, metadata, exception)
3. Valida que no se usen certificados self-signed
4. Guarda resolved_certs artifacts para evidencia
5. Implementa backoff exponencial con jitter

Uso:
    .venv/bin/python tools/test_smoke_recibe_lote_crashproof.py [--env test|prod] [--max-retries 3]
"""
import os
import sys
import json
import logging
import argparse
import time
import random
import traceback
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, Tuple, Optional

# Asegurar que estamos en el directorio correcto
script_dir = Path(__file__).parent
project_root = script_dir.parent
sys.path.insert(0, str(project_root))

# Configurar logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Importar cert_resolver
try:
    from tools.cert_resolver import (
        resolve_signing_cert, 
        resolve_mtls_cert,
        save_resolved_certs_artifact,
        get_resolved_certs_info,
        validate_no_self_signed
    )
except ImportError:
    logger.error("No se pudo importar cert_resolver")
    sys.exit(1)

def parse_args() -> argparse.Namespace:
    """Parse argumentos de línea de comandos"""
    parser = argparse.ArgumentParser(description='Smoke test crash-proof para recibe-lote SIFEN')
    parser.add_argument(
        '--env',
        choices=['test', 'prod'],
        default='test',
        help='Ambiente SIFEN (default: test)'
    )
    parser.add_argument(
        '--verbose', '-v',
        action='store_true',
        help='Logging verbose'
    )
    parser.add_argument(
        '--max-retries',
        type=int,
        default=int(os.getenv("SIFEN_SOAP_MAX_RETRIES", "3")),
        help='Número máximo de reintentos (default: 3)'
    )
    parser.add_argument(
        '--backoff-base',
        type=float,
        default=float(os.getenv("SIFEN_SOAP_BACKOFF_BASE", "0.6")),
        help='Backoff base en segundos (default: 0.6)'
    )
    parser.add_argument(
        '--backoff-max',
        type=float,
        default=float(os.getenv("SIFEN_SOAP_BACKOFF_MAX", "8.0")),
        help='Backoff máximo en segundos (default: 8.0)'
    )
    parser.add_argument(
        '--sign-p12-path',
        type=str,
        default=os.getenv("SIFEN_SIGN_P12_PATH") or os.getenv("SIFEN_P12_PATH") or "",
        help='Ruta al archivo P12 de firma'
    )
    parser.add_argument(
        '--sign-p12-password',
        type=str,
        default=os.getenv("SIFEN_SIGN_P12_PASSWORD") or os.getenv("SIFEN_P12_PASSWORD") or "",
        help='Contraseña del archivo P12 de firma'
    )
    parser.add_argument(
        '--allow-placeholder',
        action='store_true',
        help='Permite usar placeholders genéricos (solo para testing)'
    )
    return parser.parse_args()

def save_crash_artifacts(
    env: str,
    attempt: int,
    request_bytes: Optional[bytes] = None,
    response_bytes: Optional[bytes] = None,
    metadata: Optional[Dict[str, Any]] = None,
    exception: Optional[Exception] = None,
    resolved_certs: Optional[Dict[str, Any]] = None
) -> None:
    """
    Guarda artifacts completos incluso si falla el envío.
    
    Args:
        env: Ambiente SIFEN
        attempt: Número de intento
        request_bytes: SOAP request enviado
        response_bytes: SOAP response recibido
        metadata: Metadata del intento
        exception: Excepción si falló
        resolved_certs: Info de certificados resueltos
    """
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")[:-3]
    artifacts_dir = Path("artifacts")
    artifacts_dir.mkdir(exist_ok=True)
    
    # Metadata completa del crash
    crash_metadata = {
        "timestamp": timestamp,
        "environment": env,
        "attempt": attempt,
        "crash": True,
        "exception": {
            "type": type(exception).__name__ if exception else None,
            "message": str(exception) if exception else None,
            "traceback": traceback.format_exc() if exception else None,
        } if exception else None,
        "resolved_certs": resolved_certs or {},
        "metadata": metadata or {},
    }
    
    # Guardar metadata
    meta_path = artifacts_dir / f"crash_metadata_{env}_{timestamp}_attempt_{attempt}.json"
    meta_path.write_text(json.dumps(crash_metadata, indent=2, default=str), encoding='utf-8')
    logger.info(f"📝 Crash metadata guardada: {meta_path}")
    
    # Guardar request si existe
    if request_bytes:
        req_path = artifacts_dir / f"crash_request_{env}_{timestamp}_attempt_{attempt}.xml"
        req_path.write_bytes(request_bytes)
        logger.info(f"📝 Crash request guardado: {req_path}")
    
    # Guardar response si existe
    if response_bytes:
        resp_path = artifacts_dir / f"crash_response_{env}_{timestamp}_attempt_{attempt}.xml"
        resp_path.write_bytes(response_bytes)
        logger.info(f"📝 Crash response guardado: {resp_path}")
    
    # Guardar exception en archivo txt
    if exception:
        exc_path = artifacts_dir / f"crash_exception_{env}_{timestamp}_attempt_{attempt}.txt"
        exc_path.write_text(
            f"Type: {type(exception).__name__}\n"
            f"Message: {str(exception)}\n"
            f"\n--- Traceback ---\n"
            f"{traceback.format_exc()}",
            encoding='utf-8'
        )
        logger.info(f"📝 Crash exception guardada: {exc_path}")

def send_lote_with_retries(
    env: str,
    zip_bytes: bytes,
    max_retries: int,
    backoff_base: float,
    backoff_max: float
) -> Tuple[Dict[str, Any], bytes, bytes, int]:
    """
    Envía lote a SIFEN con retries y backoff.
    
    Returns:
        Tuple (metadata, response_bytes, request_bytes, attempt_count)
    """
    from app.sifen_client.soap_client import SoapClient
    from app.sifen_client.config import get_sifen_config
    from tools.send_sirecepde import build_r_envio_lote_xml
    import base64
    import hashlib
    import requests.exceptions
    
    # Guardar info de certificados resueltos
    resolved_certs = get_resolved_certs_info()
    
    for attempt in range(1, max_retries + 1):
        try:
            logger.info(f"🚀 Enviando lote (intento {attempt}/{max_retries}) a SIFEN {env}...")
            
            # Obtener configuración y cliente
            config = get_sifen_config(env=env)
            client = SoapClient(config)
            
            # Calcular hashes
            zip_sha256 = hashlib.sha256(zip_bytes).hexdigest()
            zip_base64 = base64.b64encode(zip_bytes).decode('ascii')
            
            # Construir rEnvioLote XML
            r_envio_lote_xml = build_r_envio_lote_xml(did=1, xml_bytes=b'', zip_base64=zip_base64)
            request_sha256 = hashlib.sha256(r_envio_lote_xml.encode('utf-8')).hexdigest()
            
            # Enviar
            response_dict = client.recepcion_lote(r_envio_lote_xml)
            response_bytes = response_dict.get('response_xml', b'')
            
            if not response_bytes and 'parsed_fields' in response_dict and 'xml' in response_dict['parsed_fields']:
                response_bytes = response_dict['parsed_fields']['xml'].encode('utf-8')
            
            # Obtener request bytes
            request_bytes = b''
            try:
                request_bytes = Path("artifacts/soap_last_request_SENT.xml").read_bytes()
            except Exception:
                logger.warning("No se pudo leer el SOAP request enviado")
            
            # Enriquecer metadata
            enriched_metadata = {
                "attempt": attempt,
                "post_url": response_dict.get("post_url"),
                "wsdl_url": response_dict.get("wsdl_url"),
                "http_status": response_dict.get("http_status"),
                "request_sha256": request_sha256,
                "response_sha256": hashlib.sha256(response_bytes).hexdigest(),
                "zip_sha256": zip_sha256,
                "resolved_certs": resolved_certs,
                **response_dict
            }
            
            logger.info(f"✅ Envío exitoso (intento {attempt})")
            return enriched_metadata, response_bytes, request_bytes, attempt
            
        except (requests.exceptions.ConnectionError,
                requests.exceptions.RemoteDisconnected,
                requests.exceptions.ReadTimeout,
                requests.exceptions.ConnectTimeout,
                ConnectionResetError) as e:
            
            logger.error(f"❌ Error de red (intento {attempt}/{max_retries}): {type(e).__name__}: {e}")
            
            # Guardar crash artifacts
            crash_metadata = {"error_type": type(e).__name__, "error_message": str(e)}
            request_bytes = b''
            try:
                request_bytes = Path("artifacts/soap_last_request_SENT.xml").read_bytes()
            except Exception:
                pass
            
            save_crash_artifacts(
                env=env,
                attempt=attempt,
                request_bytes=request_bytes,
                metadata=crash_metadata,
                exception=e,
                resolved_certs=resolved_certs
            )
            
            # Si es el último intento, relanzar
            if attempt == max_retries:
                logger.error(f"🔥 Todos los intentos fallaron. Último error: {e}")
                raise
            
            # Calcular backoff con jitter
            delay = min(backoff_base * (2 ** (attempt - 1)), backoff_max)
            jitter = delay * 0.25 * (random.random() * 2 - 1)
            final_delay = delay + jitter
            
            logger.warning(f"⏳ Reintentando en {final_delay:.2f}s...")
            time.sleep(final_delay)
            
        except Exception as e:
            # Error no recuperable (ej: XML mal formado, certificado inválido)
            logger.error(f"❌ Error no recuperable (intento {attempt}): {type(e).__name__}: {e}")
            
            # Guardar crash artifacts
            request_bytes = b''
            try:
                request_bytes = Path("artifacts/soap_last_request_SENT.xml").read_bytes()
            except Exception:
                pass
            
            save_crash_artifacts(
                env=env,
                attempt=attempt,
                request_bytes=request_bytes,
                exception=e,
                resolved_certs=resolved_certs
            )
            
            # No reintentar errores no recuperables
            raise
    
    # Nunca debería llegar aquí
    raise RuntimeError("Error inesperado en send_lote_with_retries")

def create_minimal_lote(cert_path: str, cert_password: str, allow_placeholder: bool = False) -> bytes:
    """
    Crea un lote mínimo válido usando el pipeline existente
    """
    from tools.send_sirecepde import build_and_sign_lote_from_xml
    from tools.xml_min_builder import build_minimal_de_v150
    
    logger.info("Construyendo DE mínimo...")
    de_xml = build_minimal_de_v150(allow_placeholder=allow_placeholder)
    
    # Guardar DE temporal
    temp_de_path = Path("artifacts/crashproof_de_minimal.xml")
    temp_de_path.parent.mkdir(exist_ok=True)
    temp_de_path.write_bytes(de_xml)
    
    logger.info("Construyendo y firmando lote...")
    zip_base64, lote_xml_bytes, zip_bytes, lote_did = build_and_sign_lote_from_xml(
        de_xml,
        cert_path=cert_path,
        cert_password=cert_password,
        return_debug=True
    )
    
    # Guardar lote para debug
    temp_lote_path = Path("artifacts/crashproof_lote.xml")
    temp_lote_path.write_bytes(lote_xml_bytes)
    
    return zip_bytes

def main() -> int:
    """Punto de entrada principal"""
    import traceback
    args = parse_args()
    
    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)
    
    logger.info("=== Smoke Test Crash-Proof ===")
    logger.info(f"Ambiente: {args.env}")
    logger.info(f"Max retries: {args.max_retries}")
    logger.info(f"Backoff: {args.backoff_base}s - {args.backoff_max}s")
    
    # Validar y resolver certificados
    try:
        logger.info("=== Resolviendo certificados ===")
        
        # Validar certificado de firma
        if not args.sign_p12_path or not args.sign_p12_password:
            # Usar el resolver automático
            sign_cert_path, sign_cert_password = resolve_signing_cert()
        else:
            # Validar el proporcionado
            validate_no_self_signed(args.sign_p12_path, "firma XML")
            sign_cert_path, sign_cert_password = args.sign_p12_path, args.sign_p12_password
        
        # Resolver mTLS (para validación)
        mtls_cert, mtls_key_or_pass, is_pem = resolve_mtls_cert()
        
        # Guardar artifact con certificados resueltos
        cert_artifact = save_resolved_certs_artifact(
            signing_cert=sign_cert_path,
            mtls_cert=mtls_cert,
            mtls_key=mtls_key_or_pass if is_pem else None,
            mtls_mode="PEM" if is_pem else "P12"
        )
        
        logger.info(f"✅ Certificados resueltos: {Path(cert_artifact).name}")
        
    except Exception as e:
        logger.error(f"❌ Error resolviendo certificados: {e}")
        return 1
    
    try:
        # 1. Crear lote mínimo
        logger.info("=== Paso 1: Creando lote mínimo ===")
        zip_bytes = create_minimal_lote(sign_cert_path, sign_cert_password, args.allow_placeholder)
        
        # 2. Enviar con retries
        logger.info("=== Paso 2: Enviando con retries ===")
        metadata, response_bytes, request_bytes, attempt_count = send_lote_with_retries(
            env=args.env,
            zip_bytes=zip_bytes,
            max_retries=args.max_retries,
            backoff_base=args.backoff_base,
            backoff_max=args.backoff_max
        )
        
        # 3. Guardar artifacts finales
        logger.info("=== Paso 3: Guardando artifacts ===")
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        artifacts_dir = Path("artifacts")
        
        # Metadata final
        final_metadata = {
            **metadata,
            "final_attempt": attempt_count,
            "crashproof": True,
            "success": True
        }
        
        meta_path = artifacts_dir / f"crashproof_final_{args.env}_{timestamp}.json"
        meta_path.write_text(json.dumps(final_metadata, indent=2, default=str), encoding='utf-8')
        
        # Request y response
        if request_bytes:
            req_path = artifacts_dir / f"crashproof_request_{args.env}_{timestamp}.xml"
            req_path.write_bytes(request_bytes)
        
        if response_bytes:
            resp_path = artifacts_dir / f"crashproof_response_{args.env}_{timestamp}.xml"
            resp_path.write_bytes(response_bytes)
        
        # 4. Clasificar resultado
        logger.info("=== Paso 4: Resultado ===")
        d_cod_res = metadata.get("response_dCodRes", "").strip()
        
        if d_cod_res == "0300":
            logger.info("✅ Envío exitoso - Lote encolado")
            exit_code = 0
        elif d_cod_res == "0301":
            logger.error("❌ Lote no encolado (0301)")
            exit_code = 1
        else:
            logger.error(f"❌ Respuesta inesperada (dCodRes={d_cod_res})")
            exit_code = 1
        
        # Resumen
        logger.info("=== Resumen ===")
        logger.info(f"Intentos usados: {attempt_count}/{args.max_retries}")
        logger.info(f"Endpoint: {metadata.get('post_url')}")
        logger.info(f"HTTP Status: {metadata.get('http_status')}")
        logger.info(f"dCodRes: {d_cod_res}")
        logger.info(f"Certificado firma: {Path(sign_cert_path).name}")
        logger.info(f"Modo mTLS: {'PEM' if is_pem else 'P12'}")
        
        return exit_code
        
    except Exception as e:
        logger.error(f"🔥 Error fatal en smoke test: {e}", exc_info=True)
        
        # Guardar crash artifact final
        try:
            save_crash_artifacts(
                env=args.env,
                attempt=args.max_retries,
                exception=e,
                resolved_certs=get_resolved_certs_info()
            )
        except Exception as save_e:
            logger.error(f"No se pudo guardar crash artifact: {save_e}")
        
        return 1

if __name__ == "__main__":
    sys.exit(main())
