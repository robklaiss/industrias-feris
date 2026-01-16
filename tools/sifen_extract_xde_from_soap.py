


#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Extrae el nodo rDE desde un SOAP 1.2 envelope de SIFEN
Preserva la firma sin alterar whitespace
"""

import argparse
import sys
from pathlib import Path
from lxml import etree

def extract_rde_from_soap(soap_path: str, output_path: str) -> None:
    """Extrae rDE desde SOAP y lo escribe sin pretty_print"""
    
    # Parsear SOAP
    try:
        tree = etree.parse(soap_path)
        root = tree.getroot()
    except Exception as e:
        print(f"❌ ERROR: No se pudo parsear SOAP: {e}")
        sys.exit(1)
    
    # Namespaces
    ns = {
        "soap": "http://www.w3.org/2003/05/soap-envelope",
        "sifen": "http://ekuatia.set.gov.py/sifen/xsd"
    }
    
    # Buscar xDE -> rDE
    xde = root.xpath("//soap:Body/sifen:rEnviDe/sifen:xDE", namespaces=ns)
    if not xde:
        print("❌ ERROR: No se encontró xDE en el SOAP")
        sys.exit(1)
    
    xde = xde[0]
    
    # Extraer rDE (puede estar directamente o dentro de rLoteDE)
    rde_children = list(xde)
    if not rde_children:
        print("❌ ERROR: No se encontró contenido dentro de xDE")
        sys.exit(1)
    
    first_child = rde_children[0]
    
    # Si el primer hijo es rLoteDE, buscar rDE dentro
    if first_child.tag.endswith('rLoteDE'):
        rde_in_lote = list(first_child)
        if not rde_in_lote or not rde_in_lote[0].tag.endswith('rDE'):
            print("❌ ERROR: No se encontró rDE dentro de rLoteDE")
            sys.exit(1)
        rde = rde_in_lote[0]
    elif first_child.tag.endswith('rDE'):
        rde = first_child
    else:
        print(f"❌ ERROR: Estructura inesperada en xDE: {first_child.tag}")
        sys.exit(1)
    
    # Escribir rDE sin pretty_print (preservar whitespace original)
    try:
        rde_bytes = etree.tostring(rde, encoding='UTF-8', xml_declaration=True, pretty_print=False)
        Path(output_path).write_bytes(rde_bytes)
        print(f"✅ rDE extraído: {output_path}")
    except Exception as e:
        print(f"❌ ERROR: No se pudo escribir rDE: {e}")
        sys.exit(1)

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("soap_path", help="Path al archivo SOAP 1.2")
    ap.add_argument("--out", default="/tmp/extracted_rDE.xml", help="Path de salida para rDE")
    args = ap.parse_args()
    
    soap_path = Path(args.soap_path)
    if not soap_path.exists():
        print(f"❌ ERROR: No existe {soap_path}")
        sys.exit(1)
    
    extract_rde_from_soap(str(soap_path), args.out)

if __name__ == "__main__":
    main()
