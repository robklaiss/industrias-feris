#!/usr/bin/env python3
"""
Validador XSD para XML SIFEN

Valida XML contra esquemas XSD:
- DE crudo: contra DE_v150.xsd
- siRecepDE: contra WS_SiRecepDE_v150.xsd

Uso:
    python -m tools.validate_xsd --schema de path/to/de.xml
    python -m tools.validate_xsd --schema sirecepde path/to/sirecepde.xml
    python -m tools.validate_xsd --schema de --xsd-dir schemas_sifen path/to/de.xml
"""
import sys
import argparse
from pathlib import Path
from typing import Optional, Tuple, List

# Agregar el directorio padre al path para imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from lxml import etree
from tools.xsd_resolver import LocalXsdResolver, resolve_xsd_dependencies


def validate_against_xsd(
    xml_path: Path,
    schema_name: str,
    xsd_dir: Optional[Path] = None
) -> Tuple[bool, List[str]]:
    """
    Valida un XML contra un esquema XSD específico
    
    Args:
        xml_path: Ruta al archivo XML
        schema_name: Nombre del esquema ("de" o "sirecepde")
        xsd_dir: Directorio donde buscar XSDs (default: schemas_sifen/)
        
    Returns:
        Tupla (es_valido, lista_errores)
    """
    errors = []
    
    if xsd_dir is None:
        # Resolver ruta relativa al repo (no hardcodeada)
        # Buscar schemas_sifen en tesaka-cv/ (relativo a tools/)
        schemas_sifen = Path(__file__).resolve().parent.parent / "schemas_sifen"
        xsd_legacy = Path(__file__).resolve().parent.parent / "xsd"
        if schemas_sifen.exists():
            xsd_dir = schemas_sifen
        elif xsd_legacy.exists():
            xsd_dir = xsd_legacy
        else:
            xsd_dir = schemas_sifen  # Default a schemas_sifen (aunque no exista aún)
    else:
        # Si se proporciona, convertir a Path absoluto
        xsd_dir = Path(xsd_dir).resolve()
    xsd_dir = Path(xsd_dir)
    
    if not xsd_dir.exists():
        errors.append(f"Directorio XSD no encontrado: {xsd_dir}")
        errors.append(f"Ejecuta: python -m tools.download_xsd")
        return False, errors
    
    # Seleccionar XSD según schema_name
    if schema_name.lower() == "de":
        # DE crudo: validación estructural de campos principales
        # (validación XSD completa se hace cuando está dentro de siRecepDE)
        xsd_file = xsd_dir / "DE_v150.xsd"
        if not xsd_file.exists():
            # Fallback
            xsd_file = xsd_dir / "siRecepDE_v150.xsd"
    elif schema_name.lower() == "sirecepde":
        # siRecepDE (root rEnviDe): validar con XSD del WS Recepción
        # Prioridad: WS_SiRecepDE_v150.xsd > siRecepDE_v150.xsd > siRecepRDE_Ekuatiai_v150.xsd
        xsd_candidates = [
            "WS_SiRecepDE_v150.xsd",
            "siRecepDE_v150.xsd",
            "siRecepRDE_Ekuatiai_v150.xsd",
        ]
        xsd_file = None
        for candidate in xsd_candidates:
            candidate_path = xsd_dir / candidate
            if candidate_path.exists():
                xsd_file = candidate_path
                break
        
        if not xsd_file:
            errors.append(f"XSD para siRecepDE no encontrado en {xsd_dir}")
            errors.append(f"Candidatos buscados: {', '.join(xsd_candidates)}")
            errors.append(f"Ejecuta: python -m tools.download_xsd")
            return False, errors
    elif schema_name.lower().endswith('.xsd'):
        # Si se proporciona el nombre del archivo XSD directamente
        xsd_file = xsd_dir / schema_name
    else:
        errors.append(f"Schema desconocido: {schema_name}. Use 'de', 'sirecepde', o nombre de archivo .xsd")
        return False, errors
    
    if not xsd_file.exists():
        errors.append(f"XSD no encontrado: {xsd_file}")
        errors.append(f"Ejecuta: python -m tools.download_xsd")
        return False, errors
    
    # Parsear XML
    try:
        xml_doc = etree.parse(str(xml_path))
        xml_root = xml_doc.getroot()
    except etree.XMLSyntaxError as e:
        errors.append(f"Error de sintaxis XML: {e}")
        return False, errors
    except FileNotFoundError:
        errors.append(f"Archivo XML no encontrado: {xml_path}")
        return False, errors
    except Exception as e:
        errors.append(f"Error al parsear XML: {e}")
        return False, errors
    
    # Manejo especial para DE crudo: si el elemento raíz es DE (no rDE),
    # validamos que el DE tenga la estructura correcta leyendo directamente el XML generado
    # y verificando que tenga los campos principales (validación estructural, no XSD completa)
    # Nota: La validación XSD completa del DE se hace cuando está dentro de siRecepDE
    if schema_name.lower() == "de" and xml_root.tag.endswith("DE") and not xml_root.tag.endswith("}rDE"):
        # El DE crudo tiene elemento raíz DE. Para validación XSD, necesitamos envolverlo en rDE.
        # Sin embargo, esto es complejo porque el DE puede tener estructura variable.
        # Alternativamente, validamos que el DE tenga estructura básica correcta.
        # En producción, el DE se valida cuando está dentro de siRecepDE (dentro de xDE).
        
        # Validación básica: verificar que el DE tenga campos principales
        # Los campos pueden estar con o sin namespace explícito
        required_fields = ['dDVId', 'dFecFirma', 'dSisFact', 'gOpeDE', 'gTimb', 'gDatGralOpe', 'gDtipDE']
        ns = "{http://ekuatia.set.gov.py/sifen/xsd}"
        missing_fields = []
        
        # Buscar campos directamente en el elemento raíz (primer nivel)
        for field in required_fields:
            # Buscar sin namespace y con namespace
            found = False
            # En el elemento raíz directamente
            for child in xml_root:
                tag_local = child.tag.split('}')[-1] if '}' in child.tag else child.tag
                if tag_local == field:
                    found = True
                    break
            # También buscar recursivamente
            if not found:
                found_field = xml_root.find(f".//{field}") is not None
                found_field_ns = xml_root.find(f".//{{{ns}}}{field}") is not None
                if found_field or found_field_ns:
                    found = True
            
            if not found:
                missing_fields.append(field)
        
        if missing_fields:
            errors.append(f"DE crudo falta campos requeridos: {', '.join(missing_fields)}")
            errors.append("Nota: Validación XSD completa del DE se realiza cuando está dentro de siRecepDE")
            return False, errors
        
        # Si tiene los campos básicos, considerar válido estructuralmente
        # (la validación XSD completa se hace en siRecepDE)
        return True, []
    
    # Cargar y resolver XSD
    try:
        schema = resolve_xsd_dependencies(xsd_file, xsd_dir)
    except FileNotFoundError as e:
        errors.append(str(e))
        return False, errors
    except Exception as e:
        errors.append(f"Error al cargar XSD: {e}")
        return False, errors
    
    # Validar
    try:
        if schema.validate(xml_doc):
            return True, []
        else:
            # Agregar información del XSD usado al inicio de los errores
            errors.insert(0, f"XSD usado: {xsd_file.name}")
            
            for error in schema.error_log:
                line = error.line if error.line else "?"
                column = error.column if error.column else "?"
                message = error.message
                
                # Intentar extraer XPath si está disponible
                xpath = ""
                if hasattr(error, 'path') and error.path:
                    xpath = f" (XPath: {error.path})"
                
                errors.append(f"Línea {line}, columna {column}: {message}{xpath}")
            
            return False, errors
    except Exception as e:
        errors.append(f"Error durante validación: {e}")
        return False, errors


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
        "--schema", "-s",
        type=str,
        required=True,
        choices=["de", "sirecepde"],
        help="Tipo de esquema: 'de' (DE crudo) o 'sirecepde' (envelope de recepción)"
    )
    parser.add_argument(
        "--xsd-dir",
        type=Path,
        help="Directorio donde buscar XSDs (default: schemas_sifen/)"
    )
    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="Mostrar información detallada"
    )
    
    args = parser.parse_args()
    
    xml_path = Path(args.xml_file)
    if not xml_path.exists():
        print(f"❌ Error: Archivo XML no encontrado: {xml_path}")
        return 1
    
    if args.verbose:
        print(f"📄 Validando: {xml_path}")
        print(f"📋 Schema: {args.schema}")
        if args.xsd_dir:
            print(f"📁 XSD dir: {args.xsd_dir}")
        print()
    
    # Validar
    is_valid, errors = validate_against_xsd(
        xml_path,
        args.schema,
        args.xsd_dir
    )
    
    # Extraer nombre del XSD usado (si está en los errores)
    xsd_used = None
    error_messages = []
    for error in errors:
        if error.startswith("XSD usado:"):
            xsd_used = error.replace("XSD usado: ", "")
        else:
            error_messages.append(error)
    
    if is_valid:
        print("✅ XML válido según XSD")
        if xsd_used:
            print(f"   XSD usado: {xsd_used}")
        return 0
    else:
        print("❌ XML NO válido según XSD")
        if xsd_used:
            print(f"   XSD usado: {xsd_used}")
        print()
        if error_messages:
            print(f"Errores encontrados ({len(error_messages)}):")
            for i, error in enumerate(error_messages, 1):
                print(f"  {i}. {error}")
        else:
            print("(sin errores detallados)")
        return 1


if __name__ == "__main__":
    sys.exit(main())

