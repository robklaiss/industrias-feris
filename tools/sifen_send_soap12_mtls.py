#!/usr/bin/env python3
"""
Sender SOAP 1.2 mTLS para SIFEN v150
Envía SOAP generado con curl y mTLS
NO re-parsea ni modifica el XML - envía bytes tal cual
"""

import sys
import os
import subprocess
import tempfile
import hashlib
import shutil
from pathlib import Path

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

def send_soap_with_curl(soap_path: Path, cert_pem: str, key_pem: str, debug: bool = False) -> subprocess.CompletedProcess:
    """Envía SOAP usando curl con mTLS (bytes raw, sin modificar)."""
    endpoint = "https://sifen-test.set.gov.py/de/ws/sync/recibe.wsdl"
    
    # Leer bytes tal cual (sin parsear ni modificar)
    soap_bytes = soap_path.read_bytes()
    
    if debug:
        # Calcular SHA256 de los bytes enviados
        sha256_hash = hashlib.sha256(soap_bytes).hexdigest()
        print(f"[DEBUG] SHA256 de bytes enviados: {sha256_hash}")
        print(f"[DEBUG] Tamaño: {len(soap_bytes)} bytes")
        
        # Guardar exactamente lo que se envía
        last_sent_path = Path("/tmp/last_sent_soap.xml")
        last_sent_path.write_bytes(soap_bytes)
        print(f"[DEBUG] SOAP enviado guardado en: {last_sent_path}")
    
    cmd = [
        'curl', '-v',
        '--request', 'POST',
        '--url', endpoint,
        '--header', 'Content-Type: application/soap+xml; charset=utf-8',
        '--header', 'SOAPAction: urn:rEnviDe',
        '--cert', cert_pem,
        '--key', key_pem,
        '--data-binary', f'@{soap_path}',
        '--output', '/tmp/sifen_rEnviDe_response.xml',
        '--write-out', '%{http_code}\n'
    ]
    
    print(f"📤 Enviando a: {endpoint}")
    print(f"🔐 Cert: {cert_pem}")
    print(f"🔑 Key: {key_pem}")
    
    return subprocess.run(cmd, capture_output=True, text=True)

def parse_response() -> dict:
    """Parsea respuesta SOAP de SIFEN."""
    response_path = Path("/tmp/sifen_rEnviDe_response.xml")
    if not response_path.exists():
        return {'dCodRes': 'ERROR', 'dMsgRes': 'No response file', 'dEstRes': 'N/A'}
    
    try:
        content = response_path.read_text(encoding='utf-8')
        
        # Buscar campos de respuesta (simple string search)
        result = {}
        
        if '<dCodRes>' in content:
            start = content.find('<dCodRes>') + 9
            end = content.find('</dCodRes>')
            result['dCodRes'] = content[start:end]
        else:
            result['dCodRes'] = 'N/A'
        
        if '<dMsgRes>' in content:
            start = content.find('<dMsgRes>') + 9
            end = content.find('</dMsgRes>')
            result['dMsgRes'] = content[start:end]
        else:
            result['dMsgRes'] = 'N/A'
        
        if '<dEstRes>' in content:
            start = content.find('<dEstRes>') + 9
            end = content.find('</dEstRes>')
            result['dEstRes'] = content[start:end]
        else:
            result['dEstRes'] = 'N/A'
        
        return result
        
    except Exception as e:
        return {'dCodRes': 'ERROR', 'dMsgRes': f'Error parsing response: {e}', 'dEstRes': 'N/A'}

