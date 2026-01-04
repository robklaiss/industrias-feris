#!/usr/bin/env python3
"""
Valida el contenido de xDE (ZIP con lote.xml) antes de enviar a SIFEN.

Extrae BASE64 → ZIP → lote.xml y valida:
1. XML well-formed (sin recover)
2. lote.xml contra XSD de lote
3. rDE interno contra XSD de DE

Uso:
    python -m tools.validate_outgoing_lote --debug-file artifacts/soap_last_http_debug.txt --xsd-dir <path>
"""
import sys
import os
import base64
import zipfile
import re
from pathlib import Path
from io import BytesIO
from typing import Optional, Tuple

try:
    import lxml.etree as etree
except ImportError:
    print("ERROR: lxml no está instalado. Instalar con: pip install lxml", file=sys.stderr)
    sys.exit(1)

# Agregar parent al path para imports
sys.path.insert(0, str(Path(__file__).parent.parent))

try:
    from app.sifen_client.xsd_validator import load_schema, _parser_with_resolver, SifenLocalResolver
except ImportError:
    # Fallback si no está disponible
    load_schema = None
    _parser_with_resolver = None

SIFEN_NS = "http://ekuatia.set.gov.py/sifen/xsd"


def extract_xde_base64_from_payload_xml(payload_xml: str) -> bytes:
    """
    Extrae ZIP bytes desde el XML payload (rEnvioLote con xDE).
    
    Args:
        payload_xml: XML string del rEnvioLote
        
    Returns:
        bytes del ZIP decodificado
    """
    import base64
    
    # Buscar <xDE> o <xsd:xDE>
    patterns = [
        r'<xDE[^>]*>([A-Za-z0-9+/=\s]+)</xDE>',
        r'<xsd:xDE[^>]*>([A-Za-z0-9+/=\s]+)</xsd:xDE>',
    ]
    
    xde_base64 = None
    for pattern in patterns:
        match = re.search(pattern, payload_xml, re.DOTALL)
        if match:
            xde_base64 = match.group(1).strip()
            break
    
    if not xde_base64:
        raise ValueError("No se encontró xDE en el XML payload")
    
    # Limpiar whitespace
    xde_base64_clean = re.sub(r'\s+', '', xde_base64)
    
    try:
        zip_bytes = base64.b64decode(xde_base64_clean)
        return zip_bytes
    except Exception as e:
        raise ValueError(f"xDE no es Base64 válido: {e}")


def extract_xde_from_debug_file(debug_file: Path) -> bytes:
    """
    Extrae el contenido Base64 de xDE desde el archivo de debug.
    
    Returns:
        bytes del ZIP decodificado
        
    Raises:
        ValueError: Si no se encuentra xDE o no es válido
    """
    content = debug_file.read_text(encoding="utf-8")
    
    # Buscar en el SOAP (puede estar en múltiples formas)
    # Patrón 1: <xDE>...</xDE> o <xsd:xDE>...</xsd:xDE>
    patterns = [
        r'<xDE[^>]*>([A-Za-z0-9+/=\s]+)</xDE>',
        r'<xsd:xDE[^>]*>([A-Za-z0-9+/=\s]+)</xsd:xDE>',
    ]
    
    xde_base64 = None
    for pattern in patterns:
        match = re.search(pattern, content, re.DOTALL | re.MULTILINE)
        if match:
            xde_base64 = match.group(1).strip()
            break
    
    if not xde_base64:
        # Intentar buscar en la sección SOAP BEGIN
        soap_section = content.split("---- SOAP BEGIN ----")[-1].split("---- SOAP END ----")[0]
        for pattern in patterns:
            match = re.search(pattern, soap_section, re.DOTALL)
            if match:
                xde_base64 = match.group(1).strip()
                break
    
    if not xde_base64:
        raise ValueError("No se encontró xDE en el archivo de debug")
    
    # Limpiar whitespace del Base64
    xde_base64_clean = re.sub(r'\s+', '', xde_base64)
    
    try:
        zip_bytes = base64.b64decode(xde_base64_clean)
        return zip_bytes
    except Exception as e:
        raise ValueError(f"xDE no es Base64 válido: {e}")


def extract_lote_xml_from_zip(zip_bytes: bytes) -> Tuple[bytes, bytes]:
    """
    Extrae lote.xml del ZIP.
    
    Returns:
        Tupla (lote_xml_bytes, zip_bytes) para guardar
        
    Raises:
        ValueError: Si el ZIP no es válido o no contiene lote.xml
    """
    try:
        with zipfile.ZipFile(BytesIO(zip_bytes), mode='r') as zf:
            # Soportar tanto xml_file.xml como lote.xml (compatibilidad)
            xml_file_name = None
            if "xml_file.xml" in zf.namelist():
                xml_file_name = "xml_file.xml"
            elif "lote.xml" in zf.namelist():
                xml_file_name = "lote.xml"
            
            if not xml_file_name:
                raise ValueError(f"ZIP no contiene 'xml_file.xml' ni 'lote.xml'. Archivos: {zf.namelist()}")
            
            lote_xml_bytes = zf.read(xml_file_name)
            return lote_xml_bytes, zip_bytes
    except zipfile.BadZipFile as e:
        raise ValueError(f"ZIP inválido: {e}")


