#!/usr/bin/env python3
"""
Inspeccionar posición de firma XMLDSig en SIFEN
"""

import sys
from pathlib import Path

try:
    import lxml.etree as etree
except ImportError:
    print("ERROR: lxml no disponible")
    sys.exit(1)

def main():
    if len(sys.argv) != 2:
        print("USAGE: .venv/bin/python tools/sifen_inspect_signature.py <archivo.xml>")
        sys.exit(1)
    
    xml_path = Path(sys.argv[1])
    if not xml_path.exists():
        print(f"ERROR: Archivo no encontrado: {xml_path}")
        sys.exit(1)
    
    # Parsear XML
    try:
        with open(xml_path, 'rb') as f:
            root = etree.parse(f).getroot()
    except Exception as e:
        print(f"ERROR: No se pudo parsear XML: {e}")
        sys.exit(1)
    
    # Namespaces
    ns = {
        'sifen': 'http://ekuatia.set.gov.py/sifen/xsd',
        'ds': 'http://www.w3.org/2000/09/xmldsig#'
    }
    
    # Buscar Signature
    signatures = root.xpath('//ds:Signature', namespaces=ns)
    has_signature = len(signatures) > 0
    print(f"HAS Signature: {has_signature}")
    
    if not has_signature:
        print("ERROR: No se encontró ds:Signature")
        sys.exit(1)
    
    signature = signatures[0]
    parent = signature.getparent()
    
    if parent is None:
        print("Signature parent tag: None")
        print("FAIL: Signature sin parent")
        sys.exit(2)
    
    parent_tag = etree.QName(parent).localname
    print(f"Signature parent tag: {parent_tag}")
    
    # Buscar DE
    de_elements = root.xpath('//sifen:DE', namespaces=ns)
    if not de_elements:
        de_elements = root.xpath('//DE')  # fallback sin namespace
    
    if not de_elements:
        print("DE tag: None")
        print("ERROR: No se encontró elemento DE")
        sys.exit(1)
    
    de_tag = etree.QName(de_elements[0]).localname
    print(f"DE tag: {de_tag}")
    
    # Verificar posición
    if parent_tag == "DE":
        print("OK: Signature dentro de DE")
        sys.exit(0)
    else:
        print("FAIL: Signature fuera de DE")
        sys.exit(2)

if __name__ == '__main__':
    main()
