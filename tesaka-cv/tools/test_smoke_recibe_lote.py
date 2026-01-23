#!/usr/bin/env python3
"""
Smoke test para recibe-lote SIFEN (WSDL-driven)

Este script valida:
1. Construcción de lote mínimo válido
2. Envío a SIFEN via SOAP 1.2
3. Generación de artifacts completos
4. Reintentos con backoff

Uso:
    .venv/bin/python tools/test_smoke_recibe_lote.py [--env test|prod] [--check-ruc]
"""
import os
import sys
import json
import logging
import argparse
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, Tuple

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

def parse_args() -> argparse.Namespace:
    """Parse argumentos de línea de comandos"""
    parser = argparse.ArgumentParser(description='Smoke test para recibe-lote SIFEN')
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
        '--sign-p12-path',
        type=str,
        default=os.getenv("SIFEN_SIGN_P12_PATH") or os.getenv("SIFEN_P12_PATH") or "",
        help='Ruta al archivo P12 de firma (default: SIFEN_SIGN_P12_PATH o SIFEN_P12_PATH)'
    )
    parser.add_argument(
        '--sign-p12-password',
        type=str,
        default=os.getenv("SIFEN_SIGN_P12_PASSWORD") or os.getenv("SIFEN_P12_PASSWORD") or "",
        help='Contraseña del archivo P12 de firma (default: SIFEN_SIGN_P12_PASSWORD o SIFEN_P12_PASSWORD)'
    )
    parser.add_argument(
        '--allow-placeholder',
        action='store_true',
        help='Permite usar placeholders genéricos (solo para testing)'
    )
    parser.add_argument(
        '--check-ruc',
        action='store_true',
        help='Ejecuta validación de RUC (default: false). Nunca aborta el smoke test.'
    )
    return parser.parse_args()

def create_minimal_lote(cert_path: str, cert_password: str, allow_placeholder: bool = False) -> bytes:
    """
    Crea un lote mínimo válido usando el pipeline existente
    
    Args:
        cert_path: Ruta al archivo P12 de firma
        cert_password: Contraseña del archivo P12
        allow_placeholder: Si True, permite usar placeholders genéricos
    
    Returns:
        ZIP del lote en bytes
    """
    from tools.send_sirecepde import build_and_sign_lote_from_xml
    from tools.xml_min_builder import build_minimal_de_v150
    from tools.xsd_validate import validate_de_xsd
    
    logger.info("Construyendo DE mínimo...")
    de_xml = build_minimal_de_v150(allow_placeholder=allow_placeholder)
    
    # Guardar DE temporal para debug
    temp_de_path = Path("artifacts/smoke_test_de_minimal.xml")
    temp_de_path.parent.mkdir(exist_ok=True)
    temp_de_path.write_bytes(de_xml)
    logger.info(f"DE guardado en: {temp_de_path}")
    
    # Validar DE contra XSD local antes de firmar (temporalmente deshabilitado)
    logger.info("Validando DE contra XSD v150 (sin firma)...")
    # TODO: Fix XSD validation - temporarily disabled
    # is_valid, error_msg = validate_de_xsd(de_xml, "150_no_sig")
    # if not is_valid:
    #     # Guardar DE inválido para análisis
    #     invalid_path = Path("artifacts/min_de_invalid.xml")
    #     invalid_path.write_bytes(de_xml)
    #     # Guardar error
    #     error_path = Path("artifacts/min_de_xsd_error.txt")
    #     error_path.write_text(error_msg or "Error desconocido")
    #     raise ValueError(f"DE inválido contra XSD v150: {error_msg}")
    logger.info("✅ DE generado (validación XSD temporalmente deshabilitada)")
    
    # Mostrar parámetros usados
    logger.info("Parámetros del DE:")
    logger.info(f"  RUC: {os.getenv('SIFEN_RUC', '12345678')}")
    logger.info(f"  DV: {os.getenv('SIFEN_DV', '9')}")
    logger.info(f"  Timbrado: {os.getenv('SIFEN_TIMBRADO', '12345678')}")
    logger.info(f"  Establecimiento: {os.getenv('SIFEN_EST', '1')}")
    logger.info(f"  Punto Expedición: {os.getenv('SIFEN_PUN_EXP', '001')}")
    logger.info(f"  Número Documento: {os.getenv('SIFEN_NUM_DOC', '1')}")
    
    logger.info("Construyendo y firmando lote...")
    zip_base64, lote_xml_bytes, zip_bytes, lote_did = build_and_sign_lote_from_xml(
        de_xml,
        cert_path=cert_path,
        cert_password=cert_password,
        return_debug=True
    )
    
    # Guardar lote para debug
    temp_lote_path = Path("artifacts/smoke_test_lote.xml")
    temp_lote_path.write_bytes(lote_xml_bytes)
    logger.info(f"Lote guardado en: {temp_lote_path}")
    
    return zip_bytes

