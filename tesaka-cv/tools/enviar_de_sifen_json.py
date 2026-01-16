#!/usr/bin/env python3
"""
Script para enviar DE firmado a SIFEN TEST usando JSON/REST

Uso:
    python tools/enviar_de_sifen_json.py <archivo_xml_firmado>
    
Ejemplo:
    python tools/enviar_de_sifen_json.py ~/Desktop/sifen_de_firmado_test.xml
"""

import sys
import os
from pathlib import Path

# Agregar el directorio raíz al path
sys.path.insert(0, str(Path(__file__).parent.parent))

import requests
from lxml import etree


def enviar_de_json(xml_path: str, csc: str = "ABCD0000000000000000000000000000"):
    """
    Envía un DE firmado a SIFEN TEST usando JSON/REST
    
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
    
    # Endpoint JSON de SIFEN TEST (si existe)
    # Nota: Probando diferentes variantes de URL
    urls_to_try = [
        "https://sifen-test.set.gov.py/de/ws/sync/recibe.json",
        "https://sifen-test.set.gov.py/api/de/recibe",
        "https://sifen-test.set.gov.py/de/recibe",
    ]
    
    # Codificar XML en base64
    import base64
    xml_base64 = base64.b64encode(xml_content).decode('utf-8')
    
    # Payload JSON
    payload = {
        "dId": cdc,
        "xDE": xml_base64,
        "dCSC": csc
    }
    
    headers = {
        'Content-Type': 'application/json',
        'Accept': 'application/json'
    }
    
    print("="*70)
    print("ENVIANDO A SIFEN TEST (JSON/REST)")
    print("="*70)
    print(f"CDC: {cdc}")
    print(f"CSC: {csc}")
    print(f"Protocolo: JSON/REST")
    print()
    
    # Probar cada URL
    for url in urls_to_try:
        print(f"Probando URL: {url}")
        
        try:
            response = requests.post(url, json=payload, headers=headers, timeout=30)
            
            print(f"  Status Code: {response.status_code}")
            
            if response.status_code == 200:
                print("  ✅ RESPUESTA EXITOSA")
                print()
                
                try:
                    result = response.json()
                    print("Respuesta JSON:")
                    import json
                    print(json.dumps(result, indent=2, ensure_ascii=False))
                    
                    # Verificar código de respuesta
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
                    
                    return True
                    
                except Exception as e:
                    print(f"  Respuesta (texto):")
                    print(f"  {response.text}")
                    return True
                    
            elif response.status_code == 404:
                print("  ⚠️  Endpoint no encontrado (404)")
                continue
            elif response.status_code == 405:
                print("  ⚠️  Método no permitido (405)")
                continue
            else:
                print(f"  ❌ Error: {response.status_code}")
                print(f"  Respuesta: {response.text[:200]}")
                continue
                
        except requests.exceptions.Timeout:
            print("  ⚠️  Timeout")
            continue
        except requests.exceptions.ConnectionError as e:
            print(f"  ⚠️  Error de conexión: {str(e)[:100]}")
            continue
        except Exception as e:
            print(f"  ⚠️  Error: {str(e)[:100]}")
            continue
    
    print()
    print("❌ Ninguna URL JSON funcionó")
    print()
    print("Nota: SIFEN puede requerir SOAP en lugar de JSON.")
    print("Prueba con: python tools/enviar_de_sifen_soap.py")
    
    return False


def main():
    if len(sys.argv) < 2:
        print("Uso: python enviar_de_sifen_json.py <archivo_xml_firmado>")
        print()
        print("Ejemplo:")
        print("  python tools/enviar_de_sifen_json.py ~/Desktop/sifen_de_firmado_test.xml")
        print()
        print("CSC genéricos de SIFEN TEST:")
        print("  IDCSC: 1 → ABCD0000000000000000000000000000")
        print("  IDCSC: 2 → EFGH0000000000000000000000000000")
        print()
        print("Nota: Si este script falla, prueba la versión SOAP:")
        print("  python tools/enviar_de_sifen_soap.py <archivo_xml>")
        sys.exit(1)
    
    xml_path = sys.argv[1]
    
    if not os.path.exists(xml_path):
        print(f"❌ Error: Archivo no encontrado: {xml_path}")
        sys.exit(1)
    
    csc = os.getenv("SIFEN_CSC", "ABCD0000000000000000000000000000")
    
    print()
    print("="*70)
    print("ENVÍO DE DE A SIFEN TEST (JSON/REST)")
    print("="*70)
    print()
    print(f"Archivo: {xml_path}")
    print(f"CSC: {csc}")
    print()
    
    success = enviar_de_json(xml_path, csc)
    
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
        print()
        print("Recomendación: Prueba la versión SOAP")
        print("  python tools/enviar_de_sifen_soap.py ~/Desktop/sifen_de_firmado_test.xml")
        sys.exit(1)


if __name__ == "__main__":
    main()
