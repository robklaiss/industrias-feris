#!/usr/bin/env python3
"""
Envío RAW de SOAP a SIFEN sin Zeep - usa el SOAP exacto guardado en artifacts
"""
import sys
import os
import requests
import tempfile
from pathlib import Path
from cryptography.hazmat.primitives.serialization import pkcs12, Encoding, PrivateFormat, NoEncryption

def p12_to_pem_temp(p12_path: str, password: str):
    """Convierte P12 a archivos PEM temporales"""
    with open(p12_path, 'rb') as f:
        p12_data = f.read()
    
    private_key, certificate, _ = pkcs12.load_key_and_certificates(
        p12_data, 
        password.encode('utf-8')
    )
    
    cert_pem = certificate.public_bytes(Encoding.PEM)
    key_pem = private_key.private_bytes(
        Encoding.PEM,
        PrivateFormat.TraditionalOpenSSL,
        NoEncryption()
    )
    
    cert_file = tempfile.NamedTemporaryFile(mode='wb', suffix='.pem', delete=False)
    key_file = tempfile.NamedTemporaryFile(mode='wb', suffix='.pem', delete=False)
    
    cert_file.write(cert_pem)
    cert_file.close()
    key_file.write(key_pem)
    key_file.close()
    
    return cert_file.name, key_file.name

def send_raw_soap(soap_file: str, p12_path: str, p12_pass: str, endpoint: str):
    """Envía SOAP raw usando requests con mTLS desde P12"""
    soap_path = Path(soap_file)
    if not soap_path.exists():
        print(f"ERROR: SOAP file not found: {soap_file}")
        return None
    
    soap_xml = soap_path.read_text(encoding='utf-8')
    headers = {
        'Content-Type': 'application/soap+xml; charset=utf-8; action="http://ekuatia.set.gov.py/sifen/xsd/siRecepLoteDE"',
        'Accept': 'application/xml, text/xml, */*',
        'Connection': 'close'
    }
    
    print(f"📤 Enviando SOAP raw (sin Zeep) a: {endpoint}")
    print(f"   SOAP file: {soap_file}")
    print(f"   SOAP size: {len(soap_xml)} bytes")
    
    cert_pem, key_pem = p12_to_pem_temp(p12_path, p12_pass)
    
    try:
        response = requests.post(
            endpoint,
            data=soap_xml.encode('utf-8'),
            headers=headers,
            cert=(cert_pem, key_pem),
            verify=True,
            timeout=30
        )
        
        print(f"\n✅ Response received:")
        print(f"   Status: {response.status_code}")
        print(f"\n📄 Response body:")
        print(response.text)
        
        if 'dCodRes' in response.text:
            import re
            cod_match = re.search(r'<.*?dCodRes>(\d+)</.*?dCodRes>', response.text)
            msg_match = re.search(r'<.*?dMsgRes>([^<]+)</.*?dMsgRes>', response.text)
            if cod_match:
                print(f"\n🔍 dCodRes: {cod_match.group(1)}")
            if msg_match:
                print(f"🔍 dMsgRes: {msg_match.group(1)}")
        
        return response
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()
        return None
    finally:
        try:
            os.unlink(cert_pem)
            os.unlink(key_pem)
        except:
            pass

def main():
    env_file = Path('.env')
    if env_file.exists():
        for line in env_file.read_text().splitlines():
            line = line.strip()
            if line and not line.startswith('#') and '=' in line:
                key, value = line.split('=', 1)
                os.environ[key] = value
    
    p12_path = os.getenv('SIFEN_P12_PATH')
    p12_pass = os.getenv('SIFEN_P12_PASS')
    
    if not p12_path or not p12_pass:
        print("❌ Error: SIFEN_P12_PATH y SIFEN_P12_PASS deben estar en .env")
        sys.exit(1)
    
    if not Path(p12_path).exists():
        print(f"❌ Error: P12 not found: {p12_path}")
        sys.exit(1)
    
    soap_file = "artifacts/soap_last_request_SENT.xml"
    endpoint = "https://sifen-test.set.gov.py/de/ws/async/recibe-lote"
    
    if len(sys.argv) > 1:
        soap_file = sys.argv[1]
    if len(sys.argv) > 2:
        endpoint = sys.argv[2]
    
    send_raw_soap(soap_file, p12_path, p12_pass, endpoint)

if __name__ == "__main__":
    main()