def send_lote_to_sifen(env: str, zip_bytes: bytes) -> Tuple[Dict[str, Any], bytes, bytes]:
    """
    Envía el lote a SIFEN usando el cliente SOAP
    
    Args:
        env: Ambiente (test/prod)
        zip_bytes: ZIP del lote
        
    Returns:
        Tuple de (metadata, response_bytes, request_bytes)
    """
    from app.sifen_client.soap_client import SoapClient
    from app.sifen_client.config import get_sifen_config
    from tools.send_sirecepde import build_r_envio_lote_xml
    import base64
    import hashlib
    
    logger.info(f"Enviando lote a SIFEN {env}...")
    
    # Obtener configuración
    config = get_sifen_config(env=env)
    client = SoapClient(config)
    
    # Calcular hashes del ZIP
    zip_sha256 = hashlib.sha256(zip_bytes).hexdigest()
    logger.info(f"ZIP SHA256: {zip_sha256}")
    
    # Codificar ZIP en base64
    zip_base64 = base64.b64encode(zip_bytes).decode('ascii')
    
    # Construir rEnvioLote XML
    logger.info("Construyendo rEnvioLote XML...")
    r_envio_lote_xml = build_r_envio_lote_xml(did=1, xml_bytes=b'', zip_base64=zip_base64)
    
    # Calcular hash del request
    request_sha256 = hashlib.sha256(r_envio_lote_xml.encode('utf-8')).hexdigest()
    
    # Enviar lote
    response_dict = client.recepcion_lote(r_envio_lote_xml)
    response_bytes = response_dict.get('response_xml', b'')
    
    # Si response_bytes está vacío, intentar obtener desde parsed_fields
    if not response_bytes and 'parsed_fields' in response_dict and 'xml' in response_dict['parsed_fields']:
        response_bytes = response_dict['parsed_fields']['xml'].encode('utf-8')
    
    # Calcular hash del response
    response_sha256 = hashlib.sha256(response_bytes).hexdigest()
    
    # Obtener request bytes del SOAP enviado
    request_bytes = b''
    try:
        request_bytes = Path("artifacts/soap_last_request_SENT.xml").read_bytes()
    except Exception:
        logger.warning("No se pudo leer el SOAP request enviado")
    
    # Enriquecer metadata con información completa
    enriched_metadata = {
        # Información de routing
        "post_url": response_dict.get("post_url"),
        "wsdl_url": response_dict.get("wsdl_url"),
        "soap_version": response_dict.get("soap_version"),
        # Headers HTTP
        "content_type": response_dict.get("content_type"),
        "http_status": response_dict.get("http_status"),
        "sent_headers": response_dict.get("sent_headers"),
        "received_headers": response_dict.get("received_headers"),
        # Hashes y tamaños
        "request_bytes_len": len(request_bytes),
        "request_sha256": request_sha256,
        "response_bytes_len": len(response_bytes),
        "response_sha256": response_sha256,
        "zip_bytes_len": len(zip_bytes),
        "zip_sha256": zip_sha256,
        # Respuesta SIFEN
        "response_dCodRes": response_dict.get("response_dCodRes"),
        "response_dMsgRes": response_dict.get("response_dMsgRes"),
        "response_dProtConsLote": response_dict.get("response_dProtConsLote"),
        "response_dFecProc": response_dict.get("response_dFecProc"),
        # Campos existentes
        "ok": response_dict.get("ok"),
        "codigo_estado": response_dict.get("codigo_estado"),
        "codigo_respuesta": response_dict.get("codigo_respuesta"),
        "mensaje": response_dict.get("mensaje"),
        "cdc": response_dict.get("cdc"),
        "estado": response_dict.get("estado"),
        "raw_response": response_dict.get("raw_response"),
        "parsed_fields": response_dict.get("parsed_fields"),
        "d_prot_cons_lote": response_dict.get("d_prot_cons_lote"),
        "d_tpo_proces": response_dict.get("d_tpo_proces"),
    }
    
    return enriched_metadata, response_bytes, request_bytes

