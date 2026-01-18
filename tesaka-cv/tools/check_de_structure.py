#!/usr/bin/env python3
"""
Verifica si el DE usa gValItem en lugar de gValTotItem según XSD v150
"""
import sys
from lxml import etree

def check_de_structure(xml_path: str) -> int:
    tree = etree.parse(xml_path)
    root = tree.getroot()
    ns = {'s': 'http://ekuatia.set.gov.py/sifen/xsd'}
    
    # Encontrar el DE
    de = root.find('.//s:DE', namespaces=ns)
    if de is None:
        print("❌ No se encontró elemento DE")
        return 2
    
    # Verificar qué elemento de totales usa
    gvaltotitem = de.find('.//s:gValTotItem', namespaces=ns)
    gvalitem = de.find('.//s:gValItem', namespaces=ns)
    
    print(f"gValTotItem: {'✅' if gvaltotitem is not None else '❌ no encontrado'}")
    print(f"gValItem: {'✅' if gvalitem is not None else '❌ no encontrado'}")
    
    # Si tiene gValItem, mostrar su contenido
    if gvalitem is not None:
        print("\nContenido de gValItem:")
        for child in gvalitem:
            tag = child.tag.split('}')[-1] if '}' in child.tag else child.tag
            print(f"  {tag}: {child.text}")
    
    # Verificar estructura completa del DE
    print("\nEstructura completa del DE:")
    for i, child in enumerate(de):
        tag = child.tag.split('}')[-1] if '}' in child.tag else child.tag
        print(f"  [{i:2d}] {tag}")
    
    return 0

if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Uso: python tools/check_de_structure.py <archivo.xml>", file=sys.stderr)
        sys.exit(2)
    
    xml_path = sys.argv[1]
    sys.exit(check_de_structure(xml_path))
