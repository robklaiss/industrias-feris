#!/usr/bin/env python3
"""
Script para generar XML para prevalidador web SIFEN (sin firma).

Este script toma un XML firmado de SIFEN y genera una versión apta para
el prevalidador web:
- Elimina ds:Signature
- Elimina gCamFuFD (QR) para evitar rechazos falsos
- Valida localmente con schema preval
- Guarda en ~/Desktop/sifen_de_prevalidador.xml

Uso:
    python tools/sifen_make_prevalidador_xml.py <xml_firmado>
"""

import sys
import argparse
from pathlib import Path
from lxml import etree

# Importar funciones del validador local
sys.path.append(str(Path(__file__).parent))
from prevalidate_local_v150 import load_xml, strip_signature, build_schema, LocalXSDResolver

def remove_qr_code(tree: etree._ElementTree) -> int:
    """
    Elimina gCamFuFD (QR code) del XML para evitar rechazos en prevalidador.
    
    Returns:
        Número de elementos eliminados
    """
    qr_elements = tree.xpath(
        './/*[local-name()="gCamFuFD" and namespace-uri()="http://ekuatia.set.gov.py/sifen/xsd"]'
    )
    removed = 0
    for elem in qr_elements:
        parent = elem.getparent()
        if parent is not None:
            parent.remove(elem)
            removed += 1
    return removed

def validate_with_schema(tree: etree._ElementTree, xsd_dir: Path, schema_name: str) -> bool:
    """
    Valida el XML contra un schema específico.
    
    Returns:
        True si es válido, False si hay errores
    """
    try:
        schema = build_schema(xsd_dir, schema_name)
        schema.assertValid(tree)
        return True
    except etree.DocumentInvalid as e:
        print(f"❌ Error de validación XSD:")
        for error in e.error_log:
            print(f"   - Línea {error.line}: {error.message}")
        return False
    except Exception as e:
        print(f"❌ Error inesperado al validar: {e}")
        return False

def main():
    parser = argparse.ArgumentParser(
        description="Genera XML para prevalidador SIFEN (sin firma ni QR)"
    )
    parser.add_argument(
        "xml_path",
        type=Path,
        help="Path al XML firmado de entrada"
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("~/Desktop/sifen_de_prevalidador.xml").expanduser(),
        help="Path de salida (default: ~/Desktop/sifen_de_prevalidador.xml)"
    )
    parser.add_argument(
        "--xsd-dir",
        default="xsd",
        help="Directorio de XSDs (default: xsd)"
    )
    parser.add_argument(
        "--no-validate",
        action="store_true",
        help="Omitir validación local"
    )
    
    args = parser.parse_args()
    
    # Verificar entrada
    if not args.xml_path.exists():
        print(f"❌ Error: No existe el archivo {args.xml_path}")
        sys.exit(1)
    
    try:
        print("=== Generador XML para Prevalidador SIFEN ===")
        print(f"📂 Entrada: {args.xml_path}")
        print(f"📂 Salida: {args.output}")
        
        # Cargar XML
        tree = load_xml(args.xml_path)
        
        # Eliminar firma
        removed_sigs = strip_signature(tree)
        if removed_sigs > 0:
            print(f"✅ Eliminadas {removed_sigs} firmas ds:Signature")
        else:
            print("ℹ️  No se encontraron firmas para eliminar")
        
        # Eliminar QR code
        removed_qr = remove_qr_code(tree)
        if removed_qr > 0:
            print(f"✅ Eliminados {removed_qr} códigos QR (gCamFuFD)")
        else:
            print("ℹ️  No se encontraron códigos QR para eliminar")
        
        # Validar localmente (opcional)
        if not args.no_validate:
            print("\n🔍 Validando localmente con schema preval...")
            xsd_dir = Path(args.xsd_dir).expanduser()
            if validate_with_schema(tree, xsd_dir, "rDE_prevalidador_v150.xsd"):
                print("✅ VALID: El XML cumple con el schema prevalidador")
            else:
                print("❌ INVALID: El XML tiene errores de validación")
                sys.exit(1)
        else:
            print("⚠️  Omitida validación local (--no-validate)")
        
        # Guardar XML
        args.output.parent.mkdir(parents=True, exist_ok=True)
        
        # Serializar con pretty print
        xml_bytes = etree.tostring(
            tree.getroot(),
            xml_declaration=True,
            encoding="UTF-8",
            pretty_print=True,
            standalone=False
        )
        
        args.output.write_bytes(xml_bytes)
        print(f"\n✅ XML para prevalidador guardado en: {args.output}")
        print(f"📊 Tamaño: {len(xml_bytes)} bytes")
        
        print("\n🎯 Próximos pasos:")
        print("1) Subir a prevalidador SIFEN:")
        print("   https://ekuatia.set.gov.py/prevalidador/validacion")
        print(f"2) Archivo a subir: {args.output}")
        
    except Exception as e:
        print(f"❌ Error: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