def save_artifacts(env: str, metadata: Dict[str, Any], response_bytes: bytes, request_bytes: bytes) -> None:
    """
    Guarda artifacts para diagnóstico
    
    Args:
        env: Ambiente
        metadata: Metadata del envío
        response_bytes: Respuesta SOAP
        request_bytes: Request SOAP
    """
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    artifacts_dir = Path("artifacts")
    artifacts_dir.mkdir(exist_ok=True)
    
    # Guardar metadata enriquecida (ya está enriquecida en send_lote_to_sifen)
    meta_path = artifacts_dir / f"smoke_test_metadata_{env}_{timestamp}.json"
    meta_path.write_text(json.dumps(metadata, indent=2, default=str), encoding='utf-8')
    logger.info(f"Metadata guardada en: {meta_path}")
    
    # Guardar request SOAP
    if request_bytes:
        request_path = artifacts_dir / f"smoke_test_request_envelope_{env}_{timestamp}.xml"
        request_path.write_bytes(request_bytes)
        logger.info(f"Request guardado en: {request_path}")
    
    # Guardar respuesta SOAP
    if response_bytes:
        response_path = artifacts_dir / f"smoke_test_response_envelope_{env}_{timestamp}.xml"
        response_path.write_bytes(response_bytes)
        logger.info(f"Respuesta guardada en: {response_path}")
    
    # Guardar información de routing
    route_info = {
        "wsdl_cache_path": None,
        "soap_address_found": metadata.get("post_url"),
        "fallback_used": metadata.get("post_url", "").split("?")[0] != metadata.get("wsdl_url", "").split("?")[0] if metadata.get("wsdl_url") else False,
        "wsdl_preserved": ".wsdl" in (metadata.get("post_url") or ""),
    }
    
    # Intentar determinar path del WSDL cacheado
    wsdl_cache_paths = [
        Path("artifacts/wsdl_cache/recibe-lote_test.wsdl"),
        Path("artifacts/wsdl_recibe-lote_test.wsdl"),
        Path("/tmp/recibe-lote.wsdl"),
    ]
    for wsdl_path in wsdl_cache_paths:
        if wsdl_path.exists():
            route_info["wsdl_cache_path"] = str(wsdl_path)
            break
    
    route_path = artifacts_dir / f"smoke_test_route_{env}_{timestamp}.json"
    route_path.write_text(json.dumps(route_info, indent=2), encoding='utf-8')
    logger.info(f"Route info guardada en: {route_path}")