def hexdump(data: bytes, max_bytes: int = 256) -> str:
    """Genera hexdump de los primeros bytes para debug."""
    lines = []
    for i in range(0, min(len(data), max_bytes), 16):
        chunk = data[i:i+16]
        hex_str = ' '.join(f'{b:02x}' for b in chunk)
        ascii_str = ''.join(chr(b) if 32 <= b < 127 else '.' for b in chunk)
        lines.append(f"{i:04x}: {hex_str:<48} {ascii_str}")
    return '\n'.join(lines)


def validate_xml_well_formed(xml_bytes: bytes, name: str) -> etree._Element:
    """
    Valida que XML sea well-formed (sin recover).
    
    Returns:
        Element root parseado
        
    Raises:
        ValueError: Si el XML no es well-formed
    """
    parser = etree.XMLParser(recover=False, huge_tree=True)
    try:
        root = etree.fromstring(xml_bytes, parser=parser)
        return root
    except etree.XMLSyntaxError as e:
        print(f"\n❌ {name} NO es well-formed XML:", file=sys.stderr)
        print(f"   Error: {e}", file=sys.stderr)
        print(f"   Línea {e.lineno}, columna {e.offset}", file=sys.stderr)
        print(f"\n📋 Hexdump (primeros 256 bytes):", file=sys.stderr)
        print(hexdump(xml_bytes[:256]), file=sys.stderr)
        raise ValueError(f"{name} no es well-formed XML: {e}") from e
    except Exception as e:
        print(f"\n❌ Error inesperado al parsear {name}: {e}", file=sys.stderr)
        print(f"\n📋 Hexdump (primeros 256 bytes):", file=sys.stderr)
        print(hexdump(xml_bytes[:256]), file=sys.stderr)
        raise ValueError(f"Error al parsear {name}: {e}") from e


def find_xsd_file(xsd_dir: Path, patterns: list[str], version: Optional[str] = None) -> Optional[Path]:
    """
    Busca archivo XSD que coincida con los patrones.
    
    Args:
        xsd_dir: Directorio donde buscar
        patterns: Lista de patrones (substrings) para buscar en el nombre
        version: Versión opcional (ej: "150" para v150)
        
    Returns:
        Path al XSD encontrado o None
    """
    if not xsd_dir.exists():
        return None
    
    candidates = []
    for xsd_file in xsd_dir.rglob("*.xsd"):
        filename = xsd_file.name
        # Verificar que coincida con al menos un patrón
        matches_pattern = any(pat.lower() in filename.lower() for pat in patterns)
        
        if matches_pattern:
            # Si hay versión, preferir archivos que la contengan
            if version and version in filename:
                return xsd_file
            candidates.append(xsd_file)
    
    # Si hay candidatos, devolver el primero
    if candidates:
        return candidates[0]
    
    return None


