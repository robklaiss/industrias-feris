#!/usr/bin/env python3
"""
Extrae el último DE/rDE enviado en un ZIP para validación con Prevalidador de SIFEN.

Busca el ZIP más reciente, extrae XMLs, identifica rDE/DE, hace validaciones locales
y guarda archivos listos para subir al Prevalidador.
"""
import sys
import re
import zipfile
from pathlib import Path
from typing import Optional, Tuple, List, Dict
from datetime import datetime
from io import BytesIO

# Agregar el directorio padre al path para imports
sys.path.insert(0, str(Path(__file__).parent.parent))

try:
    from lxml import etree
except ImportError:
    print("❌ ERROR: lxml no está disponible. Ejecutar: scripts/bootstrap_env.sh")
    sys.exit(1)


def find_latest_zip() -> Optional[Path]:
    """
    Busca el ZIP más reciente en rutas comunes de artifacts.
    
    Returns:
        Path al ZIP más reciente, o None si no se encuentra ninguno
    """
    search_paths = [
        Path("artifacts"),
        Path("tools/artifacts"),
        Path("web/artifacts"),
    ]
    
    # También buscar en subdirectorios de artifacts
    artifacts_dirs = []
    for base_path in search_paths:
        if base_path.exists() and base_path.is_dir():
            artifacts_dirs.append(base_path)
            # Buscar subdirectorios
            for subdir in base_path.iterdir():
                if subdir.is_dir() and "artifact" in subdir.name.lower():
                    artifacts_dirs.append(subdir)
    
    all_zips = []
    for artifacts_dir in artifacts_dirs:
        if artifacts_dir.exists():
            all_zips.extend(artifacts_dir.glob("*.zip"))
    
    if not all_zips:
        return None
    
    # Ordenar por mtime (más reciente primero)
    all_zips.sort(key=lambda p: p.stat().st_mtime, reverse=True)
    return all_zips[0]


def detect_root_localname(xml_bytes: bytes) -> Optional[str]:
    """
    Detecta el localname del root del XML sin parsear completamente.
    
    Returns:
        Localname del root (ej: "rDE", "DE") o None si falla
    """
    try:
        # Parsear solo para obtener el root
        parser = etree.XMLParser(recover=False, remove_blank_text=False)
        root = etree.fromstring(xml_bytes, parser)
        if isinstance(root.tag, str):
            if "}" in root.tag:
                return root.tag.split("}", 1)[1]
            return root.tag
    except Exception:
        pass
    return None


def extract_xmls(zip_path: Path) -> Tuple[List[Path], Optional[Path], Optional[Path]]:
    """
    Extrae todos los XMLs del ZIP a una carpeta temporal.
    
    Returns:
        (lista de paths extraídos, path al rDE si existe, path al DE si existe)
    """
    extract_dir = Path("artifacts/_extract_last_zip")
    extract_dir.mkdir(parents=True, exist_ok=True)
    
    # Limpiar extracciones anteriores
    for old_file in extract_dir.glob("*.xml"):
        old_file.unlink()
    
    extracted_paths = []
    rde_path = None
    de_path = None
    
    try:
        with zipfile.ZipFile(zip_path, "r") as zf:
            namelist = zf.namelist()
            print(f"📦 ZIP contiene {len(namelist)} archivo(s): {namelist}")
            
            for name in namelist:
                if name.endswith(".xml") or name.endswith(".XML"):
                    # Extraer
                    content = zf.read(name)
                    output_path = extract_dir / Path(name).name
                    output_path.write_bytes(content)
                    extracted_paths.append(output_path)
                    
                    # Detectar tipo
                    root_localname = detect_root_localname(content)
                    if root_localname == "rDE" and rde_path is None:
                        rde_path = output_path
                        print(f"   ✅ Detectado rDE: {name}")
                    elif root_localname == "DE" and de_path is None:
                        de_path = output_path
                        print(f"   ✅ Detectado DE: {name}")
                    elif root_localname:
                        print(f"   ℹ️  {name} tiene root: {root_localname}")
    except Exception as e:
        print(f"⚠️  Error al extraer ZIP: {e}")
    
    return extracted_paths, rde_path, de_path


