#!/usr/bin/env python3
"""
Script de diagnóstico para encontrar el DE Id dentro de un XML SIFEN.

Busca el elemento DE independientemente de:
- Prefijos de namespace (ns0, ns2, default ns, etc.)
- Case del atributo Id (Id, ID, id)
- Estructura del XML (puede estar en rDE, xDE, rLoteDE, etc.)

Uso:
    python -m tools.debug_find_de_id [path_to_xml]
    python -m tools.debug_find_de_id artifacts/sirecepde_NEW.xml
"""
import sys
import argparse
from pathlib import Path
from typing import Optional, Dict, Any

# Intentar importar lxml primero (más robusto)
try:
    import lxml.etree as etree
    HAS_LXML = True
except ImportError:
    try:
        import xml.etree.ElementTree as etree
        HAS_LXML = False
    except ImportError:
        print("❌ ERROR: No se encontró lxml ni xml.etree.ElementTree")
        print("   Instala lxml: pip install lxml")
        sys.exit(0)


def get_localname(tag: str) -> str:
    """Extrae el localname de un tag QName '{ns}local' o el tag si no tiene ns."""
    if '}' in tag:
        return tag.split('}', 1)[1]
    return tag


def get_attrib_case_insensitive(elem: Any, key: str) -> Optional[str]:
    """
    Obtiene un atributo de forma case-insensitive.
    
    Args:
        elem: Elemento XML (lxml o ElementTree)
        key: Nombre del atributo (case-insensitive)
        
    Returns:
        Valor del atributo o None si no existe
    """
    # Normalizar key a lowercase para comparación
    key_lower = key.lower()
    
    # Intentar obtener directamente
    if hasattr(elem, 'attrib'):
        # Buscar en attrib dict (case-insensitive)
        for attr_key, attr_value in elem.attrib.items():
            if attr_key.lower() == key_lower:
                return attr_value
        
        # Si no se encuentra, intentar métodos directos
        if hasattr(elem, 'get'):
            # Intentar con diferentes cases
            for variant in [key, key.upper(), key.lower(), key.capitalize()]:
                value = elem.get(variant)
                if value is not None:
                    return value
    
    return None


def find_de_element(root: Any) -> Optional[Any]:
    """
    Busca el primer elemento cuyo localname sea "DE".
    
    Args:
        root: Elemento raíz del XML
        
    Returns:
        Elemento DE encontrado o None
    """
    # Buscar recursivamente
    for elem in root.iter():
        localname = get_localname(elem.tag)
        if localname == "DE":
            return elem
    return None


def find_candidate_elements(root: Any, candidate_names: set) -> list:
    """
    Busca elementos candidatos con localname en candidate_names.
    
    Args:
        root: Elemento raíz del XML
        candidate_names: Set de localnames a buscar
        
    Returns:
        Lista de tuplas (tag_completo, localname, attribs_dict)
    """
    candidates = []
    for elem in root.iter():
        localname = get_localname(elem.tag)
        if localname in candidate_names:
            # Obtener atributos
            if hasattr(elem, 'attrib'):
                attribs = dict(elem.attrib)
            else:
                attribs = {}
            candidates.append((elem.tag, localname, attribs))
            if len(candidates) >= 15:
                break
    return candidates


def main():
    parser = argparse.ArgumentParser(
        description="Busca el DE Id dentro de un XML SIFEN",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Ejemplos:
  python -m tools.debug_find_de_id artifacts/sirecepde_NEW.xml
  python -m tools.debug_find_de_id /path/to/file.xml
        """
    )
    parser.add_argument(
        'xml_path',
        nargs='?',
        default='artifacts/sirecepde_NEW.xml',
        help='Path al archivo XML (default: artifacts/sirecepde_NEW.xml)'
    )
    
    args = parser.parse_args()
    xml_path = Path(args.xml_path)
    
    # Verificar que el archivo existe
    if not xml_path.exists():
        print(f"❌ ERROR: Archivo no encontrado: {xml_path}")
        print(f"   Path absoluto: {xml_path.resolve()}")
        sys.exit(0)
    
    # Obtener tamaño del archivo
    file_size = xml_path.stat().st_size
    print(f"📄 Archivo: {xml_path}")
    print(f"   Tamaño: {file_size} bytes ({file_size / 1024:.2f} KB)")
    print(f"   Parser: {'lxml' if HAS_LXML else 'xml.etree.ElementTree'}\n")
    
    # Parsear XML
    try:
        if HAS_LXML:
            parser = etree.XMLParser(remove_blank_text=False, recover=False)
            tree = etree.parse(str(xml_path), parser=parser)
            root = tree.getroot()
        else:
            tree = etree.parse(str(xml_path))
            root = tree.getroot()
    except Exception as e:
        print(f"❌ ERROR al parsear XML: {e}")
        sys.exit(0)
    
    # Información del root
    root_tag = root.tag
    root_localname = get_localname(root_tag)
    print(f"📋 Root tag completo: {root_tag}")
    print(f"   Root localname: {root_localname}\n")
    
    # Contar elementos totales
    element_count = sum(1 for _ in root.iter())
    print(f"📊 Elementos totales en el XML: {element_count}\n")
    
    # Buscar elemento DE
    de_elem = find_de_element(root)
    
    if de_elem is None:
        print("❌ No se encontró ningún elemento DE en el XML\n")
        
        # Buscar elementos candidatos
        candidate_names = {"rEnviDe", "rLoteDE", "xDE", "rDE", "DE", "gDE"}
        candidates = find_candidate_elements(root, candidate_names)
        
        if candidates:
            print(f"🔍 Elementos candidatos encontrados (primeros {len(candidates)}):")
            for i, (tag, localname, attribs) in enumerate(candidates, 1):
                print(f"   {i}. Tag: {tag}")
                print(f"      Localname: {localname}")
                if attribs:
                    print(f"      Atributos: {attribs}")
                else:
                    print(f"      Atributos: (ninguno)")
                print()
        else:
            print("   No se encontraron elementos candidatos (rEnviDe, rLoteDE, xDE, rDE, DE, gDE)\n")
        
        sys.exit(0)
    
    # DE encontrado
    print("✅ Elemento DE encontrado:")
    print(f"   Tag completo: {de_elem.tag}")
    print(f"   Localname: {get_localname(de_elem.tag)}")
    
    # Obtener atributos
    if hasattr(de_elem, 'attrib'):
        attribs = dict(de_elem.attrib)
    else:
        attribs = {}
    
    print(f"   Atributos disponibles: {attribs}\n")
    
    # Buscar Id (case-insensitive)
    de_id = get_attrib_case_insensitive(de_elem, "Id")
    
    if de_id:
        print(f"✅ DE Id encontrado: {de_id}")
        print(f"   Longitud: {len(de_id)} caracteres")
        if de_id.isdigit():
            print(f"   Es numérico: ✅ ({len(de_id)} dígitos)")
        else:
            print(f"   Es numérico: ❌ (contiene caracteres no numéricos)")
    else:
        print("❌ No se encontró atributo Id/ID/id en el elemento DE")
        print("   Atributos disponibles:")
        for key, value in attribs.items():
            print(f"      - {key}: {value}")
    
    print()
    sys.exit(0)


if __name__ == "__main__":
    main()

