#!/usr/bin/env python3
"""
Generador de siRecepDE (envelope de recepción) para SIFEN v150

Wrappea un DE crudo dentro de rEnviDe con xDE, según WS_SiRecepDE_v150.xsd.

Según la Nota Técnica NT_E_KUATIA_010_MT_V150.pdf:
"xDE = XML del DE transmitido"

Uso:
    python -m tools.build_sirecepde --de de_test.xml --output sirecepde_test.xml
    python -m tools.build_sirecepde --de de_test.xml --did 1 --output sirecepde_test.xml
"""
import sys
import argparse
import xml.etree.ElementTree as ET
from pathlib import Path
from datetime import datetime
import re

# Agregar el directorio padre al path para imports
sys.path.insert(0, str(Path(__file__).parent.parent))


def strip_xml_declaration(xml_content: str) -> str:
    """
    Remueve la declaración XML (<?xml ...?>) y cualquier BOM/espacios iniciales
    
    Args:
        xml_content: Contenido XML que puede incluir declaración XML
        
    Returns:
        XML sin declaración y sin espacios/BOM iniciales
    """
    # Remover BOM si existe
    if xml_content.startswith('\ufeff'):
        xml_content = xml_content[1:]
    
    # Remover espacios iniciales
    xml_content = xml_content.lstrip()
    
    # Remover declaración XML si existe
    if xml_content.startswith('<?xml'):
        # Buscar el cierre de la declaración ?>
        end_decl = xml_content.find('?>')
        if end_decl >= 0:
            xml_content = xml_content[end_decl + 2:]
            # Remover cualquier espacio/newline después de la declaración
            xml_content = xml_content.lstrip()
    
    return xml_content


def build_sirecepde_xml(
    de_xml_content: str,
    d_id: str = "1"
) -> str:
    """
    Wrappea un DE crudo dentro de rEnviDe según WS_SiRecepDE_v150.xsd
    
    IMPORTANTE: El contenido de xDE NO debe incluir la declaración XML <?xml ...?>
    porque eso causaría "XML or text declaration not at start of entity"
    
    Args:
        de_xml_content: Contenido XML del DE crudo (puede incluir prolog XML)
        d_id: Identificador de control de envío (default: "1")
        
    Returns:
        XML siRecepDE completo (rEnviDe con xDE) con declaración XML única al inicio
    """
    # Remover declaración XML del DE para evitar conflicto
    de_without_declaration = strip_xml_declaration(de_xml_content)
    
    # Namespace: http://ekuatia.set.gov.py/sifen/xsd
    ns = "http://ekuatia.set.gov.py/sifen/xsd"
    ds_ns = "http://www.w3.org/2000/09/xmldsig#"
    
    # Registrar namespaces para que ET.tostring() los incluya con prefijos
    # register_namespace('', ns) hace que ET.tostring() agregue xmlns automáticamente
    ET.register_namespace('', ns)  # Namespace por defecto
    ET.register_namespace('ds', ds_ns)  # Namespace para ds:Signature
    
    # Crear elemento raíz rEnviDe usando ET
    # NO establecer xmlns manualmente ya que register_namespace('', ns) lo maneja
    # Solo establecer xmlns:ds que no se maneja automáticamente
    root = ET.Element(f"{{{ns}}}rEnviDe")
    root.set("xmlns:ds", ds_ns)  # Declarar namespace para ds:Signature que puede estar en el DE
    
    # dId: Identificador de control de envío
    d_id_elem = ET.SubElement(root, f"{{{ns}}}dId")
    d_id_elem.text = str(d_id)
    
    # xDE: XML del DE transmitido
    # Según el XSD, xDE contiene <xs:any namespace="..." processContents="skip"/>
    # Esto significa que puede contener cualquier elemento del namespace correcto
    x_de_elem = ET.SubElement(root, f"{{{ns}}}xDE")
    
    # Parsear el DE sin declaración y agregarlo como hijo de xDE
    try:
        # El DE debe tener el namespace correcto
        # Parsear el DE sin declaración XML
        de_root = ET.fromstring(de_without_declaration)
        
        # Si el DE tiene namespace, preservarlo; si no, agregar el namespace correcto
        if de_root.tag.startswith('{') and '}' in de_root.tag:
            # Ya tiene namespace, usar directamente
            x_de_elem.append(de_root)
        else:
            # No tiene namespace explícito, asumir que es DE y agregar namespace
            # Crear nuevo elemento DE con namespace correcto
            de_with_ns = ET.Element(f"{{{ns}}}DE")
            # Copiar atributos
            for attr, value in de_root.attrib.items():
                de_with_ns.set(attr, value)
            # Copiar hijos recursivamente
            for child in de_root:
                _copy_element_with_ns(child, de_with_ns, ns)
            de_with_ns.text = de_root.text
            de_with_ns.tail = de_root.tail
            x_de_elem.append(de_with_ns)
            
    except ET.ParseError as e:
        # Si falla el parseo, intentar como texto XML (último recurso)
        # Esto puede ocurrir si el DE tiene estructura compleja
        x_de_elem.text = de_without_declaration
    
    # Serializar a XML string
    # Usar ET.tostring con encoding='unicode' y agregar prolog manualmente
    xml_body = ET.tostring(root, encoding='unicode', xml_declaration=False)
    
    # Limpiar atributos duplicados que pueden ocurrir cuando se copian elementos
    # ET.tostring() puede duplicar xmlns:ds si el DE también lo declara
    # Buscar y remover duplicados de xmlns:ds
    import re
    # Patrón para encontrar xmlns:ds duplicado en el mismo elemento
    # Buscar: xmlns:ds="..." xmlns:ds="..." (duplicado consecutivo)
    xml_body = re.sub(
        r'xmlns:ds="[^"]*"\s+xmlns:ds="[^"]*"',
        'xmlns:ds="' + ds_ns + '"',
        xml_body
    )
    
    # También limpiar si está al inicio del tag (después de otros atributos)
    # Buscar: ... xmlns:ds="..." xmlns:ds="..."
    xml_body = re.sub(
        r'(\S+)\s+xmlns:ds="[^"]*"\s+xmlns:ds="[^"]*"',
        r'\1 xmlns:ds="' + ds_ns + '"',
        xml_body
    )
    
    # Asegurar que comienza EXACTAMENTE con <?xml (sin espacios/BOM)
    result = f'<?xml version="1.0" encoding="UTF-8"?>\n{xml_body}'
    
    # Verificar que no hay espacios antes del prolog
    if not result.startswith('<?xml'):
        # Remover cualquier espacio/BOM inicial
        result = result.lstrip('\ufeff \t\n\r') + result.lstrip('\ufeff \t\n\r')
        # Agregar prolog si falta
        if not result.startswith('<?xml'):
            result = '<?xml version="1.0" encoding="UTF-8"?>\n' + result
    
    return result


