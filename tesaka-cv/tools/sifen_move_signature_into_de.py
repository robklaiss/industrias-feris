#!/usr/bin/env python3
"""
Mover ds:Signature de rDE a dentro de DE (último hijo)
"""

import argparse
import sys
from pathlib import Path

try:
    import lxml.etree as etree
except ImportError:
    print("ERROR: lxml no disponible")
    sys.exit(1)

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('input_xml', type=Path)
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--verify', action='store_true')
    args = parser.parse_args()
    
    # Validar input
    if not args.input_xml.exists():
        print(f"ERROR: Archivo no encontrado: {args.input_xml}")
        sys.exit(1)
    
    # Parsear XML
    try:
        with open(args.input_xml, 'rb') as f:
            root = etree.parse(f).getroot()
    except Exception as e:
        print(f"ERROR: No se pudo parsear XML: {e}")
        sys.exit(1)
    
    # Namespaces
    ns = {
        'sifen': 'http://ekuatia.set.gov.py/sifen/xsd',
        'ds': 'http://www.w3.org/2000/09/xmldsig#'
    }
    
    # Encontrar DE
    de_elements = root.xpath('//sifen:DE', namespaces=ns)
    if not de_elements:
        de_elements = root.xpath('//DE')  # fallback sin namespace
    
    if not de_elements:
        print("ERROR: No se encontró elemento DE")
        sys.exit(1)
    
    de_elem = de_elements[0]
    
    # Encontrar Signature
    signatures = root.xpath('//ds:Signature', namespaces=ns)
    if not signatures:
        print("ERROR: No se encontró ds:Signature")
        sys.exit(1)
    
    signature = signatures[0]
    
    # Validar que parent actual sea rDE
    parent = signature.getparent()
    if parent is None or etree.QName(parent).localname != 'rDE':
        print("ERROR: Signature parent no es rDE")
        sys.exit(1)
    
    # Mover Signature a DE (como último hijo)
    parent.remove(signature)
    de_elem.append(signature)
    
    # Crear directorio de salida si no existe
    args.out.parent.mkdir(parents=True, exist_ok=True)
    
    # Guardar XML
    try:
        with open(args.out, 'wb') as f:
            f.write(etree.tostring(root, encoding='UTF-8', xml_declaration=True, pretty_print=False))
    except Exception as e:
        print(f"ERROR: No se pudo guardar archivo: {e}")
        sys.exit(1)
    
    print(f"Signature movida exitosamente a: {args.out}")
    
    # Verificación si se solicita
    if args.verify:
        try:
            with open(args.out, 'rb') as f:
                verify_root = etree.parse(f).getroot()
            
            verify_signatures = verify_root.xpath('//ds:Signature', namespaces=ns)
            if not verify_signatures:
                print("ERROR: Verificación falló - no Signature en output")
                sys.exit(3)
            
            verify_signature = verify_signatures[0]
            verify_parent = verify_signature.getparent()
            
            if verify_parent is None or etree.QName(verify_parent).localname != 'DE':
                print("ERROR: Verificación falló - Signature no está en DE")
                sys.exit(3)
            
            print("Verificación OK: Signature está dentro de DE")
            
        except Exception as e:
            print(f"ERROR: Verificación falló: {e}")
            sys.exit(3)

if __name__ == '__main__':
    main()