def sanity_checks(xml_bytes: bytes) -> Dict[str, any]:
    """
    Realiza validaciones de sanidad sobre los bytes del XML.
    
    Returns:
        Dict con reporte de validaciones
    """
    report = {
        "has_bom": False,
        "invalid_control_chars": [],
        "suspicious_sequences": [],
        "well_formed": False,
        "parse_error": None,
    }
    
    # 1. Verificar BOM UTF-8
    if xml_bytes.startswith(b"\xef\xbb\xbf"):
        report["has_bom"] = True
    
    # 2. Buscar caracteres de control inválidos en XML 1.0
    # Prohibidos: 0x00-0x08, 0x0B, 0x0C, 0x0E-0x1F (excepto 0x09, 0x0A, 0x0D que son válidos)
    invalid_ranges = [
        (0x00, 0x08),  # NULL a BS
        (0x0B, 0x0B),  # VT
        (0x0C, 0x0C),  # FF
        (0x0E, 0x1F),  # SO a US
    ]
    
    for i, byte_val in enumerate(xml_bytes):
        for start, end in invalid_ranges:
            if start <= byte_val <= end:
                report["invalid_control_chars"].append({
                    "position": i,
                    "byte": f"0x{byte_val:02x}",
                    "char": repr(chr(byte_val)) if byte_val < 0x80 else f"\\x{byte_val:02x}",
                })
    
    # 3. Buscar secuencias sospechosas de entidades mal formadas
    # Buscar "&" seguido de algo que no sea "&amp;", "&lt;", "&gt;", "&quot;", "&apos;" o "&#" o "&x"
    text = xml_bytes.decode("utf-8", errors="replace")
    for match in re.finditer(r"&(?!amp;|lt;|gt;|quot;|apos;|#\d+|#x[0-9a-fA-F]+;)", text):
        report["suspicious_sequences"].append({
            "position": match.start(),
            "sequence": text[match.start():match.start()+20],  # Primeros 20 chars
        })
    
    # 4. Intentar parsear para verificar well-formed
    try:
        parser = etree.XMLParser(recover=False, remove_blank_text=False)
        etree.fromstring(xml_bytes, parser)
        report["well_formed"] = True
    except etree.XMLSyntaxError as e:
        report["parse_error"] = {
            "message": str(e),
            "line": getattr(e, "lineno", None),
            "column": getattr(e, "column", None),
        }
    except Exception as e:
        report["parse_error"] = {
            "message": str(e),
            "type": type(e).__name__,
        }
    
    return report


def write_outputs(xml_path: Path, root_type: str, artifacts_dir: Path) -> Path:
    """
    Escribe el XML limpio para el Prevalidador.
    
    Args:
        xml_path: Path al XML extraído
        root_type: "rDE" o "DE"
        artifacts_dir: Directorio de artifacts
        
    Returns:
        Path al archivo generado
    """
    xml_bytes = xml_path.read_bytes()
    
    # Parsear y re-serializar para asegurar formato limpio
    try:
        parser = etree.XMLParser(remove_blank_text=False, recover=False)
        root = etree.fromstring(xml_bytes, parser)
        
        # Guardar versión limpia (sin pretty_print para mantener espacios)
        output_path = artifacts_dir / f"prevalidator_input_{root_type}.xml"
        output_bytes = etree.tostring(
            root,
            encoding="utf-8",
            xml_declaration=True,
            pretty_print=False,
        )
        output_path.write_bytes(output_bytes)
        
        # Guardar versión pretty solo para lectura
        pretty_path = artifacts_dir / "prevalidator_pretty.xml"
        pretty_bytes = etree.tostring(
            root,
            encoding="utf-8",
            xml_declaration=True,
            pretty_print=True,
        )
        pretty_path.write_bytes(pretty_bytes)
        
        return output_path
    except Exception as e:
        # Si no se puede parsear, guardar crudo
        raw_path = artifacts_dir / "prevalidator_raw.xml"
        raw_path.write_bytes(xml_bytes)
        
        error_path = artifacts_dir / "prevalidator_parse_error.txt"
        error_path.write_text(
            f"Error al parsear XML:\n{type(e).__name__}: {e}\n\n"
            f"XML crudo guardado en: {raw_path}",
            encoding="utf-8"
        )
        return raw_path


