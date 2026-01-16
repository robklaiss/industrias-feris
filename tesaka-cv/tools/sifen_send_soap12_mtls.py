#!/usr/bin/env python3
"""
Script para enviar XML SIFEN v150 via SOAP 1.2 con mTLS.

Este script construye un envelope SOAP 1.2 para la operación rEnviDe
de SIFEN, enviando el rDE completo (no base64) con autenticación mTLS.

Uso:
    python tools/sifen_send_soap12_mtls.py <xml_firmado>
"""

import sys
import os
import argparse
import tempfile
import subprocess
from pathlib import Path
from lxml import etree
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.ssl_ import create_urllib3_context

# Importar normalizador de firma
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "tools"))
try:
    from sifen_normalize_signature_placement import normalize_signature_under_rde
except ImportError:
    print("WARNING: No se pudo importar normalize_signature_under_rde - la normalización será omitida")
    normalize_signature_under_rde = None

def convert_p12_to_pem(p12_path: str, p12_password: str) -> tuple[str, str]:
    """
    Convierte certificado P12 a archivos PEM temporales.
    
    Returns:
        Tuple (cert_pem_path, key_pem_path)
    """
    # Crear archivos temporales
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

def build_soap_envelope(rde_element: etree._Element, d_id: int) -> etree._Element:
    """
    Construye envelope SOAP 1.2 para operación rEnviDe con rDE como nodo XML real.
    
    Args:
        rde_element: Elemento etree del rDE (con firma normalizada)
        d_id: ID entero (<= 15 dígitos)
    
    Returns:
        Elemento etree del envelope SOAP completo
    """
    # Namespaces
    SOAP12_NS = "http://www.w3.org/2003/05/soap-envelope"
    SIFEN_NS = "http://ekuatia.set.gov.py/sifen/xsd"
    
    # Crear envelope
    envelope = etree.Element(etree.QName(SOAP12_NS, "Envelope"))
    etree.SubElement(envelope, etree.QName(SOAP12_NS, "Header"))
    
    # Body con rEnviDe
    body = etree.SubElement(envelope, etree.QName(SOAP12_NS, "Body"))
    r_envi_de = etree.SubElement(body, etree.QName(SIFEN_NS, "rEnviDe"))
    
    # dId
    d_id_elem = etree.SubElement(r_envi_de, etree.QName(SIFEN_NS, "dId"))
    d_id_elem.text = str(d_id)
    
    # xDE conteniendo rDE como nodo XML real (no CDATA)
    xde_elem = etree.SubElement(r_envi_de, etree.QName(SIFEN_NS, "xDE"))
    xde_elem.append(rde_element)
    
    return envelope

def parse_soap_response(response_text: str) -> dict:
    """
    Parsea respuesta SOAP y extrae dCodRes y dMsgRes.
    
    Returns:
        Dict con {dCodRes, dMsgRes}
    """
    try:
        root = etree.fromstring(response_text)
        
        # Buscar respuesta en namespace SIFEN
        ns = {'sif': 'http://ekuatia.set.gov.py/sifen/xsd'}
        
        # Intentar encontrar rEnviDeRes
        res = root.xpath('//sif:rEnviDeRes', namespaces=ns)
        if res:
            elem = res[0]
            cod_res = elem.findtext('sif:dCodRes', namespaces=ns)
            msg_res = elem.findtext('sif:dMsgRes', namespaces=ns)
            return {'dCodRes': cod_res, 'dMsgRes': msg_res}
        
        # Si no encuentra, buscar en cualquier parte
        cod_res = root.xpath('//*[local-name()="dCodRes"]/text()')
        msg_res = root.xpath('//*[local-name()="dMsgRes"]/text()')
        
        return {
            'dCodRes': cod_res[0] if cod_res else 'N/A',
            'dMsgRes': msg_res[0] if msg_res else 'N/A'
        }
    except Exception as e:
        return {'dCodRes': 'ERROR', 'dMsgRes': f'Error parseando respuesta: {e}'}

