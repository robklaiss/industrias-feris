#!/usr/bin/env python3
"""
Script para enviar DE firmado a SIFEN TEST

Uso:
    python tools/enviar_de_sifen_test.py <archivo_xml_firmado>
    
Ejemplo:
    python tools/enviar_de_sifen_test.py ~/Desktop/sifen_de_test_signed.xml
"""

import sys
import os
from pathlib import Path

# Agregar el directorio raíz al path
sys.path.insert(0, str(Path(__file__).parent.parent))

import requests
from lxml import etree


def enviar_de_a_sifen_test(xml_path: str, csc: str = "ABCD0000000000000000000000000000"):
    """
    Envía un DE firmado a SIFEN TEST
    
    Args:
        xml_path: Ruta al archivo XML firmado
        csc: Código de Seguridad del Contribuyente (CSC genérico de SIFEN TEST)
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
    
    # Endpoint de SIFEN TEST para recepción de DEs (SOAP/WSDL)
    # IMPORTANTE: SIFEN usa SOAP, no REST/JSON
    url = "https://sifen-test.set.gov.py/de/ws/sync/recibe.wsdl"
    
    print("⚠️  IMPORTANTE: SIFEN usa SOAP/WSDL, no REST/JSON")
    print("   Este script es una demostración básica.")
    print("   Para envío real, se recomienda usar:")
    print("   - Librería jsifenlib (Java)")
    print("   - Cliente SOAP (zeep para Python)")
    print()
    print("   Por ahora, este script solo verifica la estructura del XML.")
    print()
    
    # Preparar datos para envío SOAP
    import base64
    xml_base64 = base64.b64encode(xml_content).decode('utf-8')
    
    # SOAP Envelope para SIFEN
    soap_body = f"""<?xml version="1.0" encoding="UTF-8"?>
<soapenv:Envelope xmlns:soapenv="http://schemas.xmlsoap.org/soap/envelope/" 
                  xmlns:rec="http://ekuatia.set.gov.py/sifen/recibe">
   <soapenv:Header/>
   <soapenv:Body>
      <rec:rEnviDe>
         <rec:dId>{cdc}</rec:dId>
         <rec:xDE>{xml_base64}</rec:xDE>
         <rec:dCSC>{csc}</rec:dCSC>
      </rec:rEnviDe>
   </soapenv:Body>
</soapenv:Envelope>"""
    
    headers = {
        'Content-Type': 'text/xml; charset=utf-8',
        'SOAPAction': ''
    }
    
    print("="*70)
    print("ENVIANDO A SIFEN TEST")
    print("="*70)
    print(f"URL: {url}")
    print(f"CDC: {cdc}")
    print(f"CSC: {csc}")
    print(f"Tamaño XML: {len(xml_content)} bytes")
    print()
    
    try:
        response = requests.post(url, data=soap_body, headers=headers, timeout=30)
        
        print(f"Status Code: {response.status_code}")
        print()
        
        if response.status_code == 200:
            print("✅ RESPUESTA EXITOSA")
            print()
            
            try:
                result = response.json()
                print("Respuesta JSON:")
                import json
                print(json.dumps(result, indent=2, ensure_ascii=False))
                
                # Verificar si hay errores en la respuesta
                if 'dCodRes' in result:
                    cod_res = result['dCodRes']
                    if cod_res == '0300':
                        print()
                        print("✅ DE APROBADO POR SIFEN")
                        return True
                    else:
                        print()
                        print(f"⚠️  Código de respuesta: {cod_res}")
                        if 'dMsgRes' in result:
                            print(f"Mensaje: {result['dMsgRes']}")
                        return False
                
            except Exception as e:
                print(f"Respuesta (texto):")
                print(response.text)
                
        else:
            print("❌ ERROR EN ENVÍO")
            print()
            print(f"Respuesta:")
            print(response.text)
            return False
            
    except requests.exceptions.Timeout:
        print("❌ ERROR: Timeout al conectar con SIFEN")
        return False
    except requests.exceptions.ConnectionError as e:
        print(f"❌ ERROR: No se pudo conectar con SIFEN: {e}")
        return False
    except Exception as e:
        print(f"❌ ERROR: {e}")
        return False
    
    return True


def main():
    if len(sys.argv) < 2:
        print("Uso: python enviar_de_sifen_test.py <archivo_xml_firmado>")
        print()
        print("Ejemplo:")
        print("  python tools/enviar_de_sifen_test.py ~/Desktop/sifen_de_test_signed.xml")
        print()
        print("CSC genéricos de SIFEN TEST:")
        print("  IDCSC: 1 → ABCD0000000000000000000000000000")
        print("  IDCSC: 2 → EFGH0000000000000000000000000000")
        sys.exit(1)
    
    xml_path = sys.argv[1]
    
    # Verificar que el archivo existe
    if not os.path.exists(xml_path):
        print(f"❌ Error: Archivo no encontrado: {xml_path}")
        sys.exit(1)
    
    # CSC genérico de SIFEN TEST (IDCSC: 1)
    csc = os.getenv("SIFEN_CSC", "ABCD0000000000000000000000000000")
    
    print()
    print("="*70)
    print("ENVÍO DE DE A SIFEN TEST")
    print("="*70)
    print()
    print(f"Archivo: {xml_path}")
    print(f"CSC: {csc}")
    print()
    
    success = enviar_de_a_sifen_test(xml_path, csc)
    
    if success:
        print()
        print("="*70)
        print("✅ ENVÍO EXITOSO")
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
