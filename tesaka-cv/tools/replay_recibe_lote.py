#!/usr/bin/env python3
"""
Script para re-enviar exactamente el mismo request a SIFEN (replay).
Usa el último request guardado para aislar problemas de transporte.
"""

import argparse
import json
import sys
from pathlib import Path
import requests
from datetime import datetime

# Agregar el path del proyecto para importar config
sys.path.insert(0, str(Path(__file__).parent.parent))
from app.sifen_client.config import SifenConfig


def load_latest_request(artifacts_dir: Path):
    """Carga el último request guardado."""
    # Buscar archivos REQ_* (nuevo formato con request_id)
    req_files = sorted(artifacts_dir.glob("recibe_lote_REQ_*.xml"), key=lambda p: p.stat().st_mtime, reverse=True)
    
    if not req_files:
        # Fallback a archivos antiguos
        req_files = sorted(artifacts_dir.glob("soap_last_request_SENT.xml"), key=lambda p: p.stat().st_mtime, reverse=True)
    
    if not req_files:
        raise FileNotFoundError("No se encontró ningún request guardado")
    
    req_file = req_files[0]
    
    # Buscar headers correspondientes
    headers_file = None
    if "REQ_" in req_file.name:
        req_id = req_file.name.split("REQ_")[1].split(".xml")[0]
        headers_file = artifacts_dir / f"recibe_lote_REQ_{req_id}_headers.json"
    
    if not headers_file or not headers_file.exists():
        # Fallback a headers antiguos
        headers_files = sorted(artifacts_dir.glob("soap_last_headers_SENT.json"), key=lambda p: p.stat().st_mtime, reverse=True)
        if headers_files:
            headers_file = headers_files[0]
        else:
            headers_file = None
    
    # Cargar contenido
    xml = req_file.read_text(encoding="utf-8")
    headers = {}
    if headers_file:
        headers = json.loads(headers_file.read_text(encoding="utf-8"))
    
    return xml, headers, req_file.name


def create_session(cert_path: str, cert_password: str, ca_bundle_path: str = None):
    """Crea una sesión mTLS con el certificado."""
    # Importar función de conversión desde el módulo correcto
    from tools.sifen_send_soap12_mtls_v2 import convert_p12_to_pem
    
    # Convertir P12 a PEM si es necesario
    if cert_path.lower().endswith('.p12') or cert_path.lower().endswith('.pfx'):
        cert_pem, key_pem = convert_p12_to_pem(cert_path, cert_password)
        cert = (cert_pem, key_pem)
    else:
        cert = cert_path
    
    session = requests.Session()
    session.cert = cert
    
    # Configurar CA bundle si se proporciona
    if ca_bundle_path:
        session.verify = ca_bundle_path
    else:
        # Usar el bundle por defecto del sistema
        session.verify = True
    
    return session


def main():
    parser = argparse.ArgumentParser(description="Re-envía un request anterior a SIFEN para debug")
    parser.add_argument("--env", choices=["test", "prod"], default="test", help="Ambiente SIFEN")
    parser.add_argument("--artifacts-dir", type=Path, default=Path("artifacts"), help="Directorio de artifacts")
    parser.add_argument("--request-file", type=Path, help="Archivo XML específico para re-enviar (opcional)")
    
    args = parser.parse_args()
    
    # Cargar configuración
    config = SifenConfig(env=args.env)
    
    # Verificar certificado
    if not config.cert_path or not config.cert_password:
        print("❌ Se requiere certificado (SIFEN_CERT_PATH y SIFEN_CERT_PASSWORD)")
        return 1
    
    # Cargar request
    if args.request_file:
        xml = args.request_file.read_text(encoding="utf-8")
        headers = {"Content-Type": "application/xml; charset=utf-8"}
        req_name = args.request_file.name
    else:
        xml, headers, req_name = load_latest_request(args.artifacts_dir)
    
    print(f"📤 Re-enviando request: {req_name}")
    endpoint = config.get_soap_service_url("recibe_lote").replace('.wsdl', '')
    print(f"📍 Endpoint: {endpoint}")
    print(f"📋 Headers: {json.dumps(headers, indent=2)}")
    print()
    
    # Crear sesión mTLS
    try:
        session = create_session(config.cert_path, config.cert_password, config.ca_bundle_path)
    except Exception as e:
        print(f"❌ Error al crear sesión mTLS: {e}")
        return 1
    
    # Enviar request
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    
    try:
        print("🚀 Enviando request...")
        resp = session.post(
            endpoint,
            data=xml.encode("utf-8"),
            headers=headers,
            timeout=(30, 60)
        )
        
        print(f"\n✅ Response recibido:")
        print(f"   Status Code: {resp.status_code}")
        print(f"   Headers: {dict(resp.headers)}")
        print(f"\n📄 Body:\n{resp.text}")
        
        # Guardar artifacts del replay
        replay_dir = args.artifacts_dir / "replay"
        replay_dir.mkdir(exist_ok=True)
        
        (replay_dir / f"replay_REQ_{timestamp}.xml").write_text(xml, encoding="utf-8")
        (replay_dir / f"replay_REQ_{timestamp}_headers.json").write_text(json.dumps(headers, indent=2), encoding="utf-8")
        (replay_dir / f"replay_RESP_{timestamp}.xml").write_text(resp.text, encoding="utf-8")
        
        meta = {
            "original_request": req_name,
            "endpoint": endpoint,
            "status_code": resp.status_code,
            "timestamp": timestamp,
            "headers": dict(resp.headers)
        }
        (replay_dir / f"replay_RESP_{timestamp}_meta.json").write_text(json.dumps(meta, indent=2), encoding="utf-8")
        
        print(f"\n💾 Replay guardado en: {replay_dir}/replay_*_{timestamp}.*")
        
        # Parsear respuesta SIFEN
        if "<dCodRes>" in resp.text:
            import lxml.etree as etree
            root = etree.fromstring(resp.text.encode("utf-8"))
            dCodRes = root.xpath("string(//*[local-name()='dCodRes'])")
            dMsgRes = root.xpath("string(//*[local-name()='dMsgRes'])")
            print(f"\n🔍 Respuesta SIFEN:")
            print(f"   dCodRes: {dCodRes}")
            print(f"   dMsgRes: {dMsgRes}")
        
        return 0
        
    except Exception as e:
        print(f"❌ Error al enviar request: {e}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