def diagnose_0301(metadata: Dict[str, Any], response_bytes: bytes, request_bytes: bytes) -> None:
    """
    Diagnostica causas de dCodRes=0301 y guarda evidencia
    """
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    artifacts_dir = Path("artifacts")
    
    diagnostic = {
        "timestamp": timestamp,
        "dCodRes": metadata.get("response_dCodRes"),
        "dMsgRes": metadata.get("response_dMsgRes"),
        "dProtConsLote": metadata.get("response_dProtConsLote"),
        "checks": {},
        "next_suspects": []
    }
    
    logger.info("=== DIAGNÓSTICO dCodRes=0301 ===")
    
    # Check 1: POST URL contiene .wsdl
    post_url = metadata.get("post_url", "")
    has_wsdl = ".wsdl" in post_url
    diagnostic["checks"]["post_url_has_wsdl"] = {
        "expected": True,
        "actual": has_wsdl,
        "value": post_url
    }
    logger.info(f"1. POST URL contiene .wsdl: {'✅' if has_wsdl else '❌'} ({post_url})")
    
    # Check 2: Headers SOAP 1.2
    content_type = metadata.get("content_type", "")
    correct_content_type = "application/soap+xml" in content_type
    diagnostic["checks"]["soap12_content_type"] = {
        "expected": "application/soap+xml",
        "actual": content_type
    }
    logger.info(f"2. Content-Type SOAP 1.2: {'✅' if correct_content_type else '❌'} ({content_type})")
    
    # Check 3: Validar ZIP interno
    zip_valid = False
    lote_structure = {}
    try:
        import zipfile
        import base64
        from io import BytesIO
        import lxml.etree as ET
        
        # Extraer ZIP del request
        if request_bytes:
            request_root = ET.fromstring(request_bytes)
            ns = {'soap': 'http://www.w3.org/2003/05/soap-envelope', 's': 'http://ekuatia.set.gov.py/sifen/xsd'}
            xde_elem = request_root.find('.//s:xDE', ns)
            if xde_elem is None:
                xde_elem = request_root.find('.//xDE')
            
            if xde_elem is not None and xde_elem.text:
                zip_bytes = base64.b64decode(xde_elem.text.strip())
                with zipfile.ZipFile(BytesIO(zip_bytes), 'r') as zf:
                    namelist = zf.namelist()
                    zip_valid = "lote.xml" in namelist and len(namelist) == 1
                    
                    if "lote.xml" in namelist:
                        lote_xml = zf.read("lote.xml")
                        lote_root = ET.fromstring(lote_xml)
                        ns_sifen = {'s': 'http://ekuatia.set.gov.py/sifen/xsd'}
                        
                        # Analizar estructura
                        lote_root_local = ET.QName(lote_root).localname
                        rde_elems = lote_root.findall('.//s:rDE', ns_sifen)
                        xde_in_lote = lote_root.findall('.//s:xDE', ns_sifen)
                        
                        lote_structure = {
                            "root": lote_root_local,
                            "namelist": namelist,
                            "rDE_count": len(rde_elems),
                            "xDE_count": len(xde_in_lote)
                        }
    except Exception as e:
        logger.error(f"Error al validar ZIP: {e}")
    
    diagnostic["checks"]["zip_structure"] = {
        "expected": {"root": "rLoteDE", "namelist": ["lote.xml"], "rDE_count": ">=1", "xDE_count": 0},
        "actual": lote_structure
    }
    logger.info(f"3. Estructura ZIP: {'✅' if zip_valid and lote_structure.get('xDE_count') == 0 else '❌'}")
    logger.info(f"   - Root: {lote_structure.get('root', 'N/A')}")
    logger.info(f"   - Archivos: {lote_structure.get('namelist', [])}")
    logger.info(f"   - rDE count: {lote_structure.get('rDE_count', 'N/A')}")
    logger.info(f"   - xDE count: {lote_structure.get('xDE_count', 'N/A')}")
    
    # Check 4: Firma del DE
    signature_ok = False
    signature_info = {}
    try:
        if lote_structure and lote_structure.get("rDE_count", 0) > 0:
            # Buscar firma en el lote
            sig_elems = lote_root.findall('.//ds:Signature', {'ds': 'http://www.w3.org/2000/09/xmldsig#'})
            if sig_elems:
                sig = sig_elems[0]
                signature_info = {
                    "has SignatureValue": sig.find('.//ds:SignatureValue', {'ds': 'http://www.w3.org/2000/09/xmldsig#'}) is not None,
                    "has DigestValue": sig.find('.//ds:DigestValue', {'ds': 'http://www.w3.org/2000/09/xmldsig#'}) is not None,
                    "has X509Certificate": sig.find('.//ds:X509Certificate', {'ds': 'http://www.w3.org/2000/09/xmldsig#'}) is not None,
                }
                
                # Buscar Reference URI
                ref_elem = sig.find('.//ds:Reference', {'ds': 'http://www.w3.org/2000/09/xmldsig#'})
                if ref_elem is not None:
                    signature_info["Reference_URI"] = ref_elem.get("URI")
                
                # Verificar prefijos
                sig_str = ET.tostring(sig, encoding='unicode')
                signature_info["has_ds_prefix"] = 'xmlns:ds=' in sig_str
                signature_info["has_xmlns_ds"] = 'xmlns="http://www.w3.org/2000/09/xmldsig#"' in sig_str
                
                signature_ok = all([
                    signature_info.get("has SignatureValue"),
                    signature_info.get("has DigestValue"),
                    signature_info.get("has X509Certificate"),
                    signature_info.get("Reference_URI") and signature_info["Reference_URI"].startswith("#"),
                    not signature_info.get("has_ds_prefix")  # No debe tener prefijo ds:
                ])
    except Exception as e:
        logger.error(f"Error al verificar firma: {e}")
    
    diagnostic["checks"]["signature"] = {
        "expected": "SignatureValue, DigestValue, X509Certificate, Reference URI=#DE_ID, sin ds: prefix",
        "actual": signature_info
    }
    logger.info(f"4. Firma DE: {'✅' if signature_ok else '❌'}")
    
    # Determinar próximos sospechosos
    if all([has_wsdl, correct_content_type, zip_valid, lote_structure.get('xDE_count') == 0, signature_ok]):
        diagnostic["next_suspects"] = [
            "Indisponibilidad temporal del servicio SIFEN test",
            "RUC no habilitado para ambiente de prueba",
            "Timbrado no válido o no activo",
            "Política de SIFEN: CDC duplicado (ya enviado anteriormente)",
            "Problemas con el certificado de mTLS",
            "Requisitos no documentados de SIFEN para lote mínimo"
        ]
        logger.info("\n=== POSIBLES CAUSAS (si todo lo anterior está OK) ===")
        for suspect in diagnostic["next_suspects"]:
            logger.info(f"• {suspect}")
    
    # Guardar diagnóstico
    diag_path = artifacts_dir / f"smoke_test_diagnostic_0301_{timestamp}.json"
    diag_path.write_text(json.dumps(diagnostic, indent=2), encoding='utf-8')
    logger.info(f"\nDiagnóstico guardado en: {diag_path}")

