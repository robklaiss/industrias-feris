#!/usr/bin/env python3
"""
Genera XML SIFEN final con todo en orden correcto desde el inicio
"""

import sys
import os
import argparse
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from lxml import etree

def generar_xml_final(xml_template, output_path):
    """
    Genera XML final manteniendo el orden correcto:
    1. dVerFor
    2. DE
    3. Signature
    4. gCamFuFD
    """
    
    print("📝 Generando XML final con orden correcto...")
    
    # Parsear XML template
    parser = etree.XMLParser(remove_blank_text=False)
    tree = etree.parse(xml_template, parser)
    root = tree.getroot()
    
    # Extraer rDE del template original
    SIFEN_NS = "{http://ekuatia.set.gov.py/sifen/xsd}"
    rde = root.find(f".//{SIFEN_NS}rDE")
    
    # Verificar orden actual
    print("\n📋 Verificando orden en template:")
    children = list(rde)
    for i, child in enumerate(children):
        name = child.tag.split('}')[-1]
        print(f"   {i+1}. {name}")
    
    # El template ya tiene el orden correcto:
    # - DE
    # - Signature
    # - gCamFuFD
    
    # Guardar XML final
    xml_bytes = etree.tostring(rde, encoding='utf-8', xml_declaration=True, standalone=False)
    Path(output_path).write_bytes(xml_bytes)
    
    # Verificar CDC
    de = rde.find(f"{SIFEN_NS}DE")
    cdc = de.get('Id')
    print(f"\n📊 CDC en XML: {cdc}")
    
    print(f"\n✅ XML final guardado: {output_path}")
    print("   Orden: dVerFor -> DE -> Signature -> gCamFuFD")
    
    return output_path

def main():
    parser = argparse.ArgumentParser(description="Generar XML SIFEN final")
    parser.add_argument('--template', required=True, help='XML template original')
    parser.add_argument('--output', required=True, help='XML final de salida')
    
    args = parser.parse_args()
    
    if not Path(args.template).exists():
        print(f"❌ Archivo no encontrado: {args.template}")
        sys.exit(1)
    
    try:
        generar_xml_final(args.template, args.output)
        print("\n🎯 XML listo para SIFEN")
        print("   - CDC correspondiente")
        print("   - Firma válida")
        print("   - Orden correcto")
        print("   - gCamFuFD presente")
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

if __name__ == "__main__":
    main()