def main():
    # Parsear argumentos
    debug = '--debug' in sys.argv
    args = [arg for arg in sys.argv[1:] if arg != '--debug']
    
    if len(args) < 1:
        print("USAGE: .venv/bin/python tools/sifen_send_soap12_mtls.py <soap_xml_path> [cert_path] [cert_pass] [--debug]")
        print("")
        print("Opciones:")
        print("  --debug    Muestra SHA256 de bytes enviados y guarda en /tmp/last_sent_soap.xml")
        sys.exit(1)
    
    soap_path = Path(args[0])
    if not soap_path.exists():
        print(f"❌ ERROR: No existe {soap_path}")
        sys.exit(1)
    
    # Certificado (argumentos o variables de entorno)
    cert_path = args[1] if len(args) > 1 else os.getenv('SIFEN_CERT_PATH')
    cert_pass = args[2] if len(args) > 2 else os.getenv('SIFEN_CERT_PASS')
    
    if not cert_path or not cert_pass:
        print("❌ ERROR: Especificar cert_path y cert_pass o setear SIFEN_CERT_PATH y SIFEN_CERT_PASS")
        sys.exit(1)
    
    if not Path(cert_path).exists():
        print(f"❌ ERROR: No existe el certificado {cert_path}")
        sys.exit(1)
    
    print("=== SENDER SOAP 1.2 mTLS SIFEN v150 ===")
    print(f"📂 SOAP: {soap_path}")
    print(f"🔐 Cert: {cert_path}")
    if debug:
        print("🐛 Modo DEBUG activado")
    
    cert_pem_path = key_pem_path = None
    try:
        # Convertir P12 a PEM
        print("🔐 Convirtiendo certificado P12 a PEM...")
        cert_pem_path, key_pem_path = convert_p12_to_pem(cert_path, cert_pass)
        
        # Enviar SOAP (bytes raw, sin modificar)
        print("📤 Enviando SOAP a SIFEN (bytes raw, sin re-parsear)...")
        result = send_soap_with_curl(soap_path, cert_pem_path, key_pem_path, debug=debug)
        
        # Parsear status
        status_code = result.stdout.strip()
        print(f"📊 HTTP Status: {status_code}")
        
        if result.stderr:
            print(f"📋 Curl stderr:")
            for line in result.stderr.strip().split('\n')[-5:]:
                print(f"   {line}")
        
        # Parsear respuesta
        print("\n🔍 Parseando respuesta SIFEN...")
        response_data = parse_response()
        
        print(f"\n📋 Respuesta SIFEN:")
        print(f"   dCodRes: {response_data['dCodRes']}")
        print(f"   dMsgRes: {response_data['dMsgRes']}")
        print(f"   dEstRes: {response_data['dEstRes']}")
        
        # Guardar respuesta cruda
        response_path = Path("/tmp/sifen_rEnviDe_response.xml")
        if response_path.exists():
            print(f"\n💾 Respuesta guardada: {response_path}")
            
            # Mostrar preview
            content = response_path.read_text(encoding='utf-8')
            lines = content.split('\n')
            print("\n📋 Response preview:")
            print("="*60)
            for i, line in enumerate(lines[:15]):
                print(f"{i+1:2d}: {line}")
            if len(lines) > 15:
                print("...")
            print("="*60)
        
        # Evaluar resultado
        print(f"\n🎯 EVALUACIÓN:")
        
        if response_data['dCodRes'] == 'ERROR':
            print("❌ ERROR en respuesta")
            sys.exit(1)
        elif 'no tiene firma' in response_data['dMsgRes'].lower():
            print("❌ ERROR: SIFEN sigue reportando 'no tiene firma'")
            print("   Revisar perfil de firma y estructura del XML")
            sys.exit(1)
        elif response_data['dEstRes'] in ['A', 'Aprobado']:
            print("✅ ACEPTADO por SIFEN")
            sys.exit(0)
        else:
            print(f"⚠️  Estado: {response_data['dEstRes']}")
            print("   Firma reconocida, pero hay otros errores (negocio/campos)")
            sys.exit(0)  # Éxito parcial - firma OK
        
    except Exception as e:
        print(f"❌ ERROR: {e}")
        sys.exit(1)
    finally:
        # Limpiar archivos temporales
        if cert_pem_path:
            os.unlink(cert_pem_path)
        if key_pem_path:
            os.unlink(key_pem_path)

if __name__ == "__main__":
    main()
