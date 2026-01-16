#!/usr/bin/env python3
"""
Script para enviar DE firmado a SIFEN TEST con autenticación por certificado

IMPORTANTE: SIFEN requiere autenticación mutua (mTLS) con certificado cliente

Uso:
    python tools/enviar_de_sifen_con_certificado.py <archivo_xml_firmado>
    
Ejemplo:
    export SIFEN_CERT_PATH="/Users/robinklaiss/.sifen/certs/F1T_65478.p12"
    export SIFEN_CERT_PASS="bH1%T7EP"
    python tools/enviar_de_sifen_con_certificado.py ~/Desktop/sifen_de_firmado_test.xml
"""

import sys
import os
from pathlib import Path
import tempfile

# Agregar el directorio raíz al path
sys.path.insert(0, str(Path(__file__).parent.parent))

import requests
from lxml import etree


def convertir_p12_a_pem(p12_path: str, password: str):
    """
    Convierte P12 a PEM para usar con requests
    
    Returns:
        tuple: (cert_pem_path, key_pem_path)
    """
    from cryptography.hazmat.primitives.serialization import pkcs12, Encoding, PrivateFormat, NoEncryption
    from cryptography.hazmat.backends import default_backend
    
    # Leer P12
    with open(p12_path, 'rb') as f:
        p12_data = f.read()
    
    # Cargar P12
    private_key, certificate, ca_certs = pkcs12.load_key_and_certificates(
        p12_data,
        password.encode('utf-8'),
        backend=default_backend()
    )
    
    # Crear archivos temporales
    cert_file = tempfile.NamedTemporaryFile(mode='wb', delete=False, suffix='.pem')
    key_file = tempfile.NamedTemporaryFile(mode='wb', delete=False, suffix='.pem')
    
    # Escribir certificado
    cert_pem = certificate.public_bytes(Encoding.PEM)
    cert_file.write(cert_pem)
    
    # Si hay certificados adicionales (CA), agregarlos
    if ca_certs:
        for ca_cert in ca_certs:
            ca_pem = ca_cert.public_bytes(Encoding.PEM)
            cert_file.write(ca_pem)
    
    cert_file.close()
    
    # Escribir clave privada
    key_pem = private_key.private_bytes(
        encoding=Encoding.PEM,
        format=PrivateFormat.TraditionalOpenSSL,
        encryption_algorithm=NoEncryption()
    )
    key_file.write(key_pem)
    key_file.close()
    
    return cert_file.name, key_file.name


