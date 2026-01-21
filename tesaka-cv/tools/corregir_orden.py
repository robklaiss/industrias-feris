#!/usr/bin/env python3
"""
Corrige el orden de los elementos en XML SIFEN
Signature debe ir antes que gCamFuFD
"""

import sys
import os
import argparse
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from lxml import etree

def corregir_orden(xml_path, output_path):
    """Corrige el orden de Signature y gCamFuFD"""
    
    # Parsear XML
    parser = etree.XMLParser(remove_blank_text=False)
    tree = etree.parse(xml_path, parser)
    root = tree.getroot()
    
    SIFEN_NS = "{http://ekuatia.set.gov.py/sifen/xsd}"
    DS_NS = "{http://www.w3.org/2000/09/xmldsig#}"
    
    # Encontrar rDE
    rde = root
    if root.tag == "rLoteDE":
        rde = root.find(f".//{SIFEN_NS}rDE")
    
    # Extraer elementos
    signature = rde.find(f"{DS_NS}Signature")
    camfu = rde.find(f"{SIFEN_NS}gCamFuFD")
    
    # Eliminar elementos existentes
    if signature is not None:
        rde.remove(signature)
    if camfu is not None:
        rde.remove(camfu)
    
    # Reinsertar en orden correcto
    # 1. DE
    de = rde.find(f"{SIFEN_NS}DE")
    
    # 2. Signature (después de DE)
    if signature is not None:
        de.addnext(signature)
    
    # 3. gCamFuFD (después de Signature)
    if camfu is not None:
        if signature is not None:
            signature.addnext(camfu)
        else:
            de.addnext(camfu)
    
    # Guardar XML
    xml_bytes = etree.tostring(root, encoding='utf-8', xml_declaration=True)
    Path(output_path).write_bytes(xml_bytes)
    
    print(f"✅ Orden corregido: {output_path}")
    
    # Verificar orden
    print("\n📋 Orden de elementos en rDE:")
    children = list(rde)
    for i, child in enumerate(children):
        name = child.tag.split('}')[-1]
        print(f"   {i+1}. {name}")
    
    return output_path

def main():
    parser = argparse.ArgumentParser(description="Corregir orden de elementos XML SIFEN")
    parser.add_argument('--xml', required=True, help='XML a corregir')
    parser.add_argument('--output', required=True, help='XML corregido')
    
    args = parser.parse_args()
    
    if not Path(args.xml).exists():
        print(f"❌ Archivo no encontrado: {args.xml}")
        sys.exit(1)
    
    try:
        corregir_orden(args.xml, args.output)
        print("\n✅ XML listo para SIFEN")
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

if __name__ == "__main__":
    main()
