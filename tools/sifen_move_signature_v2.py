#!/usr/bin/env python3
"""
Mover ds:Signature de rDE a dentro de DE (último hijo)

Input: XML firmado donde ds:Signature es hijo de rDE
Output: XML con ds:Signature como último hijo de DE
"""

import argparse
from pathlib import Path
import sys

try:
    import lxml.etree as etree
except ImportError:
    print("ERROR: lxml no disponible")
    sys.exit(1)

def move_signature(input_path: Path, output_path: Path) -> None:
    # Parsear XML
    with open(input_path, 'rb') as f:
        root = etree.parse(f).getroot()
    
    # Namespaces
    ns = {
        'ds': 'http://www.w3.org/2000/09/xmldsig#',
        'sifen': 'http://ekuatia.set.gov.py/sifen/xsd'
    }
    
    # Encontrar Signature
    signatures = root.xpath('//ds:Signature', namespaces=ns)
    if not signatures:
        print("ERROR: No ds:Signature found")
        sys.exit(1)
    
    signature = signatures[0]
    
    # Verificar que parent sea rDE
    parent = signature.getparent()
    if parent is None or etree.QName(parent).localname != 'rDE':
        print("ERROR: Signature parent is not rDE")
        sys.exit(1)
    
    # Encontrar DE
    de_elements = root.xpath('//sifen:DE', namespaces=ns)
    if not de_elements:
        de_elements = root.xpath('//DE')  # fallback sin namespace
    
    if not de_elements:
        print("ERROR: No DE element found")
        sys.exit(1)
    
    de_elem = de_elements[0]
    
    # Mover Signature
    parent.remove(signature)
    de_elem.append(signature)
    
    # Guardar
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, 'wb') as f:
        f.write(etree.tostring(root, encoding='UTF-8', xml_declaration=True))
    
    # Verificación
    new_parent = signature.getparent()
    print("OK moved signature")
    print(f"Signature parent: {etree.QName(new_parent).localname}")
    print(f"Output: {output_path}")

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('input_xml', type=Path)
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    
    move_signature(args.input_xml, args.out)

if __name__ == '__main__':
    main()
