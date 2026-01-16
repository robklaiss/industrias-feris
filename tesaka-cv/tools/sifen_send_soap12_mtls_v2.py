#!/usr/bin/env python3
"""
Sender SOAP 1.2 mTLS v2 - Envia SOAP a SIFEN con firma corregida
"""

import sys
import os
import tempfile
import subprocess
from pathlib import Path
from lxml import etree
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.ssl_ import create_urllib3_context

def convert_p12_to_pem(p12_path: str, p12_password: str) -> tuple[str, str]:
    """Convierte certificado P12 a archivos PEM temporales."""
    cert_fd, cert_path = tempfile.mkstemp(suffix='.pem')
    key_fd, key_path = tempfile.mkstemp(suffix='.pem')
    
    try:
        # Extraer certificado
        subprocess.run([
            'openssl', 'pkcs12', '-in', p12_path,
            '-passin', f'pass:{p12_password}',
            '-clcerts', '-nokeys', '-out', cert_path
        ], check=True, capture_output=True)
        
        # Extraer clave privada
        subprocess.run([
            'openssl', 'pkcs12', '-in', p12_path,
            '-passin', f'pass:{p12_password}',
            '-nocerts', '-nodes', '-out', key_path
        ], check=True, capture_output=True)
        
        return cert_path, key_path
    except subprocess.CalledProcessError as e:
        os.close(cert_fd)
        os.close(key_fd)
        os.unlink(cert_path)
        os.unlink(key_path)
        raise RuntimeError(f"Error convirtiendo P12 a PEM: {e.stderr.decode()}") from e

class TLSAdapter(HTTPAdapter):
    """Adapter para configurar TLS específico para mTLS."""
    
    def __init__(self, cert_file: str, key_file: str):
        self.cert_file = cert_file
        self.key_file = key_file
        super().__init__()
    
    def init_poolmanager(self, *args, **kwargs):
        context = create_urllib3_context()
        context.load_cert_chain(certfile=self.cert_file, keyfile=self.key_file)
        kwargs['ssl_context'] = context
        return super().init_poolmanager(*args, **kwargs)

def parse_soap_response(response_bytes: bytes) -> dict:
    """Parsea respuesta SOAP (bytes) y extrae campos de respuesta."""
    try:
        root = etree.fromstring(
            response_bytes,
            parser=etree.XMLParser(recover=True, resolve_entities=False)
        )
        
        # Buscar respuesta en namespace SIFEN
        ns = {'sif': 'http://ekuatia.set.gov.py/sifen/xsd'}
        
        # Intentar encontrar rEnviDeRes
        res = root.xpath('//sif:rEnviDeRes', namespaces=ns)
        if res:
            elem = res[0]
            return {
                'dCodRes': elem.findtext('sif:dCodRes', namespaces=ns),
                'dMsgRes': elem.findtext('sif:dMsgRes', namespaces=ns),
                'dEstRes': elem.findtext('sif:dEstRes', namespaces=ns),
                'dFecProc': elem.findtext('sif:dFecProc', namespaces=ns),
            }
        
        # Si no encuentra, buscar en cualquier parte
        return {
            'dCodRes': root.xpath('//*[local-name()="dCodRes"]/text()')[0] if root.xpath('//*[local-name()="dCodRes"]/text()') else 'N/A',
            'dMsgRes': root.xpath('//*[local-name()="dMsgRes"]/text()')[0] if root.xpath('//*[local-name()="dMsgRes"]/text()') else 'N/A',
            'dEstRes': root.xpath('//*[local-name()="dEstRes"]/text()')[0] if root.xpath('//*[local-name()="dEstRes"]/text()') else 'N/A',
            'dFecProc': root.xpath('//*[local-name()="dFecProc"]/text()')[0] if root.xpath('//*[local-name()="dFecProc"]/text()') else 'N/A',
        }
    except Exception as e:
        return {'dCodRes': 'ERROR', 'dMsgRes': f'Error parseando respuesta: {e}', 'dEstRes': 'N/A', 'dFecProc': 'N/A'}