def pick_best_xsd_by_trial(xml_bytes: bytes, xsd_dir: Path, root_qname: str, debug: bool = False) -> Tuple[Optional[Path], dict]:
    """
    Encuentra el mejor XSD probando validación real contra todos los XSDs disponibles.
    
    Args:
        xml_bytes: XML a validar
        xsd_dir: Directorio donde buscar XSDs
        root_qname: QName completo del root (ej: "{http://ekuatia.set.gov.py/sifen/xsd}rLoteDE")
        debug: Si True, imprime información detallada
        
    Returns:
        Tupla (best_xsd_path, debug_info_dict)
        - best_xsd_path: Path al mejor XSD encontrado o None
        - debug_info: Dict con información de debug
    """
    debug_info = {
        "total_tested": 0,
        "case_a_count": 0,  # No matching global declaration
        "case_b_count": 0,  # Schema OK pero falla validación (candidato correcto)
        "case_c_count": 0,  # Valida OK
        "candidates": []
    }
    
    if not xsd_dir.exists():
        return None, debug_info
    
    import re
    
    # Parsear XML una vez
    try:
        xml_doc = etree.fromstring(xml_bytes)
    except Exception as e:
        if debug:
            print(f"   DEBUG: Error al parsear XML: {e}", file=sys.stderr)
        return None, debug_info
    
    # Extraer localname para filtrar XSDs de consulta
    root_localname = etree.QName(root_qname).localname
    exclude_cons = root_localname == "rLoteDE"
    
    candidates_case_b = []  # (priority_score, xsd_path, first_error)
    candidate_case_c = None  # Primer XSD que valida OK
    
    # Iterar todos los XSD
    all_xsd_files = list(xsd_dir.rglob("*.xsd"))
    debug_info["total_tested"] = len(all_xsd_files)
    
    for xsd_file in all_xsd_files:
        filename = xsd_file.name
        
        # Ignorar XSDs de consulta si es rLoteDE
        if exclude_cons and any(excl in filename.lower() for excl in ["cons", "consult"]):
            continue
        
        try:
            # Intentar compilar schema
            try:
                # Usar resolver si está disponible
                if load_schema is not None:
                    schema = load_schema(xsd_file, xsd_dir)
                else:
                    # Fallback: cargar sin resolver pero con base_url
                    parser = etree.XMLParser(base_url=str(xsd_file.parent))
                    schema_doc = etree.parse(str(xsd_file), parser)
                    schema = etree.XMLSchema(schema_doc)
                schema_compiled = True
            except Exception as e:
                schema_compiled = False
                if debug:
                    print(f"   DEBUG: {filename}: No compiló schema: {e}", file=sys.stderr)
                continue
            
            # Intentar validar
            try:
                is_valid = schema.validate(xml_doc)
                
                if is_valid:
                    # Caso C: Valida OK
                    candidate_case_c = xsd_file
                    debug_info["case_c_count"] += 1
                    if debug:
                        print(f"   DEBUG: ✓ {filename}: VALIDA OK (Caso C)", file=sys.stderr)
                    # Si encontramos uno que valida, usarlo inmediatamente
                    break
                else:
                    # Caso A o B: Analizar error_log
                    error_log = schema.error_log
                    if not error_log:
                        continue
                    
                    first_error = error_log[0]
                    error_msg = first_error.message or ""
                    error_msg_lower = error_msg.lower()
                    
                    # Caso A: "No matching global declaration"
                    if "no matching global" in error_msg_lower or "no matching global element" in error_msg_lower:
                        debug_info["case_a_count"] += 1
                        if debug:
                            print(f"   DEBUG: ✗ {filename}: Caso A (root no declarado)", file=sys.stderr)
                        continue
                    
                    # Caso B: Schema OK pero falla por otras razones
                    debug_info["case_b_count"] += 1
                    
                    # Calcular priority_score (mayor es mejor)
                    # Preferir nombres que contengan "RecepLote" o "Lote" sobre otros
                    priority_score = 0
                    if "receplotede" in filename.lower() or "receplotede" in filename.lower():
                        priority_score = 100
                    elif "lote" in filename.lower():
                        priority_score = 50
                    elif "contenedor" in filename.lower():
                        priority_score = 75
                    
                    # Extraer versión (mayor versión = mejor)
                    version_match = re.search(r'_v(\d+)\.xsd$|v(\d+)\.xsd$', filename, re.IGNORECASE)
                    if version_match:
                        version_int = int(version_match.group(1) or version_match.group(2))
                        priority_score += version_int
                    
                    candidates_case_b.append((
                        priority_score,
                        xsd_file,
                        first_error
                    ))
                    
                    if debug:
                        error_preview = error_msg[:120] if len(error_msg) > 120 else error_msg
                        print(f"   DEBUG: ⚠ {filename}: Caso B (schema OK, error real): {error_preview}", file=sys.stderr)
                        
            except Exception as e:
                # Error durante validación (no schema compilado, etc)
                if debug:
                    print(f"   DEBUG: ✗ {filename}: Error en validación: {e}", file=sys.stderr)
                continue
                
        except Exception as e:
            # Error general
            if debug:
                print(f"   DEBUG: ✗ {filename}: Error: {e}", file=sys.stderr)
            continue
    
    # Elegir mejor candidato
    best_xsd = None
    
    # Prioridad 1: Caso C (valida OK)
    if candidate_case_c:
        best_xsd = candidate_case_c
    # Prioridad 2: Caso B (mejor error real)
    elif candidates_case_b:
        # Ordenar por priority_score desc
        candidates_case_b.sort(key=lambda x: x[0], reverse=True)
        best_xsd = candidates_case_b[0][1]
        debug_info["best_error"] = candidates_case_b[0][2]
        debug_info["candidates"] = [
            {
                "filename": c[1].name,
                "priority": c[0],
                "error": str(c[2].message)[:120] if c[2].message else ""
            }
            for c in candidates_case_b[:10]
        ]
    # Prioridad 3: Caso A (ninguno sirve)
    else:
        best_xsd = None
    
    return best_xsd, debug_info


