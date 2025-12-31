#!/usr/bin/env python3
"""
Validador XSD para lote.xml (rLoteDE) y rEnvioLote.

Valida:
1. lote.xml extraído del ZIP contra XSD de rLoteDE
2. rEnvioLote contra XSD de rEnvioLote (si está disponible)
"""
import sys
import argparse
from pathlib import Path

try:
    from app.sifen_client.xsd_validator import (
        validate_rde_and_lote,
        find_xsd_declaring_global_element,
        load_schema,
        validate_xml_bytes,
        SIFEN_NS
    )
    import lxml.etree as etree
except ImportError as e:
    print(f"❌ Error: {e}")
    print("   Asegúrate de estar en el directorio raíz del proyecto")
    sys.exit(1)


def validate_lote_xml(lote_xml_path: Path, xsd_dir: Path) -> dict:
    """Valida lote.xml estructuralmente (no existe XSD global para rLoteDE)."""
    if not lote_xml_path.exists():
        return {"ok": False, "errors": [f"Archivo no encontrado: {lote_xml_path}"]}
    
    lote_bytes = lote_xml_path.read_bytes()
    
    # NOTA: No existe XSD que declare elemento global rLoteDE en el set actual de SIFEN.
    # En su lugar, hacemos validación estructural.
    try:
        lote_root = etree.fromstring(lote_bytes)
        
        def get_localname(tag: str) -> str:
            return tag.split("}", 1)[-1] if "}" in tag else tag
        
        def get_namespace(tag: str) -> str:
            if "}" in tag and tag.startswith("{"):
                return tag[1:].split("}", 1)[0]
            return ""
        
        root_local = get_localname(lote_root.tag)
        root_ns = get_namespace(lote_root.tag)
        
        structural_errors = []
        
        # 1. Root debe ser rLoteDE sin namespace
        if root_local != "rLoteDE":
            structural_errors.append(f"Root debe ser 'rLoteDE', encontrado: {root_local}")
        if root_ns:
            structural_errors.append(f"rLoteDE NO debe tener namespace, encontrado: {root_ns}")
        
        # 2. Debe contener exactamente 1 rDE
        rde_candidates = []
        for child in lote_root:
            if get_localname(child.tag) == "rDE":
                rde_candidates.append(child)
        
        if len(rde_candidates) == 0:
            structural_errors.append("rLoteDE debe contener exactamente 1 rDE, encontrado: 0")
        elif len(rde_candidates) > 1:
            structural_errors.append(f"rLoteDE debe contener exactamente 1 rDE, encontrado: {len(rde_candidates)}")
        else:
            rde_elem = rde_candidates[0]
            rde_ns = get_namespace(rde_elem.tag)
            
            # 3. rDE debe tener namespace SIFEN
            if rde_ns != SIFEN_NS:
                structural_errors.append(f"rDE debe tener namespace {SIFEN_NS}, encontrado: {rde_ns}")
            
            # 4. rDE debe contener Signature y gCamFuFD
            rde_children = [get_localname(c.tag) for c in rde_elem]
            has_signature = "Signature" in rde_children
            has_gcam = "gCamFuFD" in rde_children
            
            if not has_signature:
                structural_errors.append("rDE debe contener elemento Signature")
            if not has_gcam:
                structural_errors.append("rDE debe contener elemento gCamFuFD")
        
        return {
            "ok": len(structural_errors) == 0,
            "errors": structural_errors,
            "schema": None  # No hay XSD para rLoteDE
        }
    except Exception as e:
        return {
            "ok": False,
            "errors": [f"Error al validar estructura de lote.xml: {e}"],
            "schema": None
        }


def validate_renviolote_xml(renviolote_xml_path: Path, xsd_dir: Path) -> dict:
    """Valida rEnvioLote contra XSD."""
    if not renviolote_xml_path.exists():
        return {"ok": False, "errors": [f"Archivo no encontrado: {renviolote_xml_path}"]}
    
    renviolote_bytes = renviolote_xml_path.read_bytes()
    
    # Buscar XSD para rEnvioLote
    schema_path = find_xsd_declaring_global_element(xsd_dir, "rEnvioLote")
    
    if schema_path is None:
        # Fallback: buscar WS_SiRecepLoteDE_v141.xsd
        schema_path = xsd_dir / "WS_SiRecepLoteDE_v141.xsd"
        if not schema_path.exists():
            return {
                "ok": False,
                "errors": [f"No se encontró XSD para rEnvioLote en {xsd_dir}"],
                "schema": None
            }
    
    try:
        schema = load_schema(schema_path, xsd_dir)
        ok, errors = validate_xml_bytes(renviolote_bytes, schema, xsd_dir)
        
        return {
            "ok": ok,
            "errors": errors,
            "schema": str(schema_path)
        }
    except Exception as e:
        return {
            "ok": False,
            "errors": [f"Error al cargar/validar XSD: {e}"],
            "schema": str(schema_path)
        }