def main():
    parser = argparse.ArgumentParser(
        description="Enviar XML SIFEN v150 via SOAP 1.2 con mTLS"
    )
    parser.add_argument(
        "xml_path",
        type=Path,
        help="Path al XML firmado a enviar"
    )
    parser.add_argument(
        "--endpoint",
        default="https://sifen-test.set.gov.py/de/ws/sync/recibe.wsdl",
        help="Endpoint SOAP (default: SIFEN test)"
    )
    parser.add_argument(
        "--d-id",
        type=int,
        default=1,
        help="ID entero para dId (default: 1)"
    )
    parser.add_argument(
        "--cert-path",
        default=os.getenv('SIFEN_CERT_PATH'),
        help="Path al certificado P12 (default: $SIFEN_CERT_PATH)"
    )
    parser.add_argument(
        "--cert-pass",
        default=os.getenv('SIFEN_CERT_PASS'),
        help="Password del certificado (default: $SIFEN_CERT_PASS)"
    )
    parser.add_argument(
        "--timeout",
        type=int,
        default=30,
        help="Timeout en segundos (default: 30)"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Generar SOAP y guardarlo en archivo sin enviar"
    )
    
    args = parser.parse_args()
    
    # Validar argumentos
    if not args.dry_run:
        if not args.cert_path:
            print("❌ Error: Especificar --cert-path o setear SIFEN_CERT_PATH")
            sys.exit(1)
        
        if not args.cert_pass:
            print("❌ Error: Especificar --cert-pass o setear SIFEN_CERT_PASS")
            sys.exit(1)
        
        if not Path(args.cert_path).exists():
            print(f"❌ Error: No existe el certificado {args.cert_path}")
            sys.exit(1)
    
    if args.d_id > 999999999999999:
        print("❌ Error: dId debe ser <= 15 dígitos")
        sys.exit(1)
    
    cert_pem_path = key_pem_path = None
    try:
        print("=== Enviador SOAP 1.2 SIFEN ===")
        print(f"📂 XML: {args.xml_path}")
        if not args.dry_run:
            print(f"🌐 Endpoint: {args.endpoint}")
            print(f"🔐 Cert: {args.cert_path}")
        print(f"📋 dId: {args.d_id}")
        
        # Cargar XML y normalizar firma
        if not args.xml_path.exists():
            print(f"❌ Error: No existe {args.xml_path}")
            sys.exit(1)
        
        xml_bytes = args.xml_path.read_bytes()
        
        # Normalizar posición de la firma si está disponible el helper
        if normalize_signature_under_rde:
            try:
                xml_bytes = normalize_signature_under_rde(xml_bytes)
                print("✅ Firma normalizada: Signature movida a rDE")
            except Exception as e:
                print(f"⚠️  Warning: No se pudo normalizar la firma: {e}")
        
        # Parsear rDE como elemento etree
        rde_element = etree.fromstring(xml_bytes)
        
        # Construir envelope SOAP con rDE como nodo real
        print("📦 Construyendo envelope SOAP 1.2...")
        soap_envelope_element = build_soap_envelope(rde_element, args.d_id)
        
        # Serializar envelope a bytes
        soap_envelope_bytes = etree.tostring(
            soap_envelope_element, 
            encoding='UTF-8', 
            xml_declaration=True,
            pretty_print=False
        )
        soap_envelope = soap_envelope_bytes.decode('utf-8')
        
        # Si es dry-run, guardar y salir
        if args.dry_run:
            soap_path = args.xml_path.parent / f"{args.xml_path.stem}_soap_generated.xml"
            soap_path.write_text(soap_envelope, encoding='utf-8')
            print(f"💾 SOAP guardado en: {soap_path}")
            print("🔍 Verificando estructura del SOAP...")
            
            # Verificar estructura
            from lxml import etree as verify_etree
            soap_root = verify_etree.fromstring(soap_envelope.encode('utf-8'))
            ns = {"ds": "http://www.w3.org/2000/09/xmldsig#", "s": "http://ekuatia.set.gov.py/sifen/xsd"}
            
            sigs = soap_root.xpath("//ds:Signature", namespaces=ns)
            if sigs:
                parent = sigs[0].getparent()
                parent_name = verify_etree.QName(parent).localname
                print(f"   ✅ Signature parent: {parent_name}")
                
                rde = soap_root.xpath("//s:rDE", namespaces=ns)
                if rde:
                    kids = [verify_etree.QName(k).localname for k in rde[0]]
                    print(f"   ✅ rDE children: {kids}")
                    print(f"   ✅ Estructura correcta: {kids == ['dVerFor', 'DE', 'Signature']}")
                else:
                    print("   ❌ No se encontró rDE en SOAP")
            else:
                print("   ❌ No se encontró Signature en SOAP")
            
            return
        
        # Convertir P12 a PEM
        print("🔐 Convirtiendo certificado P12 a PEM...")
        cert_pem_path, key_pem_path = convert_p12_to_pem(args.cert_path, args.cert_pass)
        
        # Enviar petición
        print(f"📤 Enviando a {args.endpoint}...")
        headers = {
            'Content-Type': 'application/soap+xml; charset=utf-8',
            'SOAPAction': 'urn:rEnviDe'
        }
        
        session = requests.Session()
        session.mount('https://', TLSAdapter(cert_pem_path, key_pem_path))
        
        response = session.post(
            args.endpoint,
            data=soap_envelope.encode('utf-8'),
            headers=headers,
            timeout=args.timeout
        )
        
        print(f"📊 Status: {response.status_code}")
        print(f"📊 Headers: {dict(response.headers)}")
        
        if response.status_code == 200:
            print("✅ Petición enviada exitosamente")
            
            # Parsear respuesta
            result = parse_soap_response(response.text)
            print(f"\n📋 Respuesta SIFEN:")
            print(f"   dCodRes: {result['dCodRes']}")
            print(f"   dMsgRes: {result['dMsgRes']}")
            
            # Guardar respuesta para debug
            response_path = args.xml_path.parent / f"{args.xml_path.stem}_soap_response.xml"
            response_path.write_text(response.text, encoding='utf-8')
            print(f"\n💾 Respuesta guardada en: {response_path}")
            
        else:
            print(f"❌ Error HTTP {response.status_code}")
            print(f"Response: {response.text[:500]}...")
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