def generate_sanity_report(xml_bytes: bytes, artifacts_dir: Path) -> Path:
    """
    Genera reporte de validaciones de sanidad.
    
    Returns:
        Path al archivo de reporte generado
    """
    report = sanity_checks(xml_bytes)
    report_path = artifacts_dir / "prevalidator_sanity_report.txt"
    
    lines = [
        "=== REPORTE DE VALIDACIÓN LOCAL ===",
        f"Generado: {datetime.now().isoformat()}",
        "",
        "1. BOM UTF-8:",
        f"   {'✅ NO tiene BOM' if not report['has_bom'] else '⚠️  TIENE BOM (debería removerse)'}",
        "",
        "2. Caracteres de control inválidos:",
    ]
    
    if report["invalid_control_chars"]:
        lines.append(f"   ⚠️  Encontrados {len(report['invalid_control_chars'])} caracteres inválidos:")
        for item in report["invalid_control_chars"][:10]:  # Primeros 10
            lines.append(f"      Posición {item['position']}: {item['byte']} ({item['char']})")
        if len(report["invalid_control_chars"]) > 10:
            lines.append(f"      ... y {len(report['invalid_control_chars']) - 10} más")
    else:
        lines.append("   ✅ No se encontraron caracteres de control inválidos")
    
    lines.extend([
        "",
        "3. Secuencias sospechosas (entidades mal formadas):",
    ])
    
    if report["suspicious_sequences"]:
        lines.append(f"   ⚠️  Encontradas {len(report['suspicious_sequences'])} secuencias sospechosas:")
        for item in report["suspicious_sequences"][:10]:  # Primeros 10
            lines.append(f"      Posición {item['position']}: {item['sequence']!r}")
        if len(report["suspicious_sequences"]) > 10:
            lines.append(f"      ... y {len(report['suspicious_sequences']) - 10} más")
    else:
        lines.append("   ✅ No se encontraron secuencias sospechosas")
    
    lines.extend([
        "",
        "4. Well-formed XML:",
    ])
    
    if report["well_formed"]:
        lines.append("   ✅ XML es well-formed")
    else:
        lines.append("   ❌ XML NO es well-formed")
        if report["parse_error"]:
            error = report["parse_error"]
            lines.append(f"   Error: {error.get('message', 'Desconocido')}")
            if error.get("line"):
                lines.append(f"   Línea: {error['line']}")
            if error.get("column"):
                lines.append(f"   Columna: {error['column']}")
    
    report_path.write_text("\n".join(lines), encoding="utf-8")
    return report_path


def check_sifen_response(artifacts_dir: Path) -> Optional[Dict[str, str]]:
    """
    Busca respuesta de SIFEN y extrae dCodRes/dMsgRes si existe.
    
    Returns:
        Dict con dCodRes y dMsgRes, o None si no se encuentra
    """
    response_files = [
        artifacts_dir / "soap_last_response.xml",
        artifacts_dir / "consulta_lote_*.xml",
    ]
    
    for pattern in response_files:
        if "*" in str(pattern):
            # Buscar más reciente
            matches = list(artifacts_dir.glob(pattern.name))
            if matches:
                matches.sort(key=lambda p: p.stat().st_mtime, reverse=True)
                pattern = matches[0]
            else:
                continue
        
        if pattern.exists():
            try:
                content = pattern.read_bytes()
                root = etree.fromstring(content)
                
                # Buscar dCodRes y dMsgRes
                dcodres = None
                dmsgres = None
                
                for elem in root.iter():
                    localname = elem.tag.split("}", 1)[1] if "}" in elem.tag else elem.tag
                    if localname == "dCodRes" and elem.text:
                        dcodres = elem.text
                    elif localname == "dMsgRes" and elem.text:
                        dmsgres = elem.text
                
                if dcodres or dmsgres:
                    return {
                        "dCodRes": dcodres or "N/A",
                        "dMsgRes": dmsgres or "N/A",
                        "source": pattern.name,
                    }
            except Exception:
                pass
    
    return None