def find_xsd_that_declares_root(xsd_dir: Path, root_localname: str, debug: bool = False) -> Optional[Path]:
    """
    Busca un XSD que declare el elemento global root_localname.
    
    Args:
        xsd_dir: Directorio donde buscar XSDs
        root_localname: Nombre local del elemento raíz (ej: "rLoteDE")
        debug: Si True, imprime candidatos evaluados
        
    Returns:
        Path al XSD encontrado o None
    """
    if not xsd_dir.exists():
        return None
    
    import re
    
    # Fast check: buscar name="root_localname" o name='root_localname' en bytes
    search_pattern = f'name="{root_localname}"'.encode('utf-8')
    search_pattern_alt = f"name='{root_localname}'".encode('utf-8')
    
    # Para rLoteDE, excluir XSDs de consulta (que contienen "Cons")
    exclude_patterns = []
    if root_localname == "rLoteDE":
        exclude_patterns = ["Cons", "cons"]
    
    # Prioridad de nombres (orden de preferencia)
    priority_patterns = []
    if root_localname == "rLoteDE":
        priority_patterns = [
            ("ContenedorDE", 100),  # Mayor prioridad
            ("SiRecepLoteDE", 90),
            ("siRecepLoteDE", 89),
            ("WS_SiRecepLoteDE", 80),
            ("Lote", 50),  # Cualquier otro con "Lote" pero no "Cons"
        ]
    
    candidates_with_match = []  # (priority, version_int, path, has_fast_match)
    candidates_all = []  # Todos los candidatos (para debug)
    
    # Escanear todos los XSD
    for xsd_file in xsd_dir.rglob("*.xsd"):
        filename = xsd_file.name
        
        # Excluir según patrones
        if exclude_patterns:
            if any(excl.lower() in filename.lower() for excl in exclude_patterns):
                if debug:
                    print(f"   DEBUG: Descartado '{filename}' (contiene 'Cons')", file=sys.stderr)
                continue
        
        # Verificar si es candidato según patrones de prioridad
        priority = 0
        matched_pattern = None
        for pattern, prio in priority_patterns:
            if pattern.lower() in filename.lower():
                priority = prio
                matched_pattern = pattern
                break
        
        # Si no matchea ningún patrón de prioridad, puede ser candidato genérico (prioridad baja)
        if priority == 0 and not exclude_patterns:
            priority = 10  # Prioridad baja para otros
        
        if priority > 0 or not exclude_patterns:
            # Fast check: buscar name="root_localname" en el archivo
            try:
                content = xsd_file.read_bytes()
                has_match = search_pattern in content or search_pattern_alt in content
                
                # Extraer versión si existe
                version_match = re.search(r'_v(\d+)\.xsd$|v(\d+)\.xsd$', filename, re.IGNORECASE)
                version_int = 0
                if version_match:
                    version_int = int(version_match.group(1) or version_match.group(2))
                
                candidates_all.append((priority, version_int, xsd_file, has_match, matched_pattern))
                
                if has_match:
                    candidates_with_match.append((priority, version_int, xsd_file))
            except Exception:
                # Si no se puede leer, omitir
                continue
    
    if debug:
        # Ordenar por prioridad desc, versión desc
        candidates_all_sorted = sorted(candidates_all, key=lambda x: (x[0], x[1]), reverse=True)
        print(f"   DEBUG: Top 10 candidatos evaluados para root '{root_localname}':", file=sys.stderr)
        for i, (prio, ver, path, has_match, pattern) in enumerate(candidates_all_sorted[:10], 1):
            match_str = "✓ MATCH" if has_match else "✗ no match"
            print(f"   {i}. [{prio:3d}] v{ver:3d} {match_str}  {path.name} (pattern: {pattern})", file=sys.stderr)
    
    # Si hay candidatos con fast match, elegir el de mayor prioridad, luego mayor versión
    if candidates_with_match:
        candidates_with_match.sort(key=lambda x: (x[0], x[1]), reverse=True)
        best = candidates_with_match[0]
        return best[2]
    
    # Si no hay fast match pero hay candidatos por nombre (para rLoteDE, usar el mejor candidato de recepción)
    # Esto es útil cuando rLoteDE está definido en tipos incluidos, no directamente en el XSD
    if root_localname == "rLoteDE" and candidates_all:
        # Ordenar por prioridad desc, versión desc
        candidates_all_sorted = sorted(candidates_all, key=lambda x: (x[0], x[1]), reverse=True)
        # Tomar el primero (ya filtrado para excluir "Cons")
        best_candidate = candidates_all_sorted[0]
        return best_candidate[2]
    
    # Si no hay candidatos, devolver None
    return None


