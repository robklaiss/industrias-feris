#!/usr/bin/env python3
"""
Script ONE-OFF para arreglar ubicación de firma XMLDSIG en SIFEN v150.

Este script toma un XML firmado de SIFEN donde la ds:Signature está 
incorrectamente dentro del elemento DE y la mueve a su ubicación correcta
como hijo directo de rDE, justo después del elemento DE.

Uso:
    python tools/sifen_fix_signature_placement.py <path_xml_firmado>

Output:
    Mismo XML pero guardado como *_sigfix.xml
"""

import sys
import argparse
from pathlib import Path
from lxml import etree

def fix_signature_placement(xml_path: Path) -> Path:
    """
    Mueve ds:Signature desde dentro de DE a ser hijo directo de rDE.
    
    Args:
        xml_path: Path al XML firmado
        
    Returns:
        Path al archivo corregido
    """
    # Parsear XML
    parser = etree.XMLParser(remove_blank_text=True)
    tree = etree.parse(str(xml_path), parser)
    root = tree.getroot()
    
    # Encontrar ds:Signature
    ds_ns = "http://www.w3.org/2000/09/xmldsig#"
    ns = {"ds": ds_ns}
    
    signatures = root.xpath(".//ds:Signature", namespaces=ns)
    if not signatures:
        raise ValueError("No se encontró ds:Signature en el XML")
    
    signature = signatures[0]
    original_parent = signature.getparent()
    
    print(f"Signature encontrada: True")
    print(f"Signature parent tag: {original_parent.tag}")
    
    # Encontrar DE
    de_elements = root.xpath(".//DE", namespaces={"sifen": "http://ekuatia.set.gov.py/sifen/xsd"})
    if not de_elements:
        de_elements = root.xpath(".//DE")
    
    if not de_elements:
        # Buscar directamente en los hijos del root
        for child in root:
            if etree.QName(child).localname == "DE":
                de_elements = [child]
                break
    
    if not de_elements:
        raise ValueError("No se encontró elemento DE en el XML")
    
    de_elem = de_elements[0]
    print(f"DE tag: {de_elem.tag}")
    
    # Verificar si ya está en la posición correcta
    if original_parent == root:
        print("✅ La firma ya está en la posición correcta (hija de rDE)")
        return xml_path
    
    # Verificar si está dentro de DE
    if original_parent != de_elem:
        print(f"⚠️  La firma no está dentro de DE ni en rDE. Parent actual: {original_parent.tag}")
    
    # Mover la firma
    # 1. Remover del parent actual
    original_parent.remove(signature)
    
    # 2. Insertar en rDE justo después de DE
    children = list(root)
    de_index = None
    for i, child in enumerate(children):
        if child == de_elem:
            de_index = i
            break
    
    if de_index is None:
        raise ValueError("No se encontró DE en los hijos de rDE")
    
    # Insertar firma después de DE
    root.insert(de_index + 1, signature)
    
    # Guardar archivo corregido
    output_path = xml_path.parent / f"{xml_path.stem}_sigfix.xml"
    
    # Serializar con pretty print
    xml_bytes = etree.tostring(
        root, 
        xml_declaration=True, 
        encoding="UTF-8", 
        pretty_print=True
    )
    
    output_path.write_bytes(xml_bytes)
    
    print(f"✅ Firma movida a rDE (después de DE)")
    print(f"📁 Archivo guardado en: {output_path}")
    
    return output_path

def main():
    parser = argparse.ArgumentParser(
        description="Arregla ubicación de ds:Signature en XML SIFEN v150"
    )
    parser.add_argument(
        "xml_path",
        type=Path,
        help="Path al XML firmado a arreglar"
    )
    
    args = parser.parse_args()
    
    if not args.xml_path.exists():
        print(f"❌ Error: No existe el archivo {args.xml_path}")
        sys.exit(1)
    
    try:
        output_path = fix_signature_placement(args.xml_path)
        print(f"\n✅ Proceso completado exitosamente")
        print(f"📄 Output: {output_path}")
    except Exception as e:
        print(f"❌ Error: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
