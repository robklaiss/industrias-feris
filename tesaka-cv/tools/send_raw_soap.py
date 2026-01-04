#!/usr/bin/env python3
"""
Envía un SOAP request desde artifacts/soap_last_request.xml vía requests con mTLS.

Uso:
    python -m tools.send_raw_soap [--request-xml PATH] [--output RESPONSE_XML_PATH]
"""
import sys
import os
from pathlib import Path
from urllib.parse import urlparse

# Agregar parent al path para imports
sys.path.insert(0, str(Path(__file__).parent.parent))

try:
    import requests
except ImportError:
    print("ERROR: requests no está instalado. Instalar con: pip install requests", file=sys.stderr)
    sys.exit(1)

from app.sifen_client.config import get_sifen_config, get_mtls_cert_path_and_password
from app.sifen_client.pkcs12_utils import p12_to_temp_pem_files, cleanup_pem_files


def main():
    import argparse
    
    parser = argparse.ArgumentParser(description="Envía SOAP request raw desde XML")
    parser.add_argument("--request-xml", type=Path, default=Path("artifacts/soap_last_request.xml"), help="Path al XML SOAP request")
    parser.add_argument("--url", help="URL de POST (si no se especifica, se extrae del XML o usa default)")
    parser.add_argument("--env", choices=["test", "prod"], default="test", help="Ambiente (test/prod)")
    parser.add_argument("--output", type=Path, help="Path donde guardar la respuesta (opcional)")
    
    args = parser.parse_args()
    
    # Leer request XML
    if not args.request_xml.exists():
        print(f"ERROR: No existe el archivo: {args.request_xml}", file=sys.stderr)
        sys.exit(1)
    
    soap_xml = args.request_xml.read_text(encoding="utf-8")
    soap_bytes = soap_xml.encode("utf-8")
    
    # Obtener URL
    if args.url:
        post_url = args.url
    else:
        # Intentar extraer del XML o usar default según env
        config = get_sifen_config(env=args.env)
        post_url = config.get_soap_service_url("recibe_lote").replace(".wsdl", "").replace("?wsdl", "")
        print(f"⚠️  Usando URL por defecto: {post_url}")
        print(f"   (Usa --url para especificar explícitamente)")
    
    # Configurar mTLS
    cert_path, cert_password = get_mtls_cert_path_and_password()
    
    if not cert_path:
        print("ERROR: No se encontró certificado mTLS. Configurar SIFEN_MTLS_P12_PATH o SIFEN_CERT_PATH", file=sys.stderr)
        sys.exit(1)
    
    # Convertir P12 a PEM temporales si es necesario
    temp_pem_files = None
    if cert_path.endswith((".p12", ".pfx")):
        try:
            cert_pem_path, key_pem_path = p12_to_temp_pem_files(cert_path, cert_password)
            temp_pem_files = (cert_pem_path, key_pem_path)
            session_cert = (cert_pem_path, key_pem_path)
            print(f"✓ Certificado P12 convertido a PEM temporales")
        except Exception as e:
            print(f"ERROR al convertir P12 a PEM: {e}", file=sys.stderr)
            sys.exit(1)
    else:
        # Asumir que ya es PEM
        key_path = cert_path.replace(".pem", ".key").replace(".crt", ".key")
        if not Path(key_path).exists():
            print(f"ERROR: No se encontró archivo key correspondiente: {key_path}", file=sys.stderr)
            sys.exit(1)
        session_cert = (cert_path, key_path)
    
    # Extraer headers del XML (Content-Type, SOAPAction)
    headers = {
        "Content-Type": "application/soap+xml; charset=utf-8",
        "Accept": "application/soap+xml, text/xml, */*",
    }
    
    # Intentar detectar Content-Type desde comentarios en el XML o usar default
    if 'Content-Type' in soap_xml:
        # Si hay algún comentario o indicación, usar eso (simplificado)
        pass  # Por ahora usar default
    
    print(f"📤 Enviando SOAP request a: {post_url}")
    print(f"   Request size: {len(soap_bytes)} bytes")
    
    try:
        # Crear sesión con mTLS
        session = requests.Session()
        session.cert = session_cert
        session.verify = True
        
        # POST
        resp = session.post(
            post_url,
            data=soap_bytes,
            headers=headers,
            timeout=(30, 60),
        )
        
        print(f"\n📥 Respuesta:")
        print(f"   Status: {resp.status_code}")
        print(f"   Headers: {dict(resp.headers)}")
        print(f"   Body size: {len(resp.content)} bytes")
        
        # Guardar respuesta si se especificó output
        if args.output:
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_bytes(resp.content)
            print(f"\n✓ Respuesta guardada en: {args.output}")
        
        # Imprimir primeros 500 caracteres de la respuesta
        resp_text = resp.content.decode("utf-8", errors="replace")
        print(f"\n📄 Preview respuesta (primeros 500 chars):")
        print("-" * 60)
        print(resp_text[:500])
        print("-" * 60)
        
        return 0
        
    except Exception as e:
        print(f"\n❌ Error al enviar: {e}", file=sys.stderr)
        import traceback
        traceback.print_exc()
        return 1
    finally:
        # Limpiar PEM temporales si se crearon
        if temp_pem_files:
            cleanup_pem_files(temp_pem_files[0], temp_pem_files[1])


if __name__ == "__main__":
    sys.exit(main())