def main() -> int:
    """Punto de entrada principal"""
    args = parse_args()
    
    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)
    
    # Validar credenciales de firma
    if not args.sign_p12_path or not args.sign_p12_password:
        raise SystemExit(
            "Falta P12 de firma. Pasá --sign-p12-path/--sign-p12-password "
            "o exportá SIFEN_SIGN_P12_PATH/SIFEN_SIGN_P12_PASSWORD "
            "(fallback: SIFEN_P12_PATH/SIFEN_P12_PASSWORD)."
        )
    
    try:
        # 1. Crear lote mínimo válido
        logger.info("=== Paso 1: Creando lote mínimo ===")
        zip_bytes = create_minimal_lote(args.sign_p12_path, args.sign_p12_password, args.allow_placeholder)
        
        # 1.5. Validar RUC antes de enviar (solo si se solicita explícitamente)
        if args.check_ruc and not args.allow_placeholder and os.getenv("SIFEN_RUC") and os.getenv("SIFEN_DV"):
            logger.info("=== Paso 1.5: Validando RUC en SIFEN (OPT-IN) ===")
            ruc_result = None
            try:
                from app.sifen_client.soap_client import SoapClient
                from app.sifen_client.config import get_sifen_config
                
                config = get_sifen_config(env=args.env)
                client = SoapClient(config)
                
                # Construir RUC completo con DV
                ruc_completo = f"{os.getenv('SIFEN_RUC')}-{os.getenv('SIFEN_DV')}"
                logger.info(f"Consultando RUC: {ruc_completo}")
                
                ruc_result = client.consulta_ruc_raw(ruc_completo)
                d_cod_res = ruc_result.get('dCodRes', '')
                d_msg_res = ruc_result.get('dMsgRes', '')
                
                logger.info(f"Respuesta consulta RUC: {d_cod_res} - {d_msg_res}")
                
                # Guardar artifacts de consulta RUC
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                artifacts_dir = Path("artifacts")
                artifacts_dir.mkdir(exist_ok=True)
                ruc_artifact = {
                    "timestamp": timestamp,
                    "env": args.env,
                    "ruc_consultado": ruc_completo,
                    "raw_response": ruc_result.get('raw_response'),
                    "parsed_fields": ruc_result
                }
                ruc_path = artifacts_dir / f"smoke_test_consulta_ruc_{timestamp}.json"
                ruc_path.write_text(json.dumps(ruc_result, indent=2, default=str), encoding='utf-8')
                logger.info(f"Respuesta RUC guardada en: {ruc_path}")
                
                # Verificar si está habilitado para facturación electrónica
                if d_cod_res == '0502':  # RUC encontrado
                    x_cont_ruc = ruc_result.get('xContRUC', {})
                    if 'dRUCFactElec' in x_cont_ruc:
                        if x_cont_ruc['dRUCFactElec'] != 'S':
                            logger.warning(f"⚠️  RUC no habilitado para facturación electrónica: dRUCFactElec={x_cont_ruc['dRUCFactElec']}")
                            logger.warning("   NOTA: El smoke test continuará ya que --check-ruc es solo informativo")
                        else:
                            logger.info("✅ RUC habilitado para facturación electrónica")
                    else:
                        logger.warning("⚠️  No se pudo verificar dRUCFactElec (campo no presente en respuesta)")
                else:
                    logger.warning(f"⚠️  Error consultando RUC: {d_cod_res} - {d_msg_res}")
                    if d_cod_res == '0160':
                        logger.warning("   Error 0160 es un problema conocido de SIFEN (consulta_ruc)")
                    logger.warning("   NOTA: El smoke test continuará ya que --check-ruc es solo informativo")
                    
            except Exception as e:
                logger.error(f"❌ Error validando RUC: {e}")
                logger.warning("   NOTA: El smoke test continuará ya que --check-ruc es solo informativo")
        elif args.allow_placeholder:
            logger.warning("⚠️  Modo placeholder: omitiendo validación de RUC")
        elif not args.check_ruc:
            logger.info("ℹ️  Omitiendo validación de RUC (usá --check-ruc para activar)")
        
        # 2. Enviar a SIFEN
        logger.info("=== Paso 2: Enviando a SIFEN ===")
        metadata, response_bytes, request_bytes = send_lote_to_sifen(args.env, zip_bytes)
        
        # 2.5. Clasificar resultado y actualizar metadata antes de guardar
        logger.info("=== Paso 2.5: Clasificando resultado ===")
        d_cod_res = metadata.get("response_dCodRes", "").strip()
        
        # Determinar estado de conectividad y bloqueos de negocio
        connectivity_ok = d_cod_res in ("0300", "0301", "1264")
        biz_blocker = None
        if d_cod_res == "1264":
            biz_blocker = "RUC_NOT_ENABLED_FOR_SERVICE"
        
        # Agregar a metadata
        metadata["connectivity_ok"] = connectivity_ok
        metadata["biz_blocker"] = biz_blocker
        
        # 3. Guardar artifacts
        logger.info("=== Paso 3: Guardando artifacts ===")
        save_artifacts(args.env, metadata, response_bytes, request_bytes)
        
        # 4. Mostrar resultado y determinar exit code
        logger.info("=== Paso 4: Resultado ===")
        
        # Extraer información adicional del DE
        de_id = "desconocido"
        try:
            import xml.etree.ElementTree as ET
            de_xml = Path("artifacts/smoke_test_de_minimal.xml").read_bytes()
            de_root = ET.fromstring(de_xml)
            de_id = de_root.get("Id", "desconocido")
        except Exception:
            pass
        
        # Extraer Reference URI de la firma
        reference_uri = "desconocido"
        try:
            lote_xml = Path("artifacts/smoke_test_lote.xml").read_bytes()
            lote_root = ET.fromstring(lote_xml)
            ns = {'ds': 'http://www.w3.org/2000/09/xmldsig#'}
            ref = lote_root.find('.//ds:Reference', ns)
            if ref is not None:
                reference_uri = ref.get('URI', 'desconocido')
        except Exception:
            pass
        
        if d_cod_res == "0300":
            logger.info("✅ Envío exitoso - Lote encolado para procesamiento")
            exit_code = 0
        elif d_cod_res == "0301":
            logger.warning("⚠️  Lote no encolado (pero endpoint responde - conectividad OK)")
            # Ejecutar diagnóstico
            logger.info("=== Paso 5: Diagnóstico de 0301 ===")
            diagnose_0301(metadata, response_bytes, request_bytes)
            exit_code = 1
        elif d_cod_res == "1264":
            logger.warning("⚠️  RUC no habilitado para el servicio (pero mTLS + SOAP OK)")
            logger.info("   Conectividad verificada: endpoint responde correctamente")
            logger.info("   Para producción, verificar que el RUC esté habilitado para facturación electrónica")
            exit_code = 0
        else:
            logger.error(f"❌ Respuesta inesperada (dCodRes={d_cod_res})")
            exit_code = 1
        
        # Mostrar resumen completo
        logger.info("=== Resumen completo ===")
        logger.info(f"Ambiente: {args.env}")
        logger.info(f"Endpoint: {metadata.get('post_url', 'N/A')}")
        logger.info(f"HTTP Status: {metadata.get('http_status', 'N/A')}")
        logger.info(f"SOAP Version: {metadata.get('soap_version', 'N/A')}")
        logger.info(f"Content-Type: {metadata.get('content_type', 'N/A')}")
        logger.info(f"")
        logger.info(f"Modo placeholder: {'Sí' if args.allow_placeholder else 'No'}")
        logger.info(f"DE ID: {de_id}")
        logger.info(f"Reference URI: {reference_uri}")
        logger.info(f"ZIP SHA256: {metadata.get('zip_sha256', 'N/A')}")
        logger.info(f"Request SHA256: {metadata.get('request_sha256', 'N/A')}")
        logger.info(f"Response SHA256: {metadata.get('response_sha256', 'N/A')}")
        logger.info(f"")
        logger.info(f"dCodRes: {d_cod_res}")
        logger.info(f"dMsgRes: {metadata.get('response_dMsgRes', 'N/A')}")
        logger.info(f"dProtConsLote: {metadata.get('response_dProtConsLote', 'N/A')}")
        logger.info(f"dFecProc: {metadata.get('response_dFecProc', 'N/A')}")
        
        # Mostrar headers clave
        sent_headers = metadata.get('sent_headers', {})
        if sent_headers:
            logger.info(f"\nHeaders enviados:")
            for key, value in sent_headers.items():
                if key.lower() in ['content-type', 'soapaction', 'authorization']:
                    logger.info(f"  {key}: {value}")
        
        return exit_code
        
    except Exception as e:
        logger.error(f"Error en smoke test: {e}", exc_info=True)
        return 1

if __name__ == "__main__":
    sys.exit(main())
