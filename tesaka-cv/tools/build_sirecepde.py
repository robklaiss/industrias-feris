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
from lxml import etree
import sys
import argparse
import xml.etree.ElementTree as ET
from pathlib import Path
from datetime import datetime
from typing import Optional
import re
import os

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
    d_id: str = "1",
    sign_p12_path: Optional[str] = None,
    sign_p12_password: Optional[str] = None
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
    # Firmar el DE si se proporciona certificado
    if sign_p12_path and sign_p12_password:
        try:
            from app.sifen_client.xmldsig_signer import sign_de_xml
            print(f"🔐 Firmando DE con certificado: {Path(sign_p12_path).name}")
            de_xml_content = sign_de_xml(de_xml_content, sign_p12_path, sign_p12_password)
            print("✓ DE firmado exitosamente")
        except Exception as e:
            raise ValueError(f"Error al firmar DE: {e}")
    
    # Remover declaración XML del DE para evitar conflicto
    de_without_declaration = strip_xml_declaration(de_xml_content)
    
    # Namespace: http://ekuatia.set.gov.py/sifen/xsd
    SIFEN_NS = "http://ekuatia.set.gov.py/sifen/xsd"
    XSI_NS = "http://www.w3.org/2001/XMLSchema-instance"
    
    # REGLA CRÍTICA SIFEN:
    # - El root (rEnviDe) NO debe tener xmlns:ds
    # - ds:Signature dentro del DE debe tener su propio default namespace
    # - Usar lxml para control completo del nsmap
    
    # Crear elemento raíz rEnviDe con lxml (nsmap sin ds)
    nsmap = {None: SIFEN_NS, "xsi": XSI_NS}
    root = etree.Element(f"{{{SIFEN_NS}}}rEnviDe", nsmap=nsmap)
    
    # dId: Identificador de control de envío
    d_id_elem = etree.SubElement(root, f"{{{SIFEN_NS}}}dId")
    d_id_elem.text = str(d_id)
    
    # xDE: XML del DE transmitido
    x_de_elem = etree.SubElement(root, f"{{{SIFEN_NS}}}xDE")
    
    # Parsear el DE y agregarlo como hijo de xDE
    try:
        # Parsear DE con lxml (preserva namespaces correctamente)
        # Agregar declaración XML temporalmente para parseo correcto
        de_with_decl = f'<?xml version="1.0" encoding="UTF-8"?>\n{de_without_declaration}'
        
        # Usar XMLParser con recover=True para manejar XMLs problemáticos
        parser = etree.XMLParser(recover=True, remove_blank_text=False, resolve_entities=False)
        de_root = etree.fromstring(de_with_decl.encode('utf-8'), parser=parser)
        
        # Agregar el DE completo como hijo de xDE
        # NO tocar la firma - debe mantener su default namespace
        x_de_elem.append(de_root)
            
    except etree.ParseError as e:
        raise ValueError(f"Error parseando DE: {e}")
    
    # Serializar a XML string con lxml (NO pretty_print para preservar firma)
    # IMPORTANTE: NO remover xmlns:ds del root porque rompe los prefijos ds: en Signature
    # El namespace ds DEBE estar declarado en algún ancestro de los elementos ds:*
    # SIFEN acepta xmlns:ds en el root, el problema era la DUPLICACIÓN
    xml_body = etree.tostring(root, encoding='unicode', xml_declaration=False, pretty_print=False)
    
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
        "--env",
        choices=["test", "prod"],
        default=None,
        help="Ambiente SIFEN (para validación de RUC)"
    )
    parser.add_argument(
        "--did",
        type=str,
        default="1",
        help="Identificador de control de envío (default: 1)"
    )
    parser.add_argument(
        "--sign-p12",
        type=Path,
        help="Ruta al certificado P12/PFX para firmar (default: SIFEN_SIGN_P12_PATH)"
    )
    parser.add_argument(
        "--sign-password",
        type=str,
        help="Contraseña del certificado (default: SIFEN_SIGN_P12_PASSWORD)"
    )
    
    args = parser.parse_args()
    
    # Resolver certificado de firma desde args o env vars
    sign_p12_path = str(args.sign_p12) if args.sign_p12 else os.getenv("SIFEN_SIGN_P12_PATH")
    sign_p12_password = args.sign_password or os.getenv("SIFEN_SIGN_P12_PASSWORD")
    
    # Leer DE crudo
    de_path = Path(args.de)
    if not de_path.exists():
        print(f"❌ Error: Archivo DE no encontrado: {de_path}")
        return 1
    
    de_content = de_path.read_text(encoding="utf-8")
    
    # Validar RUC del emisor antes de construir siRecepDE (evitar código 1264)
    try:
        from app.sifen_client.ruc_validator import validate_emisor_ruc
        from app.sifen_client.config import get_sifen_config
        
        # Obtener RUC esperado del config si está disponible
        env = args.env or os.getenv("SIFEN_ENV", "test")
        try:
            config = get_sifen_config(env=env)
            expected_ruc = os.getenv("SIFEN_EMISOR_RUC") or getattr(config, 'test_ruc', None)
        except:
            expected_ruc = os.getenv("SIFEN_EMISOR_RUC") or os.getenv("SIFEN_TEST_RUC")
        
        is_valid, error_msg = validate_emisor_ruc(de_content, expected_ruc=expected_ruc)
        
        if not is_valid:
            print(f"❌ Validación de RUC del emisor falló:")
            print(f"   {error_msg}")
            print(f"\n   Configure SIFEN_EMISOR_RUC con el RUC real del contribuyente habilitado (formato: RUC-DV, ej: 4554737-8).")
            return 1
        
        print("✓ RUC del emisor validado (no es dummy)")
    except ImportError:
        # Si no se puede importar el validador, continuar sin validación (no crítico)
        print("⚠️  No se pudo importar validador de RUC, continuando sin validación")
    except Exception as e:
        # Si falla la validación por otro motivo, continuar (no bloquear)
        print(f"⚠️  Error al validar RUC del emisor: {e}, continuando sin validación")
    
    # Generar siRecepDE (firmando si hay certificado)
    sirecepde_xml = build_sirecepde_xml(
        de_content, 
        d_id=args.did,
        sign_p12_path=sign_p12_path,
        sign_p12_password=sign_p12_password
    )
    
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
