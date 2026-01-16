#!/usr/bin/env python3
"""
Valida XML SIFEN contra XSD local con autodiscovery.

Uso:
    python -m tools.validate_sifen_xml --xml artifacts/lote_built_<dId>.xml
    python -m tools.validate_sifen_xml --xml artifacts/rde_signed_<CDC>.xml

Exit code:
    0 si validación OK
    1 si validación falla o error
"""
import sys
import argparse
from pathlib import Path
from typing import List, Tuple, Optional

# Agregar el directorio padre al path para imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from lxml import etree


def find_xsd_files(base_dir: Path) -> List[Path]:
    """Busca todos los archivos XSD en el directorio base."""
    xsd_files = []
    for pattern in ["*.xsd", "**/*.xsd"]:
        xsd_files.extend(base_dir.glob(pattern))
    return sorted(set(xsd_files))


def autodiscover_xsd(xml_path: Path, xsd_dir: Path) -> Optional[Path]:
    """
    Autodescubre el XSD más apropiado para el XML dado.
    
    Estrategia:
    1. Parsear XML y obtener root element localname
    2. Buscar XSD que contenga element con ese nombre
    3. Priorizar XSD con nombres relevantes (DE, Lote, etc.)
    """
    try:
        xml_root = etree.parse(str(xml_path)).getroot()
        root_localname = xml_root.tag.split("}", 1)[-1] if "}" in xml_root.tag else xml_root.tag
        
        print(f"🔍 Root element: {root_localname}")
        print(f"🔍 Buscando XSD en: {xsd_dir}")
        
        xsd_files = find_xsd_files(xsd_dir)
        if not xsd_files:
            print(f"⚠️  No se encontraron archivos XSD en {xsd_dir}")
            return None
        
        print(f"🔍 Encontrados {len(xsd_files)} archivos XSD")
        
        # Estrategia 1: buscar XSD que contenga element name="<root_localname>"
        candidates = []
        for xsd_path in xsd_files:
            try:
                xsd_content = xsd_path.read_text(encoding="utf-8")
                if f'element name="{root_localname}"' in xsd_content:
                    candidates.append(xsd_path)
            except Exception:
                continue
        
        if candidates:
            # Priorizar por nombre de archivo relevante
            priority_keywords = ["DE_v", "Lote", "WS_SiRecep"]
            for keyword in priority_keywords:
                for candidate in candidates:
                    if keyword in candidate.name:
                        print(f"✅ XSD autodescubierto: {candidate.name}")
                        return candidate
            
            # Si no hay prioridad, usar el primero
            print(f"✅ XSD autodescubierto: {candidates[0].name}")
            return candidates[0]
        
        # Estrategia 2: buscar por nombre de archivo
        for xsd_path in xsd_files:
            if root_localname.lower() in xsd_path.name.lower():
                print(f"✅ XSD autodescubierto (por nombre): {xsd_path.name}")
                return xsd_path
        
        print(f"⚠️  No se pudo autodescubrir XSD para root element '{root_localname}'")
        return None
        
    except Exception as e:
        print(f"❌ Error al autodescubrir XSD: {e}")
        return None


def validate_xml_against_xsd(xml_path: Path, xsd_path: Path) -> Tuple[bool, List[str]]:
    """
    Valida XML contra XSD.
    
    Returns:
        Tupla (success, errors)
        - success: True si validación OK
        - errors: Lista de mensajes de error (vacía si success=True)
    """
    try:
        # Parsear XSD
        xsd_doc = etree.parse(str(xsd_path))
        schema = etree.XMLSchema(xsd_doc)
        
        # Parsear XML
        xml_doc = etree.parse(str(xml_path))
        
        # Validar
        is_valid = schema.validate(xml_doc)
        
        if is_valid:
            return (True, [])
        else:
            # Extraer errores
            errors = []
            for error in schema.error_log:
                errors.append(f"Línea {error.line}, Col {error.column}: {error.message}")
            return (False, errors)
            
    except etree.XMLSchemaParseError as e:
        return (False, [f"Error al parsear XSD: {e}"])
    except etree.XMLSyntaxError as e:
        return (False, [f"Error al parsear XML: {e}"])
    except Exception as e:
        return (False, [f"Error inesperado: {e}"])


def main():
    parser = argparse.ArgumentParser(
        description="Valida XML SIFEN contra XSD local con autodiscovery",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Ejemplos:
  python -m tools.validate_sifen_xml --xml artifacts/lote_built_20260113_041032.xml
  python -m tools.validate_sifen_xml --xml artifacts/rde_signed_01234567890123456789012345678901234567890123.xml
  python -m tools.validate_sifen_xml --xml artifacts/lote_built_20260113_041032.xml --xsd schemas_sifen/DE_v150.xsd
        """
    )
    
    parser.add_argument(
        "--xml",
        required=True,
        type=Path,
        help="Path al archivo XML a validar"
    )
    
    parser.add_argument(
        "--xsd",
        type=Path,
        default=None,
        help="Path al XSD (opcional, se autodescubre si no se especifica)"
    )
    
    parser.add_argument(
        "--xsd-dir",
        type=Path,
        default=None,
        help="Directorio donde buscar XSD (default: schemas_sifen/)"
    )
    
    args = parser.parse_args()
    
    # Validar que XML existe
    if not args.xml.exists():
        print(f"❌ Archivo XML no encontrado: {args.xml}")
        return 1
    
    # Determinar directorio XSD
    if args.xsd_dir:
        xsd_dir = args.xsd_dir
    else:
        # Buscar schemas_sifen/ relativo al script
        xsd_dir = Path(__file__).parent.parent / "schemas_sifen"
    
    if not xsd_dir.exists():
        print(f"❌ Directorio XSD no encontrado: {xsd_dir}")
        return 1
    
    # Determinar XSD a usar
    if args.xsd:
        xsd_path = args.xsd
        if not xsd_path.exists():
            print(f"❌ Archivo XSD no encontrado: {xsd_path}")
            return 1
        print(f"📄 Usando XSD especificado: {xsd_path.name}")
    else:
        # Autodescubrir XSD
        xsd_path = autodiscover_xsd(args.xml, xsd_dir)
        if not xsd_path:
            print(f"❌ No se pudo autodescubrir XSD para {args.xml.name}")
            print(f"   Especifica --xsd manualmente")
            return 1
    
    print(f"\n🔍 Validando {args.xml.name} contra {xsd_path.name}...")
    
    # Validar
    success, errors = validate_xml_against_xsd(args.xml, xsd_path)
    
    if success:
        print(f"✅ Validación exitosa: {args.xml.name} cumple con {xsd_path.name}")
        return 0
    else:
        print(f"❌ Validación fallida: {args.xml.name} NO cumple con {xsd_path.name}")
        print(f"\n📋 Errores encontrados ({len(errors)}):")
        for i, error in enumerate(errors[:20], 1):
            print(f"   {i}. {error}")
        if len(errors) > 20:
            print(f"   ... y {len(errors) - 20} errores más")
        return 1


if __name__ == "__main__":
    sys.exit(main())
