#!/usr/bin/env python3
"""
Herramienta para mover ds:Signature dentro del elemento DE

Toma un XML firmado actual (con Signature como hijo de rDE) y lo mueve
para que sea el último hijo del elemento DE (enveloped signature).

Esto es un fix ONE-OFF para probar si SIFEN reconoce la firma
cuando está dentro de DE.

Uso:
    python tools/sifen_move_signature_into_de.py <input.xml> --out <output.xml>
"""

import sys
import argparse
from pathlib import Path
from typing import Optional

try:
    import lxml.etree as etree
    LXML_AVAILABLE = True
except ImportError:
    LXML_AVAILABLE = False
    print("ERROR: lxml no está disponible. Instale con: pip install lxml")
    sys.exit(1)

# Namespaces
DS_NS = "http://www.w3.org/2000/09/xmldsig#"
SIFEN_NS = "http://ekuatia.set.gov.py/sifen/xsd"

def move_signature_into_de(xml_path: Path) -> str:
    """
    Mueve ds:Signature de rDE a dentro del elemento DE.
    
    Args:
        xml_path: Ruta al archivo XML firmado
        
    Returns:
        XML modificado como string
        
    Raises:
        ValueError: Si no se puede realizar la operación
    """
    if not xml_path.exists():
        raise FileNotFoundError(f"Archivo no encontrado: {xml_path}")
    
    # Parsear XML
    try:
        with open(xml_path, 'r', encoding='utf-8') as f:
            xml_content = f.read()
        
        root = etree.fromstring(xml_content.encode('utf-8'))
    except Exception as e:
        raise ValueError(f"Error al parsear XML: {e}")
    
    print(f"📄 Procesando: {xml_path}")
    print(f"🏗️  Elemento raíz: {etree.QName(root).localname}")
    
    # Verificar que sea rDE
    if etree.QName(root).localname != "rDE":
        raise ValueError("Elemento raíz no es rDE")
    
    # Buscar ds:Signature
    ns = {"ds": DS_NS}
    signatures = root.xpath(".//ds:Signature", namespaces=ns)
    
    if not signatures:
        raise ValueError("No se encontró ds:Signature en el XML")
    
    if len(signatures) > 1:
        print(f"⚠️  Se encontraron {len(signatures)} firmas, se usará la primera")
    
    signature = signatures[0]
    
    # Determinar parent actual
    current_parent = signature.getparent()
    current_parent_name = etree.QName(current_parent).localname if current_parent is not None else "None"
    print(f"📍 Ubicación actual: Signature como hijo de {current_parent_name}")
    
    # Buscar elemento DE
    de_elements = root.xpath(".//sifen:DE", namespaces={"sifen": SIFEN_NS})
    if not de_elements:
        # Intentar sin namespace
        de_elements = root.xpath(".//DE")
    
    if not de_elements:
        raise ValueError("No se encontró elemento DE en el XML")
    
    de_elem = de_elements[0]
    de_id = de_elem.get("Id") or de_elem.get("id")
    print(f"📋 Elemento DE encontrado (Id: {de_id or 'sin Id'})")
    
    # Verificar que Signature no esté ya en DE
    if current_parent == de_elem:
        print("ℹ️  La firma ya está dentro de DE, no se necesita mover")
        return xml_content
    
    # Mover Signature a DE
    print("🔄 Moviendo Signature a DE...")
    
    # 1. Eliminar Signature de su ubicación actual
    if current_parent is not None:
        current_parent.remove(signature)
    
    # 2. Insertar Signature como último hijo de DE
    de_elem.append(signature)
    
    # 3. Eliminar cualquier Signature duplicada que pueda quedar
    all_signatures = root.xpath(".//ds:Signature", namespaces=ns)
    for sig in all_signatures[1:]:  # Mantener solo la primera
        parent = sig.getparent()
        if parent is not None:
            parent.remove(sig)
            print("🧹 Eliminada firma duplicada")
    
    # Serializar XML
    try:
        modified_xml = etree.tostring(
            root, xml_declaration=True, encoding="UTF-8", pretty_print=True
        ).decode("utf-8")
    except Exception as e:
        raise ValueError(f"Error al serializar XML: {e}")
    
    print("✅ Signature movida exitosamente")
    return modified_xml

def verify_signature_placement(xml_content: str) -> bool:
    """
    Verifica que la firma esté correctamente colocada.
    
    Args:
        xml_content: XML como string
        
    Returns:
        True si la firma está correctamente colocada
    """
    try:
        root = etree.fromstring(xml_content.encode('utf-8'))
    except Exception:
        return False
    
    # Buscar Signature
    ns = {"ds": DS_NS}
    signatures = root.xpath(".//ds:Signature", namespaces=ns)
    
    if not signatures:
        return False
    
    signature = signatures[0]
    parent = signature.getparent()
    
    if parent is None:
        return False
    
    # Verificar que el parent sea DE
    parent_name = etree.QName(parent).localname
    return parent_name == "DE"

def main():
    parser = argparse.ArgumentParser(
        description="Mover ds:Signature dentro del elemento DE",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Ejemplos:
    python tools/sifen_move_signature_into_de.py ~/Desktop/sifen_de_firmado_test.xml --out ~/Desktop/sifen_de_firmado_sig_in_de.xml
    python tools/sifen_move_signature_into_de.py input.xml --out output.xml
        """
    )
    
    parser.add_argument(
        "input_file",
        type=Path,
        help="Archivo XML de entrada (firmado con Signature fuera de DE)"
    )
    
    parser.add_argument(
        "--out",
        type=Path,
        required=True,
        help="Archivo XML de salida (con Signature dentro de DE)"
    )
    
    parser.add_argument(
        "--verify",
        action="store_true",
        help="Verificar la colocación de la firma después de mover"
    )
    
    args = parser.parse_args()
    
    try:
        # Mover firma
        modified_xml = move_signature_into_de(args.input_file)
        
        # Guardar archivo de salida
        args.out.parent.mkdir(parents=True, exist_ok=True)
        with open(args.out, 'w', encoding='utf-8') as f:
            f.write(modified_xml)
        
        print(f"💾 Guardado: {args.out}")
        
        # Verificación opcional
        if args.verify:
            print("\n🔍 Verificando colocación de la firma...")
            if verify_signature_placement(modified_xml):
                print("✅ Verificación exitosa: Signature está dentro de DE")
            else:
                print("❌ Verificación fallida: Signature no está dentro de DE")
                sys.exit(1)
        
        # Mostrar información básica del resultado
        print(f"\n📊 Resumen:")
        print(f"   📁 Entrada: {args.input_file}")
        print(f"   📁 Salida: {args.out}")
        print(f"   📏 Tamaño: {len(modified_xml)} caracteres")
        
        # Buscar patrones clave
        if "</DE><ds:Signature>" in modified_xml:
            print("   ⚠️  Advertencia: Signature todavía fuera de DE")
        elif "<ds:Signature>" in modified_xml and "</DE>" in modified_xml:
            # Verificar orden
            sig_pos = modified_xml.find("<ds:Signature>")
            de_end_pos = modified_xml.find("</DE>")
            if sig_pos < de_end_pos:
                print("   ✅ Signature está dentro de DE")
            else:
                print("   ❌ Signature está después de DE")
        
        print(f"\n🎯 Para probar con SIFEN:")
        print(f"   1. Subir {args.out.name} al prevalidador")
        print(f"   2. Enviar por SOAP mTLS")
        print(f"   3. Verificar si el error cambia de 'no tiene firma' a otro")
        
    except Exception as e:
        print(f"ERROR: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