def validate_against_xsd(xml_doc: etree._Element, xsd_path: Path, xsd_dir: Path, name: str) -> bool:
    """
    Valida XML contra XSD (usando resolver local si está disponible).
    
    Returns:
        True si es válido
        
    Raises:
        ValueError: Si la validación falla (con detalles del error)
    """
    try:
        # Usar load_schema si está disponible (tiene resolver)
        if load_schema is not None:
            schema = load_schema(xsd_path, xsd_dir)
        else:
            # Fallback: cargar sin resolver
            schema = etree.XMLSchema(etree.parse(str(xsd_path)))
    except etree.XMLSchemaParseError as e:
        raise ValueError(f"XSD {xsd_path} no es válido: {e}") from e
    except Exception as e:
        raise ValueError(f"Error al cargar XSD {xsd_path}: {e}") from e
    
    is_valid = schema.validate(xml_doc)
    
    if not is_valid:
        error_log = schema.error_log
        print(f"\n❌ {name} NO pasa validación XSD ({xsd_path.name}):", file=sys.stderr)
        
        # Imprimir primeros 10 errores
        errors = list(error_log)
        for i, error in enumerate(errors[:10], 1):
            print(f"\n   Error {i}:", file=sys.stderr)
            print(f"      Domain: {error.domain}", file=sys.stderr)
            print(f"      Type: {error.type}", file=sys.stderr)
            print(f"      Level: {error.level}", file=sys.stderr)
            print(f"      Line: {error.line}, Column: {error.column}", file=sys.stderr)
            print(f"      Message: {error.message}", file=sys.stderr)
        
        # El primer error es el más importante
        first_error = errors[0] if errors else None
        if first_error:
            error_msg = (
                f"Element validation failed: {first_error.message} "
                f"(line {first_error.line}, col {first_error.column})"
            )
            raise ValueError(error_msg)
        else:
            raise ValueError(f"{name} no pasa validación XSD")
    
    return True


def extract_rde_from_lote(lote_xml_bytes: bytes) -> Tuple[etree._Element, bytes]:
    """
    Extrae el elemento rDE de lote.xml.
    
    Returns:
        Tupla (rde_element, rde_xml_bytes)
    """
    lote_root = validate_xml_well_formed(lote_xml_bytes, "lote.xml")
    
    # Buscar rDE (puede estar en namespace o sin namespace)
    rde = None
    
    # Intentar con namespace
    rde = lote_root.find(f".//{{{SIFEN_NS}}}rDE")
    
    # Si no se encuentra, buscar sin namespace
    if rde is None:
        for elem in lote_root.iter():
            if etree.QName(elem).localname == "rDE":
                rde = elem
                break
    
    if rde is None:
        raise ValueError("No se encontró elemento rDE dentro de lote.xml")
    
    # Serializar rDE como documento standalone
    rde_xml_bytes = etree.tostring(rde, xml_declaration=True, encoding="UTF-8")
    
    return rde, rde_xml_bytes


def get_version_from_rde(rde_root: etree._Element) -> Optional[str]:
    """
    Extrae dVerFor del rDE para determinar versión.
    
    Returns:
        Versión (ej: "150") o None
    """
    # Buscar dVerFor (puede estar con o sin namespace)
    dverfor = None
    
    # Intentar con namespace
    dverfor = rde_root.find(f".//{{{SIFEN_NS}}}dVerFor")
    
    if dverfor is None:
        for elem in rde_root.iter():
            if etree.QName(elem).localname == "dVerFor":
                dverfor = elem
                break
    
    if dverfor is not None and dverfor.text:
        return dverfor.text.strip()
    
    return None


def detect_xsd_dir() -> Optional[Path]:
    """
    Detecta automáticamente el directorio XSD.
    
    Prioridad:
    1. SIFEN_XSD_DIR env var
    2. rshk-jsifenlib/docs/set/ekuatia.set.gov.py/sifen/xsd (relativo desde repo root)
    3. None (no encontrado)
    """
    # 1. Env var
    xsd_dir_env = os.getenv("SIFEN_XSD_DIR")
    if xsd_dir_env:
        xsd_path = Path(xsd_dir_env)
        if xsd_path.exists():
            return xsd_path.resolve()
    
    # 2. Buscar rshk-jsifenlib desde repo root
    repo_root = Path(__file__).parent.parent.parent
    xsd_path = repo_root / "rshk-jsifenlib" / "docs" / "set" / "ekuatia.set.gov.py" / "sifen" / "xsd"
    if xsd_path.exists():
        return xsd_path.resolve()
    
    return None