def _copy_element_with_ns(source, target, namespace):
    """Copia recursivamente elementos preservando/agregando namespace"""
    for child in source:
        child_tag = child.tag
        # Si tiene namespace, mantenerlo; si no, agregar el namespace proporcionado
        if child_tag.startswith('{') and '}' in child_tag:
            new_child = ET.SubElement(target, child_tag)
        else:
            new_child = ET.SubElement(target, f"{{{namespace}}}{child_tag}")
        
        # Copiar atributos
        for attr, value in child.attrib.items():
            new_child.set(attr, value)
        
        # Copiar texto y tail
        new_child.text = child.text
        new_child.tail = child.tail
        
        # Copiar hijos recursivamente
        _copy_element_with_ns(child, new_child, namespace)


def main():
    parser = argparse.ArgumentParser(
        description="Genera un XML siRecepDE wrappeando un DE crudo"
    )
    parser.add_argument(
        "--de", "-d",
        type=Path,
        required=True,
        help="Archivo XML del DE crudo"
    )
    parser.add_argument(
        "--output", "-o",
        type=Path,
        default=Path("sirecepde_test.xml"),
        help="Archivo de salida (default: sirecepde_test.xml)"
    )
    parser.add_argument(
        "--did",
        type=str,
        default="1",
        help="Identificador de control de envío (default: 1)"
    )
    
    args = parser.parse_args()
    
    # Leer DE crudo
    de_path = Path(args.de)
    if not de_path.exists():
        print(f"❌ Error: Archivo DE no encontrado: {de_path}")
        return 1
    
    de_content = de_path.read_text(encoding="utf-8")
    
    # Generar siRecepDE
    sirecepde_xml = build_sirecepde_xml(de_content, d_id=args.did)
    
    # Escribir archivo (asegurando que comienza con <?xml sin espacios)
    output_path = Path(args.output)
    output_path.write_bytes(sirecepde_xml.encode('utf-8'))
    
    print(f"✅ siRecepDE generado: {output_path}")
    print(f"   DE fuente: {de_path}")
    print(f"   dId: {args.did}")
    print(f"   Validar con: python -m tools.validate_xsd --schema sirecepde {output_path}")
    
    # Verificar que comienza correctamente
    first_bytes = output_path.read_bytes()[:50]
    if not first_bytes.startswith(b'<?xml'):
        print(f"   ⚠️  Advertencia: El archivo no comienza con <?xml")
    
    return 0


if __name__ == "__main__":
    sys.exit(main())
