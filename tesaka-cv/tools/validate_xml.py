#!/usr/bin/env python3
"""
Validador de XML contra esquemas XSD de SIFEN

Uso:
    python -m tools.validate_xml <archivo.xml>
    python -m tools.validate_xml <archivo.xml> --prevalidate

Opciones:
    --prevalidate     También prevalida usando el servicio SIFEN (si está disponible)
    --xsd <path>      Especificar ruta al XSD principal (por defecto busca DE_v150.xsd)
"""
import sys
import argparse
from pathlib import Path
from typing import Optional, List, Tuple
from xml.etree import ElementTree as ET
from lxml import etree

# Agregar el directorio padre al path para imports
sys.path.insert(0, str(Path(__file__).parent.parent))


def find_main_xsd(xsd_dir: Path, xml_path: Optional[Path] = None) -> Optional[Path]:
    """
    Busca el XSD principal según el elemento raíz del XML
    
    Args:
        xsd_dir: Directorio donde buscar XSD
        xml_path: Path al XML para detectar elemento raíz (opcional)
        
    Returns:
        Path al XSD principal o None
    """
    if not xsd_dir.exists():
        return None
    
    # Si se proporciona XML, detectar elemento raíz
    if xml_path and xml_path.exists():
        try:
            from lxml import etree
            xml_doc = etree.parse(str(xml_path))
            root = xml_doc.getroot()
            root_tag = root.tag
            
            # Extraer localname (sin namespace)
            localname = root_tag.split('}')[-1] if '}' in root_tag else root_tag
            
            # Si el elemento raíz es rEnviDe, usar XSD del WS Recepción
            if localname == "rEnviDe":
                # Prioridad: WS_SiRecepDE_v150.xsd > siRecepDE_v150.xsd > siRecepRDE_Ekuatiai_v150.xsd
                patterns = [
                    "WS_SiRecepDE_v150.xsd",
                    "siRecepDE_v150.xsd",
                    "siRecepRDE_Ekuatiai_v150.xsd",
                ]
                for pattern in patterns:
                    xsd_file = xsd_dir / pattern
                    if xsd_file.exists():
                        return xsd_file
            # Si el elemento raíz es rDE, usar siRecepDE_v150.xsd
            elif localname == "rDE":
                patterns = [
                    "siRecepDE_v150.xsd",
                    "siRecepDE_v141.xsd",
                    "siRecepDE_v130.xsd",
                ]
                for pattern in patterns:
                    xsd_file = xsd_dir / pattern
                    if xsd_file.exists():
                        return xsd_file
            # Si el elemento raíz es DE (crudo), usar DE_v150.xsd
            elif localname == "DE":
                patterns = [
                    "DE_v150.xsd",
                    "DE_v141.xsd",
                ]
                for pattern in patterns:
                    xsd_file = xsd_dir / pattern
                    if xsd_file.exists():
                        return xsd_file
        except:
            pass
    
    # Prioridad: v150 > v130 > DE.xsd
    patterns = [
        "DE_v150.xsd",
        "DE_v1.5.0.xsd", 
        "DE_v130.xsd",
        "DE_v1.3.0.xsd",
        "DE.xsd",
    ]
    
    for pattern in patterns:
        xsd_file = xsd_dir / pattern
        if xsd_file.exists():
            return xsd_file
    
    # Buscar cualquier siRecepDE*.xsd primero, luego DE*.xsd
    recep_xsd_files = list(xsd_dir.glob("siRecepDE*.xsd"))
    if recep_xsd_files:
        return recep_xsd_files[0]
    
    de_xsd_files = list(xsd_dir.glob("DE*.xsd"))
    if de_xsd_files:
        return de_xsd_files[0]
    
    return None


def validate_against_xsd(xml_path: Path, xsd_path: Path, xsd_dir: Optional[Path] = None) -> Tuple[bool, List[str]]:
    """
    Valida un XML contra un esquema XSD resolviendo dependencias localmente
    
    Args:
        xml_path: Ruta al archivo XML
        xsd_path: Ruta al archivo XSD principal
        xsd_dir: Directorio donde buscar dependencias XSD (por defecto: directorio del XSD)
        
    Returns:
        Tupla (es_valido, lista_errores)
    """
    from .xsd_resolver import validate_xml_against_xsd as validate_with_resolver
    
    if xsd_dir is None:
        xsd_dir = xsd_path.parent
    
    return validate_with_resolver(xml_path, xsd_path, xsd_dir)


def validate_xml_structure(xml_path: Path) -> Tuple[bool, List[str]]:
    """
    Valida que el XML esté bien formado (sin XSD)
    
    Args:
        xml_path: Ruta al archivo XML
        
    Returns:
        Tupla (es_valido, lista_errores)
    """
    errors = []
    
    try:
        tree = ET.parse(str(xml_path))
        return True, []
    except ET.ParseError as e:
        errors.append(f"XML mal formado: {str(e)}")
        return False, errors
    except Exception as e:
        errors.append(f"Error: {str(e)}")
        return False, errors