def main():
    artifacts_dir = Path("artifacts")
    artifacts_dir.mkdir(parents=True, exist_ok=True)
    
    print("🔍 Buscando ZIP más reciente...")
    zip_path = find_latest_zip()
    
    if not zip_path:
        print("❌ No se encontró ningún archivo ZIP en artifacts/")
        print("   Asegúrate de haber enviado un lote recientemente.")
        return 1
    
    print(f"✅ ZIP encontrado: {zip_path}")
    print(f"   Modificado: {datetime.fromtimestamp(zip_path.stat().st_mtime).isoformat()}")
    
    print("\n📂 Extrayendo XMLs del ZIP...")
    extracted_paths, rde_path, de_path = extract_xmls(zip_path)
    
    if not extracted_paths:
        print("❌ No se encontraron archivos XML en el ZIP")
        return 1
    
    print(f"✅ Extraídos {len(extracted_paths)} archivo(s) XML")
    
    # Procesar rDE o DE
    output_paths = []
    
    if rde_path:
        print(f"\n📝 Procesando rDE: {rde_path.name}")
        xml_bytes = rde_path.read_bytes()
        output_path = write_outputs(rde_path, "rDE", artifacts_dir)
        output_paths.append(("rDE", output_path))
        
        # Validaciones
        print("🔍 Ejecutando validaciones locales...")
        generate_sanity_report(xml_bytes, artifacts_dir)
        print("✅ Reporte de validación guardado")
    
    if de_path and not rde_path:  # Solo si no hay rDE
        print(f"\n📝 Procesando DE: {de_path.name}")
        xml_bytes = de_path.read_bytes()
        output_path = write_outputs(de_path, "DE", artifacts_dir)
        output_paths.append(("DE", output_path))
        
        # Validaciones
        print("🔍 Ejecutando validaciones locales...")
        generate_sanity_report(xml_bytes, artifacts_dir)
        print("✅ Reporte de validación guardado")
    
    if not output_paths:
        print("⚠️  No se encontró rDE ni DE en el ZIP")
        print(f"   Archivos extraídos: {[p.name for p in extracted_paths]}")
        return 1
    
    # Verificar respuesta de SIFEN
    print("\n🔍 Buscando respuesta de SIFEN...")
    sifen_response = check_sifen_response(artifacts_dir)
    if sifen_response:
        print(f"✅ Respuesta encontrada en {sifen_response['source']}:")
        print(f"   dCodRes: {sifen_response['dCodRes']}")
        print(f"   dMsgRes: {sifen_response['dMsgRes']}")
    
    # Salida final
    print("\n" + "=" * 60)
    print("✅ ARCHIVOS GENERADOS:")
    print("=" * 60)
    for root_type, path in output_paths:
        print(f"   📄 {path}")
    print(f"   📄 {artifacts_dir / 'prevalidator_sanity_report.txt'}")
    if (artifacts_dir / "prevalidator_pretty.xml").exists():
        print(f"   📄 {artifacts_dir / 'prevalidator_pretty.xml'} (solo lectura)")
    
    print("\n" + "=" * 60)
    print("📋 NEXT STEP:")
    print("=" * 60)
    main_output = output_paths[0][1]
    print(f"Subí {main_output} al Prevalidador de SIFEN y copiá el error exacto.")
    
    return 0


if __name__ == "__main__":
    sys.exit(main())