def validate_lote_from_zip_bytes(zip_bytes: bytes, xsd_dir: Path) -> Tuple[bool, Optional[str]]:
    """
    Valida lote.xml desde bytes ZIP.
    
    Si rLoteDE viene sin namespace (VACÍO), hace validación estructural mínima
    en vez de requerir XSD que declare rLoteDE.
    
    Returns:
        Tupla (ok, error_message)
    """
    try:
        # Extraer lote.xml (soporta xml_file.xml y lote.xml)
        lote_xml_bytes, _ = extract_lote_xml_from_zip(zip_bytes)
        
        # Validar well-formed
        lote_root = validate_xml_well_formed(lote_xml_bytes, "lote.xml")
        
        root_qname = lote_root.tag  # QName completo
        root_localname = etree.QName(lote_root).localname
        root_ns = etree.QName(lote_root).namespace or "VACÍO"
        
        # Si rLoteDE viene SIN namespace (VACÍO), hacer validación estructural mínima
        if root_localname == "rLoteDE" and root_ns == "VACÍO":
            # Validación estructural mínima (sin XSD)
            # a) root localname == rLoteDE (ya verificado arriba)
            # b) contiene rDE con namespace SIFEN
            rde_element, rde_xml_bytes = extract_rde_from_lote(lote_xml_bytes)
            rde_root_standalone = validate_xml_well_formed(rde_xml_bytes, "rDE")
            rde_ns = etree.QName(rde_root_standalone).namespace or "VACÍO"
            
            if rde_ns != SIFEN_NS:
                return (False, f"rDE debe tener namespace {SIFEN_NS}, tiene: {rde_ns}")
            
            # c) rDE contiene Signature
            has_signature = any(
                child.tag == f"{{{DSIG_NS}}}Signature" or 
                (hasattr(child, 'tag') and 'Signature' in str(child.tag))
                for child in list(rde_root_standalone)
            )
            if not has_signature:
                return (False, "rDE no contiene Signature como hijo directo")
            
            # d) El ZIP contiene xml_file.xml o lote.xml (ya verificado en extract_lote_xml_from_zip)
            # Todo OK para validación estructural
            return (True, None)
        
        # Si rLoteDE viene con namespace, intentar validación XSD
        debug_mode = os.getenv("VALIDATE_XSD_DEBUG", "0") in ("1", "true", "True")
        
        lote_xsd, trial_debug_info = pick_best_xsd_by_trial(
            lote_xml_bytes, xsd_dir, root_qname, debug=debug_mode
        )
        
        if not lote_xsd:
            error_msg = (
                f"No hay ningún XSD en el directorio que declare el root "
                f"{{{SIFEN_NS}}}{root_localname} o que pueda validar el XML."
            )
            return (False, error_msg)
        
        # Validar con el XSD elegido
        validate_against_xsd(lote_root, lote_xsd, xsd_dir, "lote.xml")
        
        # Extraer y validar rDE
        rde_element, rde_xml_bytes = extract_rde_from_lote(lote_xml_bytes)
        version = get_version_from_rde(rde_element)
        
        rde_root_standalone = validate_xml_well_formed(rde_xml_bytes, "rDE")
        
        rde_patterns = ["siRecepDE", "DE_", "rDE"]
        if version:
            rde_patterns.append(f"v{version}")
        rde_xsd = find_xsd_file(xsd_dir, rde_patterns, version)
        
        if rde_xsd:
            validate_against_xsd(rde_root_standalone, rde_xsd, xsd_dir, "rDE")
        
        return (True, None)
        
    except Exception as e:
        return (False, str(e))