def prevalidate_with_sifen(xml_path: Path) -> dict:
    """
    Prevalida XML usando el servicio SIFEN (si está disponible)
    
    Args:
        xml_path: Ruta al archivo XML
        
    Returns:
        Diccionario con resultado de prevalidación
    """
    try:
        from app.sifen_client.validator import SifenValidator
        from app.sifen_client.xml_utils import clean_xml
        
        xml_content = xml_path.read_text(encoding='utf-8')
        xml_clean = clean_xml(xml_content)
        
        validator = SifenValidator()
        result = validator.prevalidate_with_service(xml_clean)
        
        return result
    except Exception as e:
        return {
            "error": f"Error al contactar Prevalidador: {str(e)}",
            "valid": None
        }


def main():
    parser = argparse.ArgumentParser(
        description="Valida XML contra esquemas XSD de SIFEN"
    )
    parser.add_argument(
        "xml_file",
        type=Path,
        help="Archivo XML a validar"
    )
    parser.add_argument(
        "--xsd",
        type=Path,
        help="Ruta al archivo XSD principal (por defecto busca en xsd/)"
    )
    parser.add_argument(
        "--prevalidate",
        action="store_true",
        help="También prevalidar usando el servicio SIFEN"
    )
    parser.add_argument(
        "--xsd-dir",
        type=Path,
        default=None,  # Se resolverá automáticamente
        help="Directorio donde buscar XSD (default: schemas_sifen/)"
    )
    
    args = parser.parse_args()
    
    xml_path = args.xml_file
    
    if not xml_path.exists():
        print(f"❌ Error: Archivo no encontrado: {xml_path}")
        return 1
    
    print(f"📄 Validando: {xml_path.name}")
    print()
    
    # 1. Validar estructura XML básica
    print("1️⃣  Validando estructura XML...")
    is_well_formed, errors = validate_xml_structure(xml_path)
    
    if not is_well_formed:
        print("   ❌ XML mal formado:")
        for error in errors:
            print(f"      {error}")
        return 1
    
    print("   ✅ XML bien formado")
    print()
    
    # 2. Validar contra XSD
    print("2️⃣  Validando contra esquema XSD...")
    
    # Resolver directorio XSD (paths relativos)
    if args.xsd_dir is None:
        schemas_sifen = Path(__file__).resolve().parent.parent / "schemas_sifen"
        xsd_legacy = Path(__file__).resolve().parent.parent / "xsd"
        if schemas_sifen.exists():
            xsd_dir = schemas_sifen
        elif xsd_legacy.exists():
            xsd_dir = xsd_legacy
        else:
            xsd_dir = schemas_sifen  # Default
    else:
        xsd_dir = Path(args.xsd_dir).resolve()
    
    # Buscar XSD
    if args.xsd:
        xsd_path = args.xsd
        if not xsd_path.exists():
            print(f"   ❌ Error: XSD no encontrado: {xsd_path}")
            return 1
    else:
        xsd_path = find_main_xsd(xsd_dir, xml_path)
        if not xsd_path:
            print(f"   ⚠️  No se encontró XSD principal en {xsd_dir}")
            print(f"      Ejecuta: python -m tools.download_xsd")
            print(f"      O especifica XSD con --xsd <ruta>")
            return 1
    
    print(f"   📋 Usando XSD: {xsd_path.name}")
    print(f"   📁 Directorio XSD: {xsd_dir}")
    
    is_valid, errors = validate_against_xsd(xml_path, xsd_path, xsd_dir)
    
    if not is_valid:
        print("   ❌ XML no válido según XSD:")
        for error in errors[:10]:  # Limitar a 10 errores
            print(f"      {error}")
        if len(errors) > 10:
            print(f"      ... y {len(errors) - 10} error(es) más")
        print()
        return 1
    
    print("   ✅ XML válido según XSD")
    print()
    
    # 3. Prevalidar con SIFEN (opcional)
    if args.prevalidate:
        print("3️⃣  Prevalidando con servicio SIFEN...")
        result = prevalidate_with_sifen(xml_path)
        
        if result.get("valid") is True:
            print("   ✅ XML prevalidado correctamente por SIFEN")
        elif result.get("valid") is False:
            print("   ❌ XML rechazado por Prevalidador SIFEN:")
            if result.get("error"):
                print(f"      {result['error']}")
            if result.get("response"):
                print(f"      Respuesta: {str(result['response'])[:200]}")
        elif result.get("valid") is None:
            print("   ⚠️  No se pudo prevalidar (Prevalidador requiere uso manual)")
            if result.get("note"):
                print(f"      {result['note']}")
            print(f"      Usa: https://ekuatia.set.gov.py/prevalidador/validacion")
        else:
            print("   ⚠️  Resultado desconocido del Prevalidador")
        
        print()
    
    print("✅ Validación completa - XML es válido")
    return 0


if __name__ == "__main__":
    sys.exit(main())