def main():
    if len(sys.argv) < 2:
        print("USAGE: .venv/bin/python tools/sifen_send_soap12_mtls_v2.py <soap_xml_path> [cert_path] [cert_pass]")
        sys.exit(1)
    
    soap_path = Path(sys.argv[1])
    if not soap_path.exists():
        print(f"❌ ERROR: No existe {soap_path}")
        sys.exit(1)
    
    # Certificado (argumentos o variables de entorno)
    cert_path = sys.argv[2] if len(sys.argv) > 2 else os.getenv('SIFEN_CERT_PATH')
    cert_pass = sys.argv[3] if len(sys.argv) > 3 else os.getenv('SIFEN_CERT_PASS')
    
    if not cert_path or not cert_pass:
        print("❌ ERROR: Especificar cert_path y cert_pass o setear SIFEN_CERT_PATH y SIFEN_CERT_PASS")
        sys.exit(1)
    
    if not Path(cert_path).exists():
        print(f"❌ ERROR: No existe el certificado {cert_path}")
        sys.exit(1)
    
    print("=== ENVIADOR SOAP 1.2 mTLS v2 ===")
    print(f"📂 SOAP: {soap_path}")
    print(f"🔐 Cert: {cert_path}")
    
    cert_pem_path = key_pem_path = None
    try:
        # Leer SOAP
        soap_content = soap_path.read_text(encoding='utf-8')
        print("✅ SOAP leído")
        
        # Convertir P12 a PEM
        print("🔐 Convirtiendo certificado P12 a PEM...")
        cert_pem_path, key_pem_path = convert_p12_to_pem(cert_path, cert_pass)
        
        # Enviar petición
        endpoint = "https://sifen-test.set.gov.py/de/ws/sync/recibe.wsdl"
        print(f"📤 Enviando a {endpoint}...")
        
        headers = {
            'Content-Type': 'application/soap+xml; charset=utf-8',
            'SOAPAction': 'urn:rEnviDe'
        }
        
        session = requests.Session()
        session.mount('https://', TLSAdapter(cert_pem_path, key_pem_path))
        
        response = session.post(
            endpoint,
            data=soap_content.encode('utf-8'),
            headers=headers,
            timeout=30
        )
        
        print(f"📊 Status: {response.status_code}")
        
        if response.status_code == 200:
            print("✅ Petición enviada exitosamente")
            
            # Guardar respuesta
            response_path = Path("/tmp/sifen_rEnviDe_response.xml")
            response_path.write_bytes(response.content)
            print(f"💾 Respuesta guardada en: {response_path}")
            
            # Parsear respuesta
            result = parse_soap_response(response.content)
            print(f"\n📋 Respuesta SIFEN:")
            print(f"   dCodRes: {result['dCodRes']}")
            print(f"   dMsgRes: {result['dMsgRes']}")
            print(f"   dEstRes: {result['dEstRes']}")
            print(f"   dFecProc: {result['dFecProc']}")
            
            # Exit code según estado
            if result['dEstRes'] in ['A', 'Aprobado']:
                print("✅ ACEPTADO por SIFEN")
                sys.exit(0)
            elif result['dCodRes'] == 'ERROR':
                print("❌ ERROR en respuesta")
                sys.exit(1)
            else:
                print(f"⚠️  Estado: {result['dEstRes']}")
                sys.exit(1)
        else:
            print(f"❌ Error HTTP {response.status_code}")
            preview = response.content.decode("utf-8", errors="replace")[:500]
            print(f"Response: {preview}...")
            sys.exit(1)
        
    except Exception as e:
        print(f"❌ Error: {e}")
        sys.exit(1)
    finally:
        # Limpiar archivos temporales
        if cert_pem_path:
            os.unlink(cert_pem_path)
        if key_pem_path:
            os.unlink(key_pem_path)

if __name__ == "__main__":
    main()