def enviar_de_con_certificado(xml_path: str, cert_path: str, cert_pass: str, csc: str = "ABCD0000000000000000000000000000"):
    """
    Envía un DE firmado a SIFEN TEST usando autenticación por certificado
    
    Args:
        xml_path: Ruta al archivo XML firmado
        cert_path: Ruta al certificado P12
        cert_pass: Contraseña del certificado
        csc: Código de Seguridad del Contribuyente
    """
    # Leer XML
    with open(xml_path, 'rb') as f:
        xml_content = f.read()
    
    # Parsear para obtener CDC
    root = etree.fromstring(xml_content)
    ns = {'sifen': 'http://ekuatia.set.gov.py/sifen/xsd'}
    
    de_elements = root.xpath('//sifen:DE', namespaces=ns)
    if not de_elements:
        de_elements = root.xpath('//DE')
    
    if not de_elements:
        print("❌ Error: No se encontró elemento DE en el XML")
        return False
    
    cdc = de_elements[0].get('Id')
    if not cdc:
        print("❌ Error: Elemento DE no tiene atributo Id (CDC)")
        return False
    
    print(f"CDC: {cdc}")
    print(f"Longitud CDC: {len(cdc)} dígitos")
    print()
    
    # Convertir P12 a PEM para requests
    print("Convirtiendo certificado P12 a PEM...")
    try:
        cert_pem_path, key_pem_path = convertir_p12_a_pem(cert_path, cert_pass)
        print(f"✓ Certificado: {cert_pem_path}")
        print(f"✓ Clave: {key_pem_path}")
        print()
    except Exception as e:
        print(f"❌ Error al convertir certificado: {e}")
        return False
    
    # Endpoint SOAP de SIFEN TEST (sin .wsdl)
    url = "https://sifen-test.set.gov.py/de/ws/sync/recibe"
    
    # Codificar XML en base64
    import base64
    xml_base64 = base64.b64encode(xml_content).decode('utf-8')
    
    # Crear SOAP Envelope
    soap_envelope = f"""<?xml version="1.0" encoding="UTF-8"?>
<env:Envelope xmlns:env="http://www.w3.org/2003/05/soap-envelope">
   <env:Header/>
   <env:Body>
      <ns2:rEnviDe xmlns:ns2="http://ekuatia.set.gov.py/sifen/xsd">
         <ns2:dId>202601130749047</ns2:dId>
         <ns2:xDE>{xml_base64}</ns2:xDE>
         <ns2:dCSC>{csc}</ns2:dCSC>
      </ns2:rEnviDe>
   </env:Body>
</env:Envelope>"""
    
    headers = {
        'Content-Type': 'application/soap+xml; charset=utf-8',
        'SOAPAction': ''
    }
    
    print("="*70)
    print("ENVIANDO A SIFEN TEST CON CERTIFICADO")
    print("="*70)
    print(f"URL: {url}")
    print(f"CDC: {cdc}")
    print(f"CSC: {csc}")
    print(f"Certificado: {cert_path}")
    print()
    
    try:
        # Enviar con certificado cliente (mTLS)
        response = requests.post(
            url,
            data=soap_envelope,
            headers=headers,
            cert=(cert_pem_path, key_pem_path),  # Autenticación mutua
            timeout=30,
            verify=True  # Verificar certificado del servidor
        )
        
        print(f"Status Code: {response.status_code}")
        print()
        
        if response.status_code == 200:
            print("✅ RESPUESTA RECIBIDA")
            print()
            print("Respuesta SOAP:")
            print(response.text)
            
            # Limpiar archivos temporales
            os.unlink(cert_pem_path)
            os.unlink(key_pem_path)
            
            return True
                
        else:
            print("❌ ERROR EN ENVÍO")
            print()
            print(f"Respuesta:")
            print(response.text)
            
            # Limpiar archivos temporales
            os.unlink(cert_pem_path)
            os.unlink(key_pem_path)
            
            return False
            
    except requests.exceptions.SSLError as e:
        print(f"❌ ERROR SSL: {e}")
        print()
        print("Posibles causas:")
        print("  - Certificado cliente inválido o expirado")
        print("  - Certificado no autorizado por SIFEN")
        print("  - Problema con la cadena de certificados")
        
        # Limpiar archivos temporales
        try:
            os.unlink(cert_pem_path)
            os.unlink(key_pem_path)
        except:
            pass
        
        return False
        
    except requests.exceptions.Timeout:
        print("❌ ERROR: Timeout al conectar con SIFEN")
        
        # Limpiar archivos temporales
        try:
            os.unlink(cert_pem_path)
            os.unlink(key_pem_path)
        except:
            pass
        
        return False
        
    except requests.exceptions.ConnectionError as e:
        print(f"❌ ERROR: No se pudo conectar con SIFEN: {e}")
        
        # Limpiar archivos temporales
        try:
            os.unlink(cert_pem_path)
            os.unlink(key_pem_path)
        except:
            pass
        
        return False
        
    except Exception as e:
        print(f"❌ ERROR: {e}")
        
        # Limpiar archivos temporales
        try:
            os.unlink(cert_pem_path)
            os.unlink(key_pem_path)
        except:
            pass
        
        return False


def main():
    if len(sys.argv) < 2:
        print("Uso: python enviar_de_sifen_con_certificado.py <archivo_xml_firmado>")
        print()
        print("Variables de entorno requeridas:")
        print("  SIFEN_CERT_PATH - Ruta al certificado P12")
        print("  SIFEN_CERT_PASS - Contraseña del certificado")
        print("  SIFEN_CSC (opcional) - CSC genérico TEST")
        print()
        print("Ejemplo:")
        print("  export SIFEN_CERT_PATH='/Users/robinklaiss/.sifen/certs/F1T_65478.p12'")
        print("  export SIFEN_CERT_PASS='bH1%T7EP'")
        print("  python tools/enviar_de_sifen_con_certificado.py ~/Desktop/sifen_de_firmado_test.xml")
        sys.exit(1)
    
    xml_path = sys.argv[1]
    
    if not os.path.exists(xml_path):
        print(f"❌ Error: Archivo no encontrado: {xml_path}")
        sys.exit(1)
    
    # Obtener certificado de variables de entorno
    cert_path = os.getenv("SIFEN_CERT_PATH")
    cert_pass = os.getenv("SIFEN_CERT_PASS")
    
    if not cert_path or not cert_pass:
        print("❌ Error: Variables de entorno no configuradas")
        print()
        print("Configura:")
        print("  export SIFEN_CERT_PATH='/ruta/al/certificado.p12'")
        print("  export SIFEN_CERT_PASS='contraseña'")
        sys.exit(1)
    
    if not os.path.exists(cert_path):
        print(f"❌ Error: Certificado no encontrado: {cert_path}")
        sys.exit(1)
    
    csc = os.getenv("SIFEN_CSC", "ABCD0000000000000000000000000000")
    
    print()
    print("="*70)
    print("ENVÍO DE DE A SIFEN TEST CON CERTIFICADO")
    print("="*70)
    print()
    print(f"Archivo XML: {xml_path}")
    print(f"Certificado: {cert_path}")
    print(f"CSC: {csc}")
    print()
    
    success = enviar_de_con_certificado(xml_path, cert_path, cert_pass, csc)
    
    if success:
        print()
        print("="*70)
        print("✅ ENVÍO COMPLETADO")
        print("="*70)
        sys.exit(0)
    else:
        print()
        print("="*70)
        print("❌ ENVÍO FALLÓ")
        print("="*70)
        sys.exit(1)


if __name__ == "__main__":
    main()