def main():
    import argparse
    
    parser = argparse.ArgumentParser(description="Valida lote.xml contra XSD antes de enviar")
    parser.add_argument("--debug-file", type=Path, default=Path("artifacts/soap_last_http_debug.txt"), help="Archivo de debug con SOAP")
    parser.add_argument("--xsd-dir", type=Path, help="Directorio con XSDs (si no se especifica, intenta detectar automáticamente)")
    
    args = parser.parse_args()
    
    # Detectar xsd_dir si no se especificó
    if not args.xsd_dir:
        xsd_dir = detect_xsd_dir()
        if not xsd_dir:
            print("ERROR: No se encontró directorio XSD. Usar --xsd-dir o configurar SIFEN_XSD_DIR", file=sys.stderr)
            sys.exit(1)
        args.xsd_dir = xsd_dir
    
    if not args.debug_file.exists():
        print(f"ERROR: No existe: {args.debug_file}", file=sys.stderr)
        sys.exit(1)
    
    if not args.xsd_dir.exists():
        print(f"ERROR: No existe directorio XSD: {args.xsd_dir}", file=sys.stderr)
        sys.exit(1)
    
    try:
        print("🔍 Extrayendo xDE desde debug file...")
        zip_bytes = extract_xde_from_debug_file(args.debug_file)
        print(f"   ✓ ZIP extraído: {len(zip_bytes)} bytes")
        
        print("\n📦 Extrayendo lote.xml del ZIP...")
        lote_xml_bytes, zip_bytes_saved = extract_lote_xml_from_zip(zip_bytes)
        print(f"   ✓ lote.xml extraído: {len(lote_xml_bytes)} bytes")
        
        # Guardar archivos temporales
        tmp_lote_xml = Path("/tmp/lote_extracted.xml")
        tmp_zip = Path("/tmp/lote_extracted.zip")
        tmp_lote_xml.write_bytes(lote_xml_bytes)
        tmp_zip.write_bytes(zip_bytes_saved)
        print(f"   ✓ Guardado en: {tmp_lote_xml} y {tmp_zip}")
        
        # 1) Validar XML well-formed
        print("\n✅ Validando lote.xml well-formed...")
        lote_root = validate_xml_well_formed(lote_xml_bytes, "lote.xml")
        print(f"   ✓ lote.xml es well-formed XML")
        root_localname = etree.QName(lote_root).localname
        root_ns = etree.QName(lote_root).namespace or "VACÍO"
        print(f"   ✓ Root: {root_localname} (ns: {root_ns})")
        
        # Verificar estructura esperada según evidencia externa
        if root_localname == "rLoteDE" and root_ns != "VACÍO":
            print(f"   ⚠️  WARNING: rLoteDE NO debe tener namespace (debe estar VACÍO), tiene: {root_ns}")
        elif root_localname == "rLoteDE" and root_ns == "VACÍO":
            print(f"   ✓ rLoteDE sin namespace (OK según evidencia externa)")
        
        # 2) Buscar mejor XSD probando validación real
        root_qname = lote_root.tag  # QName completo (ej: "{http://ekuatia.set.gov.py/sifen/xsd}rLoteDE")
        root_localname = etree.QName(lote_root).localname
        print(f"\n🔍 Buscando XSD que pueda validar '{root_localname}'...")
        
        debug_mode = os.getenv("VALIDATE_XSD_DEBUG", "0") in ("1", "true", "True")
        lote_xsd, trial_debug_info = pick_best_xsd_by_trial(
            lote_xml_bytes, args.xsd_dir, root_qname, debug=debug_mode
        )
        
        if not lote_xsd:
            print(f"\n❌ No hay ningún XSD en el directorio que declare el root "
                  f"{{{SIFEN_NS}}}{root_localname} o que pueda validar el XML.", file=sys.stderr)
            
            if debug_mode:
                print(f"\n   DEBUG: Total XSDs probados: {trial_debug_info['total_tested']}", file=sys.stderr)
                print(f"   DEBUG: Caso A (root no declarado): {trial_debug_info['case_a_count']}", file=sys.stderr)
                print(f"   DEBUG: Caso B (schema OK, error real): {trial_debug_info['case_b_count']}", file=sys.stderr)
                print(f"   DEBUG: Caso C (valida OK): {trial_debug_info['case_c_count']}", file=sys.stderr)
                if trial_debug_info.get("candidates"):
                    print(f"\n   DEBUG: Top candidatos Caso B:", file=sys.stderr)
                    for i, cand in enumerate(trial_debug_info["candidates"][:10], 1):
                        print(f"     {i}. {cand['filename']} (priority: {cand['priority']}): {cand['error']}", file=sys.stderr)
            
            # Listar XSDs relacionados presentes
            related_xsds = []
            for xsd_file in args.xsd_dir.rglob("*.xsd"):
                filename = xsd_file.name
                if any(term in filename.lower() for term in ["lote", "receplote", "contenedor", "recep"]):
                    related_xsds.append(filename)
            
            if related_xsds:
                print(f"\n   Archivos XSD relacionados presentes (hasta 30):", file=sys.stderr)
                for xsd_name in sorted(set(related_xsds))[:30]:
                    print(f"     - {xsd_name}", file=sys.stderr)
                print(f"\n   Sugerencia: Verificar que el pack XSD incluye el schema correcto para '{root_localname}'", file=sys.stderr)
            
            raise ValueError(f"No se encontró XSD que pueda validar '{root_localname}'")
        else:
            # Extraer versión del nombre del archivo
            version_match = re.search(r'_v(\d+)\.xsd$|v(\d+)\.xsd$', lote_xsd.name, re.IGNORECASE)
            version_str = ""
            if version_match:
                version_int = int(version_match.group(1) or version_match.group(2))
                version_str = f" (versión v{version_int})"
            
            if debug_mode:
                print(f"\n   DEBUG: Total XSDs probados: {trial_debug_info['total_tested']}", file=sys.stderr)
                print(f"   DEBUG: Caso A (root no declarado): {trial_debug_info['case_a_count']}", file=sys.stderr)
                print(f"   DEBUG: Caso B (schema OK, error real): {trial_debug_info['case_b_count']}", file=sys.stderr)
                print(f"   DEBUG: Caso C (valida OK): {trial_debug_info['case_c_count']}", file=sys.stderr)
            
            # Si es Caso B (tiene error real), mostrar que es candidato
            if trial_debug_info.get("best_error"):
                print(f"   ✓ XSD candidato para {root_localname}: {lote_xsd.name}{version_str}")
            else:
                print(f"   ✓ XSD elegido para {root_localname}: {lote_xsd.name}{version_str}")
            
            # 3) Validar lote.xml contra XSD (solo si el XSD declara rLoteDE)
            # Si el root es rLoteDE sin namespace, puede que el pack XSD no lo declare
            if root_localname == "rLoteDE" and root_ns == "VACÍO":
                # Verificar si el XSD realmente declara rLoteDE (puede que no)
                try:
                    print("\n✅ Validando lote.xml contra XSD...")
                    validate_against_xsd(lote_root, lote_xsd, args.xsd_dir, "lote.xml")
                    print(f"   ✓ lote.xml pasa validación XSD")
                except ValueError as e:
                    if "No matching global" in str(e) or "no matching global" in str(e).lower():
                        print(f"   ⚠️  WARNING: XSD pack local no declara rLoteDE; se omite validación XSD de lote")
                        print(f"   Continuando con validación well-formed y validación de rDE interno...")
                    else:
                        raise
            else:
                print("\n✅ Validando lote.xml contra XSD...")
                validate_against_xsd(lote_root, lote_xsd, args.xsd_dir, "lote.xml")
                print(f"   ✓ lote.xml pasa validación XSD")
        
        # 4) Extraer y validar rDE interno
        print("\n🔍 Extrayendo rDE de lote.xml...")
        rde_element, rde_xml_bytes = extract_rde_from_lote(lote_xml_bytes)
        version = get_version_from_rde(rde_element)
        print(f"   ✓ rDE extraído: {len(rde_xml_bytes)} bytes")
        if version:
            print(f"   ✓ Versión detectada: {version}")
        
        # Verificar que rDE tiene namespace SIFEN y contiene Signature
        rde_root_standalone = validate_xml_well_formed(rde_xml_bytes, "rDE")
        rde_ns = etree.QName(rde_root_standalone).namespace or "VACÍO"
        if rde_ns != SIFEN_NS:
            print(f"   ⚠️  WARNING: rDE debe tener namespace {SIFEN_NS}, tiene: {rde_ns}")
        else:
            print(f"   ✓ rDE tiene namespace SIFEN correcto")
        
        # Verificar Signature
        has_signature = any(
            child.tag == f"{{{DSIG_NS}}}Signature" or 
            (hasattr(child, 'tag') and 'Signature' in str(child.tag))
            for child in list(rde_root_standalone)
        )
        if not has_signature:
            print(f"   ⚠️  WARNING: rDE no contiene Signature como hijo directo")
        else:
            print(f"   ✓ rDE contiene Signature")
        
        # 5) Validar rDE well-formed (ya está validado al extraer, pero verificamos de nuevo)
        print("\n✅ Validando rDE well-formed...")
        print(f"   ✓ rDE es well-formed XML standalone")
        
        # 6) Buscar XSD de rDE
        print("\n🔍 Buscando XSD de rDE...")
        rde_patterns = ["siRecepDE", "DE_", "rDE"]
        if version:
            rde_patterns.append(f"v{version}")
        rde_xsd = find_xsd_file(args.xsd_dir, rde_patterns, version)
        
        if not rde_xsd:
            print(f"   ⚠️  No se encontró XSD de rDE en {args.xsd_dir}", file=sys.stderr)
            print(f"   Continuando sin validar contra XSD de rDE...", file=sys.stderr)
        else:
            print(f"   ✓ XSD encontrado: {rde_xsd.name}")
            
            # 7) Validar rDE contra XSD
            print("\n✅ Validando rDE contra XSD de DE...")
            validate_against_xsd(rde_root_standalone, rde_xsd, args.xsd_dir, "rDE")
            print(f"   ✓ rDE pasa validación XSD de DE")
        
        print("\n✅✅✅ VALIDACIÓN COMPLETA: Todo OK")
        return 0
        
    except ValueError as e:
        print(f"\n❌ VALIDACIÓN FALLÓ: {e}", file=sys.stderr)
        sys.exit(2)
    except Exception as e:
        print(f"\n❌ ERROR INESPERADO: {e}", file=sys.stderr)
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    # Test manual con debug:
    # VALIDATE_XSD_DEBUG=1 python -u -m tools.validate_outgoing_lote --debug-file artifacts/soap_last_http_debug.txt
    sys.exit(main())

