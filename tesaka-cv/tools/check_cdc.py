#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Script CLI para verificar y corregir CDC (Código de Control) SIFEN.

Uso:
    python -m tools.check_cdc 01045547378001001000000112025123011234567892
    python -m tools.check_cdc 01045547378001001000000112025123011234567892 --fix
    python -m tools.check_cdc de_test.xml
    python -m tools.check_cdc de_test.xml --fix
"""

import sys
from pathlib import Path

# Agregar el directorio padre al path para imports
sys.path.insert(0, str(Path(__file__).parent.parent))

# Importar módulo centralizado de DV
from tools.cdc_dv import calc_cdc_dv, is_cdc_valid, fix_cdc

# Función de compatibilidad para validate_cdc
def validate_cdc(cdc44: str):
    """Wrapper para compatibilidad con código existente."""
    if not cdc44 or not isinstance(cdc44, str):
        return (False, -1, -1)
    
    digits = ''.join(c for c in cdc44 if c.isdigit())
    if len(digits) != 44:
        return (False, -1, -1)
    
    base43 = digits[:43]
    dv_original = int(digits[43])
    
    try:
        dv_calculado = calc_cdc_dv(base43)
        es_valido = (dv_original == dv_calculado)
        return (es_valido, dv_original, dv_calculado)
    except Exception:
        return (False, dv_original, -1)


def extract_cdc_from_xml(xml_path: Path) -> str:
    """
    Extrae el atributo Id del elemento DE desde un archivo XML.
    
    Args:
        xml_path: Path al archivo XML
        
    Returns:
        CDC (string) extraído del atributo Id
        
    Raises:
        ValueError: Si no se encuentra el elemento DE o el atributo Id
    """
    try:
        from lxml import etree
    except ImportError:
        raise RuntimeError("lxml no está instalado. Instalá con: pip install lxml")
    
    try:
        tree = etree.parse(str(xml_path))
        root = tree.getroot()
        
        # Buscar elemento DE (puede estar en el root o dentro de rDE)
        de_elem = None
        
        # Si el root es DE, usarlo directamente
        if root.tag.endswith("}DE") or root.tag == "DE":
            de_elem = root
        else:
            # Buscar dentro del árbol
            ns = {"s": "http://ekuatia.set.gov.py/sifen/xsd"}
            de_candidates = root.xpath(".//s:DE", namespaces=ns)
            if not de_candidates:
                # Intentar sin namespace
                de_candidates = root.xpath(".//*[local-name()='DE']")
            
            if de_candidates:
                de_elem = de_candidates[0]
        
        if de_elem is None:
            raise ValueError(f"No se encontró elemento <DE> en el XML: {xml_path}")
        
        # Extraer atributo Id
        de_id = de_elem.get("Id")
        if not de_id:
            raise ValueError(f"El elemento <DE> no tiene atributo 'Id' en: {xml_path}")
        
        return str(de_id).strip()
    
    except etree.XMLSyntaxError as e:
        raise ValueError(f"Error al parsear XML {xml_path}: {e}")
    except Exception as e:
        raise ValueError(f"Error al extraer CDC del XML {xml_path}: {e}")


def main():
    """Función principal."""
    if len(sys.argv) < 2:
        print("Uso: python -m tools.check_cdc <CDC_44_digitos|archivo.xml> [--fix]")
        print("\nEjemplos:")
        print("  python -m tools.check_cdc 01045547378001001000000112025123011234567892")
        print("  python -m tools.check_cdc 01045547378001001000000112025123011234567892 --fix")
        print("  python -m tools.check_cdc de_test.xml")
        print("  python -m tools.check_cdc de_test.xml --fix")
        sys.exit(1)
    
    input_arg = sys.argv[1].strip()
    fix_mode = len(sys.argv) > 2 and sys.argv[2] == "--fix"
    
    # Determinar si es un archivo XML o un CDC directo
    xml_path = Path(input_arg)
    is_xml_file = xml_path.exists() and xml_path.suffix.lower() == ".xml"
    
    if is_xml_file:
        print(f"📄 Leyendo XML: {xml_path}")
        try:
            cdc_input = extract_cdc_from_xml(xml_path)
            print(f"📋 CDC extraído del XML: {cdc_input}")
        except Exception as e:
            print(f"❌ Error al extraer CDC del XML: {e}")
            sys.exit(1)
    else:
        cdc_input = input_arg
    
    # Validar y verificar CDC
    try:
        # Validar formato básico antes de validar DV
        if not cdc_input or not isinstance(cdc_input, str):
            print(f"❌ Error: CDC debe ser un string. Recibido: {cdc_input!r}")
            sys.exit(1)
        
        if len(cdc_input) != 44:
            print(f"❌ Error: CDC debe tener exactamente 44 dígitos. "
                  f"Recibido: {len(cdc_input)} caracteres en {cdc_input!r}")
            sys.exit(1)
        
        if not cdc_input.isdigit():
            print(f"❌ CDC inválido: contiene caracteres no numéricos")
            print(f"   CDC recibido: {cdc_input!r}")
            print(f"   El CDC debe ser exactamente 44 dígitos (0-9)")
            if fix_mode:
                print(f"\n⚠️  No se puede corregir un CDC con caracteres no numéricos.")
                print(f"   El CDC debe ser reconstruido desde los datos originales.")
            sys.exit(2)
        
        es_valido, dv_original, dv_calculado = validate_cdc(cdc_input)
        
        print(f"\nCDC original    : {cdc_input}")
        print(f"DV original    : {dv_original}")
        print(f"DV calculado   : {dv_calculado}")
        
        if es_valido:
            print("✅ CDC válido")
            sys.exit(0)
        else:
            print("❌ CDC inválido (DV incorrecto)")
            
            if fix_mode:
                cdc_corregido = fix_cdc(cdc_input)
                print(f"CDC corregido  : {cdc_corregido}")
                print(f"✅ CDC corregido")
                if is_xml_file:
                    print(f"\n💡 Nota: El XML no fue modificado. Solo se muestra el CDC corregido.")
                sys.exit(2)
            else:
                print("\n💡 Para corregir automáticamente, usa: --fix")
                sys.exit(2)
    
    except ValueError as e:
        print(f"❌ Error: {e}")
        sys.exit(1)
    except Exception as e:
        print(f"❌ Error inesperado: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()