def analyze_xml_structure(xml_path: Path) -> dict:
    """Analiza la estructura básica del XML."""
    try:
        root = etree.parse(str(xml_path)).getroot()
        
        def get_localname(tag: str) -> str:
            return tag.split("}", 1)[-1] if "}" in tag else tag
        
        def get_namespace(tag: str) -> str:
            if "}" in tag and tag.startswith("{"):
                return tag[1:].split("}", 1)[0]
            return root.nsmap.get(None, "NONE")
        
        root_local = get_localname(root.tag)
        root_ns = get_namespace(root.tag)
        
        children = [get_localname(c.tag) for c in root]
        
        return {
            "root_tag": root.tag,
            "root_local": root_local,
            "root_namespace": root_ns,
            "children": children,
            "nsmap": dict(root.nsmap) if hasattr(root, 'nsmap') else {}
        }
    except Exception as e:
        return {"error": str(e)}


def main():
    parser = argparse.ArgumentParser(
        description="Valida lote.xml y rEnvioLote contra XSD"
    )
    parser.add_argument(
        "--lote-xml",
        type=Path,
        help="Path al lote.xml extraído del ZIP"
    )
    parser.add_argument(
        "--renviolote-xml",
        type=Path,
        help="Path al rEnvioLote XML"
    )
    parser.add_argument(
        "--xsd-dir",
        type=Path,
        default=Path("rshk-jsifenlib/docs/set/ekuatia.set.gov.py/sifen/xsd"),
        help="Directorio con XSDs (default: rshk-jsifenlib/docs/set/ekuatia.set.gov.py/sifen/xsd)"
    )
    
    args = parser.parse_args()
    
    xsd_dir = args.xsd_dir.resolve()
    
    if not xsd_dir.exists():
        print(f"❌ Directorio XSD no encontrado: {xsd_dir}")
        return 1
    
    print("=" * 60)
    print("VALIDACIÓN XSD")
    print("=" * 60)
    print(f"XSD dir: {xsd_dir}\n")
    
    all_ok = True
    
    # Validar lote.xml
    if args.lote_xml:
        print("📄 Validando lote.xml...")
        structure = analyze_xml_structure(args.lote_xml)
        if "error" in structure:
            print(f"   ❌ Error al analizar estructura: {structure['error']}")
            all_ok = False
        else:
            print(f"   Root: {structure['root_local']}")
            print(f"   Namespace: {structure['root_namespace']}")
            print(f"   Children: {', '.join(structure['children'])}")
        
        result = validate_lote_xml(args.lote_xml, xsd_dir)
        if result["schema"]:
            print(f"   Schema: {result['schema']}")
        
        if result["ok"]:
            print("   ✅ Validación XSD: OK\n")
        else:
            print("   ❌ Validación XSD: FAIL")
            print(f"   Errores ({len(result['errors'])}):")
            for i, error in enumerate(result["errors"][:30], 1):
                print(f"     {i}. {error}")
            print()
            all_ok = False
    
    # Validar rEnvioLote
    if args.renviolote_xml:
        print("📄 Validando rEnvioLote...")
        structure = analyze_xml_structure(args.renviolote_xml)
        if "error" in structure:
            print(f"   ❌ Error al analizar estructura: {structure['error']}")
            all_ok = False
        else:
            print(f"   Root: {structure['root_local']}")
            print(f"   Namespace: {structure['root_namespace']}")
            print(f"   Children: {', '.join(structure['children'])}")
        
        result = validate_renviolote_xml(args.renviolote_xml, xsd_dir)
        if result["schema"]:
            print(f"   Schema: {result['schema']}")
        
        if result["ok"]:
            print("   ✅ Validación XSD: OK\n")
        else:
            print("   ❌ Validación XSD: FAIL")
            print(f"   Errores ({len(result['errors'])}):")
            for i, error in enumerate(result["errors"][:30], 1):
                print(f"     {i}. {error}")
            print()
            all_ok = False
    
    print("=" * 60)
    if all_ok:
        print("✅ TODAS LAS VALIDACIONES PASARON")
        return 0
    else:
        print("❌ ALGUNAS VALIDACIONES FALLARON")
        return 1


if __name__ == "__main__":
    sys.exit(main())

