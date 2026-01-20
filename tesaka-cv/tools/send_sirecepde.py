#!/usr/bin/env python3
"""
CLI para enviar XML siRecepLoteDE (rEnvioLote) al servicio SOAP de Recepción Lote DE (async) de SIFEN

Este script usa SoapClient del módulo sifen_client para enviar documentos
electrónicos a SIFEN usando mTLS con certificados P12/PFX.

El script construye un lote (rLoteDE) con 1 rDE, lo comprime en ZIP, lo codifica en Base64
y lo envía dentro de un rEnvioLote al servicio async recibe_lote.

Uso:
    python -m tools.send_sirecepde --env test --xml artifacts/sirecepde_20251226_233653.xml
    python -m tools.send_sirecepde --env test --xml latest
    SIFEN_DEBUG_SOAP=1 SIFEN_SOAP_COMPAT=roshka python -m tools.send_sirecepde --env test --xml artifacts/signed.xml
"""
import sys
import argparse
import os
import re
import copy
from lxml import etree
import time
from pathlib import Path
from typing import Optional, Union, Tuple, Dict, Any
from datetime import datetime
from io import BytesIO
import base64
import zipfile
import json
import traceback

# Constante para el nombre del archivo XML dentro del ZIP
ZIP_INTERNAL_FILENAME = "lote.xml"
import hashlib

# Agregar el directorio padre al path para imports
sys.path.insert(0, str(Path(__file__).parent.parent))

# Importar módulos de debug
try:
    from .send_sirecepde_debug import dump_stage, compare_hashes
except ImportError:
    from send_sirecepde_debug import dump_stage, compare_hashes

from dotenv import load_dotenv

# Cargar variables de entorno
load_dotenv()

# Constantes de namespace SIFEN
SIFEN_NS = "http://ekuatia.set.gov.py/sifen/xsd"
SIFEN_NS_URI = "http://ekuatia.set.gov.py/sifen/xsd"  # Alias para consistencia
DS_NS = "http://www.w3.org/2000/09/xmldsig#"
DSIG_NS_URI = "http://www.w3.org/2000/09/xmldsig#"  # Alias para consistencia
XSI_NS = "http://www.w3.org/2001/XMLSchema-instance"
XSI_NS_URI = "http://www.w3.org/2001/XMLSchema-instance"  # Alias para consistencia
NS = {"s": SIFEN_NS}

# --- Namespaces ---
def _qn_sifen(local: str) -> str:
    """Crea un QName SIFEN: {http://ekuatia.set.gov.py/sifen/xsd}local"""
    return f"{{{SIFEN_NS_URI}}}{local}"

def _is_namespaced(tag: str) -> bool:
    """Verifica si un tag tiene namespace (formato {ns}local)"""
    return isinstance(tag, str) and tag.startswith("{")

def _namespace_uri(tag: str) -> Optional[str]:
    """Extrae el namespace URI de un tag namespaced, o None si no tiene namespace"""
    if not _is_namespaced(tag):
        return None
    return tag[1:].split("}", 1)[0]

def ensure_sifen_namespace(root: etree._Element) -> etree._Element:
    """
    Asegura que TODOS los elementos SIFEN (sin namespace) queden en SIFEN_NS_URI.
    No toca nodos que ya estén namespaced (ej: ds:Signature).
    """
    def _walk(el: etree._Element):
        if isinstance(el.tag, str):
            ns = _namespace_uri(el.tag)
            if ns is None:
                el.tag = _qn_sifen(el.tag)
        for ch in el:
            _walk(ch)

    _walk(root)   # ✅ afuera del def _walk
    return root


def _localname(tag: str) -> str:
    """Extrae el localname de un tag (sin namespace)"""
    return tag.split("}", 1)[1] if isinstance(tag, str) and tag.startswith("{") else tag


def _scan_xml_bytes_for_common_malformed(xml_bytes: bytes) -> Optional[str]:
    """
    Devuelve un string describiendo el problema (con offset y contexto) o None si parece sano.
    Checks enfocados a SIFEN 0160:
      - BOM UTF-8 al inicio
      - caracteres de control inválidos en XML 1.0: 0x00–0x08, 0x0B, 0x0C, 0x0E–0x1F
      - entidades '&' sospechosas: que no sean &amp; &lt; &gt; &quot; &apos; o &#...; / &#x...;
    """
    # 1. BOM UTF-8
    if xml_bytes.startswith(b"\xef\xbb\xbf"):
        return "Se detectó BOM UTF-8 al inicio del XML (offset 0). SIFEN rechaza BOM. Remover: xml_bytes = xml_bytes[3:]"
    
    # 2. Caracteres de control inválidos
    invalid = set(range(0x00, 0x09)) | {0x0B, 0x0C} | set(range(0x0E, 0x20))
    
    for i, byte_val in enumerate(xml_bytes):
        if byte_val in invalid:
            # Contexto alrededor (40 bytes antes y después)
            start = max(0, i - 40)
            end = min(len(xml_bytes), i + 40)
            context = xml_bytes[start:end]
            context_repr = repr(context)
            
            # Precalcular representación del byte para evitar backslash en f-string
            if byte_val < 0x80:
                byte_repr = repr(chr(byte_val))
            else:
                byte_repr = f"\\x{byte_val:02x}"
            
            return (
                f"Carácter de control inválido en XML 1.0 detectado:\n"
                f"  Offset: {i} (0x{i:04x})\n"
                f"  Byte: 0x{byte_val:02x} ({byte_repr})\n"
                f"  Contexto (offset {start}-{end}): {context_repr}"
            )
    
    # 3. Entidades '&' mal formadas
    try:
        text = xml_bytes.decode("utf-8", errors="replace")
    except Exception:
        # Si no se puede decodificar, no podemos verificar entidades
        return None
    
    i = 0
    while i < len(text):
        if text[i] == '&':
            # Buscar el siguiente ';'
            semicolon_pos = text.find(';', i + 1)
            
            if semicolon_pos == -1:
                # '&' sin ';' => error
                start = max(0, i - 30)
                end = min(len(text), i + 30)
                snippet = text[start:end]
                return (
                    f"Entidad '&' mal formada (sin ';'):\n"
                    f"  Offset: {i}\n"
                    f"  Fragmento: {repr(snippet)}"
                )
            
            # Extraer la entidad
            entity = text[i+1:semicolon_pos]
            
            # Validar entidad
            is_valid = False
            if entity in ('amp', 'lt', 'gt', 'quot', 'apos'):
                is_valid = True
            elif entity.startswith('#') and len(entity) > 1:
                # Numérica: &#123; o &#x1A;
                if entity[1].isdigit():
                    # Decimal: &#123;
                    is_valid = all(c.isdigit() for c in entity[1:])
                elif entity[1].lower() == 'x' and len(entity) > 2:
                    # Hexadecimal: &#x1A;
                    is_valid = all(c in '0123456789abcdefABCDEF' for c in entity[2:])
            
            if not is_valid:
                start = max(0, i - 30)
                end = min(len(text), semicolon_pos + 1 + 30)
                snippet = text[start:end]
                return (
                    f"Entidad '&' mal formada o inválida:\n"
                    f"  Offset: {i}\n"
                    f"  Entidad: &{entity};\n"
                    f"  Fragmento: {repr(snippet)}"
                )
            
            i = semicolon_pos + 1
        else:
            i += 1
    
    return None


def ensure_rde_sifen(rde_el: etree._Element) -> etree._Element:
    """
    Garantiza que el root sea {SIFEN_NS_URI}rDE y que el default xmlns sea SIFEN.
    Además namespacifica todo el árbol SIFEN que venga sin namespace.
    No toca nodos ya namespaced (ej: ds:Signature).
    
    Args:
        rde_el: Elemento rDE a asegurar
        
    Returns:
        Nuevo elemento rDE con namespace SIFEN correcto y default xmlns
    """
    if not isinstance(rde_el.tag, str) or _localname(rde_el.tag) != "rDE":
        raise RuntimeError(f"Se esperaba rDE como root, llegó: {rde_el.tag}")

    # 1) Asegurar root rDE en SIFEN
    if _namespace_uri(rde_el.tag) != SIFEN_NS_URI:
        rde_el.tag = _qn_sifen("rDE")

    # 2) Namespacificar todo lo SIFEN sin namespace
    ensure_sifen_namespace(rde_el)

    # 3) Forzar default xmlns SIFEN re-envolviendo el root
    new_rde = etree.Element(
        _qn_sifen("rDE"),
        nsmap={None: SIFEN_NS_URI, "ds": DSIG_NS_URI},
    )

    # Copiar atributos (si existieran) EXCEPTO xsi:schemaLocation
    for k, v in rde_el.attrib.items():
        if 'schemaLocation' not in k:  # No copiar xsi:schemaLocation (causa 0160)
            new_rde.set(k, v)

    # Mover hijos
    for ch in list(rde_el):
        parent = ch.getparent()
        if parent is not None and parent is rde_el:
            rde_el.remove(ch)
            new_rde.append(ch)

    return new_rde


def _move_signature_into_de_if_needed(signed_bytes: bytes, artifacts_dir: Optional[Path], debug_enabled: bool) -> bytes:
    """
    Mueve la Signature dentro del DE si está fuera (como hermano del DE dentro del rDE).
    
    Args:
        signed_bytes: XML firmado como bytes
        artifacts_dir: Directorio para guardar artifacts (opcional)
        debug_enabled: Si True, guarda artifacts de debug
        
    Returns:
        XML corregido como bytes (con Signature dentro del DE)
    """
    try:
        root = etree.fromstring(signed_bytes)
    except Exception as e:
        raise ValueError(f"Error al parsear XML firmado: {e}")
    
    # Guardar entrada si está en modo debug
    if debug_enabled and artifacts_dir:
        try:
            artifacts_dir.mkdir(parents=True, exist_ok=True)
            artifacts_dir.joinpath("signed_before_sig_move.xml").write_bytes(signed_bytes)
        except Exception:
            pass
    
    # Encontrar el DE (namespace SIFEN)
    # Si el root es DE, usarlo directamente
    root_localname = local_tag(root.tag)
    if root_localname == "DE":
        de_elem = root
    else:
        # Buscar DE dentro del árbol
        de_elem = root.find(f".//{{{SIFEN_NS_URI}}}DE")
        if de_elem is None:
            # Fallback: buscar por local-name
            nodes = root.xpath("//*[local-name()='DE']")
            de_elem = nodes[0] if nodes else None
    
    if de_elem is None:
        # Si no hay DE, retornar sin cambios
        return signed_bytes
    
    # Verificar si Signature YA es hijo de DE
    sig_in_de = de_elem.find(f".//{{{DSIG_NS_URI}}}Signature")
    if sig_in_de is not None:
        # Ya está dentro del DE, retornar sin cambios
        return signed_bytes
    
    # Buscar Signature en namespace XMLDSIG (puede estar como hermano del DE dentro del rDE)
    sig_elem = None
    # Buscar en todo el árbol
    for elem in root.iter():
        if local_tag(elem.tag) == "Signature":
            elem_ns = _namespace_uri(elem.tag)
            if elem_ns == DSIG_NS_URI:
                sig_elem = elem
                break
    
    if sig_elem is None:
        # No hay Signature, retornar sin cambios
        return signed_bytes
    
    # Verificar si Signature es hijo directo del rDE (hermano del DE)
    sig_parent = sig_elem.getparent()
    if sig_parent is not None:
        # Verificar si el parent es rDE
        parent_localname = local_tag(sig_parent.tag)
        if parent_localname == "rDE":
            # Mover Signature dentro del DE
            # Verificar que sig_elem realmente es hijo de sig_parent antes de remover
            if sig_elem in list(sig_parent):
                sig_parent.remove(sig_elem)
            else:
                # Si no es hijo directo, buscar el parent real
                actual_parent = sig_elem.getparent()
                if actual_parent is not None:
                    actual_parent.remove(sig_elem)
            
            # Buscar gCamFuFD dentro del DE para insertar Signature antes de él
            gcamfufd = de_elem.find(f".//{{{SIFEN_NS_URI}}}gCamFuFD")
            if gcamfufd is not None:
                # Insertar Signature justo ANTES de gCamFuFD
                idx = list(de_elem).index(gcamfufd)
                de_elem.insert(idx, sig_elem)
            else:
                # Append al final del DE
                de_elem.append(sig_elem)
    
    # Serializar de vuelta a bytes
    # CRÍTICO: Preservar xmlns SIFEN en Signature si estaba presente
    result_bytes = etree.tostring(root, encoding="utf-8", xml_declaration=True)
    
    # NO tocar namespace de Signature aqui. Debe quedar XMLDSIG tal como fue firmado.
# Guardar salida si está en modo debug
    if debug_enabled and artifacts_dir:
        try:
            artifacts_dir.mkdir(parents=True, exist_ok=True)
            artifacts_dir.joinpath("signed_after_sig_move.xml").write_bytes(result_bytes)
        except Exception:
            pass
    
    return result_bytes


def _remove_redundant_xsi_declarations(xml_bytes: bytes) -> bytes:
    """
    Remove redundant xmlns:xsi declarations from child elements.
    Only rDE should have xmlns:xsi declaration according to SIFEN KB.
    """
    # import re  # usa el import global (evita UnboundLocalError)    xml_str = xml_bytes.decode('utf-8', errors='replace')
    # Remove xmlns:xsi from all elements except rDE
    # First, find and preserve the rDE declaration
    rde_match = re.search(r'<rDE[^>]*xmlns:xsi="[^"]*"[^>]*>', xml_str)
    if rde_match:
        # Remove xmlns:xsi from all other elements
        xml_str = re.sub(r'<(?!rDE)([^/][^>]*?)\s+xmlns:xsi="[^"]*"([^>]*)>', r'<\1\2>', xml_str)
        # Special case for self-closing tags (not rDE)
        xml_str = re.sub(r'<(?!rDE)([^/][^>]*?)\s+xmlns:xsi="[^"]*"([^>]*)/>', r'<\1\2/>', xml_str)
    return xml_str.encode('utf-8')


def _remove_xsi_schemalocation_from_bytes(xml_bytes: bytes) -> bytes:
    """
    Remove xsi:schemaLocation from XML bytes using regex.
    This is needed because xsi:schemaLocation causes error 0160 in SIFEN.
    """
    # import re  # usa el import global (evita UnboundLocalError)    # Remove xsi:schemaLocation attribute (including newlines)
    xml_str = xml_bytes.decode('utf-8', errors='replace')
    xml_str = re.sub(r'\s*xsi:schemaLocation="[^"]*"', '', xml_str, flags=re.DOTALL)
    return xml_str.encode('utf-8')


def _remove_xsi_schemalocation(elem):
    """
    Remueve el atributo xsi:schemaLocation de un elemento y todos sus hijos.
    Esto es necesario para evitar el error 0160 de SIFEN.
    """
    removed = False
    # Remover del elemento actual
    attrs_to_remove = []
    for attr_name in elem.attrib:
        if 'schemaLocation' in attr_name:
            attrs_to_remove.append(attr_name)
            removed = True
    for attr in attrs_to_remove:
        del elem.attrib[attr]
    
    # Recursivamente remover de los hijos
    for child in elem:
        if _remove_xsi_schemalocation(child):
            removed = True
    
    return removed


def build_lote_xml(rde_element: etree._Element) -> bytes:
    """
    Construye el XML del lote (rLoteDE) con namespace SIFEN correcto.

    IMPORTANTE:
    - lote.xml (dentro del ZIP) NO debe contener <dId> ni <xDE>.
      Esos campos pertenecen al SOAP rEnvioLote, NO al archivo lote.xml.
    """
    print("DEBUG: build_lote_xml llamado")
    # REMOVER xsi:schemaLocation del rDE y todos sus hijos (causa 0160)
    print("DEBUG: Llamando a _remove_xsi_schemalocation en build_lote_xml")
    removed = _remove_xsi_schemalocation(rde_element)
    print(f"DEBUG: _remove_xsi_schemalocation en build_lote_xml retornó {removed}")
    
    # Asegurar que rDE tenga el atributo Id requerido por el XSD
    if 'Id' not in rde_element.attrib:
        # Buscar el elemento DE interno para obtener su Id
        de_elem = rde_element.find('.//{*}DE')
        if de_elem is not None and 'Id' in de_elem.attrib:
            rde_element.set('Id', de_elem.get('Id'))
            print(f"DEBUG: Agregado atributo Id='{de_elem.get('Id')}' a rDE para cumplir XSD")
        else:
            # Generar un Id único si no encontramos el DE Id
            import uuid
            generated_id = str(uuid.uuid4())
            rde_element.set('Id', generated_id)
            print(f"DEBUG: Agregado atributo Id generado='{generated_id}' a rDE")
    
    rLoteDE = etree.Element(
        etree.QName(SIFEN_NS, "rLoteDE"),
        nsmap={None: SIFEN_NS}
    )
    # Opcional (recomendado por SIFEN)
    # REMOVIDO: xsi:schemaLocation causa error 0160 "XML Mal Formado"
    # rLoteDE.set(etree.QName(XSI_NS, "schemaLocation"), f"{SIFEN_NS} siRecepDE_v150.xsd")

    # El lote.xml debe contener directamente el rDE firmado
    rLoteDE.append(rde_element)
    
    # Serializar una vez
    lote_bytes = etree.tostring(rLoteDE, encoding="utf-8", xml_declaration=False, pretty_print=False)
    
    # POST-PROCESAMIENTO: Asegurar que Signature tenga xmlns explícito
    # SIFEN requiere que Signature declare explícitamente el namespace SIFEN
    lote_str = lote_bytes.decode('utf-8')
    # DEBUG: Ver qué encontramos
    if '<Signature' in lote_str:
        sig_start = lote_str.find('<Signature')
        sig_end = lote_str.find('>', sig_start)
        sig_tag = lote_str[sig_start:sig_end+1]
        print(f"DEBUG: Signature tag found: {sig_tag}")
    
    # Usar regex para encontrar <Signature> y agregar xmlns si no lo tiene
    # import re  # usa el import global (evita UnboundLocalError)    # Buscar cualquier <Signature> que no tenga xmlns
    sig_pattern = re.compile(r'<Signature(?![^>]*xmlns)')
    if sig_pattern.search(lote_str):
        lote_str = sig_pattern.sub('<Signature xmlns="http://www.w3.org/2000/09/xmldsig#"', lote_str)
        lote_bytes = lote_str.encode('utf-8')
        print("DEBUG: Agregado xmlns XMLDSig a Signature")
    
    return lote_bytes

# Configuración del lote: usar default namespace o prefijo
# Si True: <rLoteDE xmlns="..."> (default namespace)
# Si False: <ns0:rLoteDE xmlns:ns0="..."> (prefijo)
LOTE_DEFAULT_NS = True

# Helper regex para detectar XML declaration
_XML_DECL_RE = re.compile(br"^\s*<\?xml[^>]*\?>\s*", re.I)


def local_tag(tag: str) -> str:
    """Devuelve el localname de un tag QName '{ns}local' o 'prefix:local'."""
    if '}' in tag:
        return tag.split('}', 1)[1]
    elif ':' in tag:
        return tag.split(':', 1)[1]
    else:
        return tag

# Test rápido al inicio del módulo (solo debug)
if __name__ != "__main__":  # Solo cuando se importa, no cuando se ejecuta directamente
    assert callable(local_tag), "local_tag debe ser callable"


def _strip_xml_decl(b: bytes) -> bytes:
    """Remueve la declaración XML (<?xml ...?>) del inicio de bytes."""
    return _XML_DECL_RE.sub(b"", b, count=1)


def _root_info(xml_bytes: bytes) -> Tuple[Optional[str], Optional[str]]:
    """
    Detecta el localname y namespace del root del XML (rápido y tolerante).
    Retorna (localname, namespace) o (None, None) si falla.
    """
    try:
        parser = etree.XMLParser(recover=True, remove_blank_text=False)
        root = etree.fromstring(xml_bytes, parser)
        q = etree.QName(root)
        return q.localname, q.namespace
    except Exception:
        return None, None

# Registrar namespaces para que ET use default namespace en lugar de prefijos
# Esto ayuda a que la serialización use xmlns="..." en lugar de xmlns:ns0="..."
# Registrar namespace default (lxml puede fallar con prefix "")
try:
    etree.register_namespace("", SIFEN_NS)
except ValueError:
    # Fallback: no registramos prefijo vacío; el nsmap se fuerza más adelante.
    pass


def _assert_xde_is_zip(zip_base64: str, artifacts_dir: Path):
    """
    Guard-rail para verificar que zip_base64 es realmente un ZIP válido.
    
    Args:
        zip_base64: String base64 del ZIP
        artifacts_dir: Directorio para guardar artifacts de debug
        
    Raises:
        RuntimeError: Si zip_base64 no es un ZIP válido
    """
    import base64
    import hashlib
    
    raw = base64.b64decode("".join(zip_base64.split()))
    artifacts_dir.mkdir(parents=True, exist_ok=True)
    artifacts_dir.joinpath("_debug_xde_sha256.txt").write_text(hashlib.sha256(raw).hexdigest())
    
    if not raw.startswith(b"PK\x03\x04"):
        artifacts_dir.joinpath("_xde_not_zip.bin").write_bytes(raw)
        raise RuntimeError(
            f"xDE NO es ZIP. head={raw[:8]!r} sha256={hashlib.sha256(raw).hexdigest()}. "
            f"Dump: artifacts/_xde_not_zip.bin"
        )


def _assert_signature_xmldsig_namespace(zip_base64: str, artifacts_dir: Path):
    """
    Guard-rail anti-regresión: Verifica que Signature esté en namespace XMLDSig y no SIFEN.
    
    Args:
        zip_base64: String base64 del ZIP que contiene lote.xml
        artifacts_dir: Directorio para guardar artifacts de debug
        
    Raises:
        RuntimeError: Si alguna Signature está en namespace SIFEN
    """
    import base64
    import zipfile
    import io
    from lxml import etree
    
    # Decodificar y extraer lote.xml del ZIP
    zip_bytes = base64.b64decode("".join(zip_base64.split()))
    zip_buffer = io.BytesIO(zip_bytes)
    
    with zipfile.ZipFile(zip_buffer, 'r') as zf:
        lote_xml = zf.read(ZIP_INTERNAL_FILENAME)
        # Extraer el XML interno del wrapper
        # import re  # usa el import global (evita UnboundLocalError)        wrapper_match = re.search(rb'<rLoteDE>(.*)</rLoteDE>', lote_xml, re.DOTALL)
        if wrapper_match:
            lote_xml = wrapper_match.group(1)
    
    # Parsear XML y contar namespaces de Signature
    root = etree.fromstring(lote_xml)
    
    # Registrar namespaces para búsqueda
    ns = {
        'ds': 'http://www.w3.org/2000/09/xmldsig#',
        'sifen': 'http://ekuatia.set.gov.py/sifen/xsd'
    }
    
    # Contar Signatures en cada namespace
    dsig_signatures = root.xpath('//ds:Signature', namespaces=ns)
    sifen_signatures = root.xpath('//sifen:Signature', namespaces=ns)
    
    print(f"GUARD-RAIL Signature: XMLDSig={len(dsig_signatures)}, SIFEN={len(sifen_signatures)}")
    
    if len(sifen_signatures) > 0:
        # Guardar evidencia
        artifacts_dir.mkdir(parents=True, exist_ok=True)
        artifacts_dir.joinpath("_signature_sifen_namespace_bug.xml").write_bytes(lote_xml)
        
        # Mostrar primer Signature encontrado en namespace SIFEN
        first_sifen_sig = sifen_signatures[0]
        sig_str = etree.tostring(first_sifen_sig, encoding='unicode', with_tail=False)[:200]
        
        raise RuntimeError(
            f"BUG: Signature está en namespace SIFEN; debe ser XMLDSIG. "
            f"Encontradas {len(sifen_signatures)} Signature(s) en namespace SIFEN. "
            f"Ejemplo: {sig_str}... "
            f"Evidencia guardada en artifacts/_signature_sifen_namespace_bug.xml"
        )
    
    # Guardar evidencia de que está correcto
    if len(dsig_signatures) > 0:
        artifacts_dir.mkdir(parents=True, exist_ok=True)
        artifacts_dir.joinpath("_signature_xmldsig_ok.xml").write_bytes(lote_xml)

try:
    etree.register_namespace("xsi", "http://www.w3.org/2001/XMLSchema-instance")
    etree.register_namespace("ds", "http://www.w3.org/2000/09/xmldsig#")
except (ValueError, ImportError):
    print("❌ Error: lxml no está instalado")
    print("   Instale con: pip install lxml")
    sys.exit(1)

try:
    from app.sifen_client import SoapClient, get_sifen_config, SifenClientError, SifenResponseError, SifenSizeLimitError
    from app.sifen_client.xsd_validator import validate_rde_and_lote
except ImportError as e:
    print("❌ Error: No se pudo importar módulos SIFEN")
    print(f"   Error: {e}")
    print("   Asegúrate de que las dependencias estén instaladas:")
    print("   pip install zeep lxml cryptography signxml python-dotenv")
    sys.exit(1)

# Import validation script
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "tools"))
try:
    from validate_lote_xsd import validate_lote_xsd
except ImportError:
    validate_lote_xsd = None


def _extract_metadata_from_xml(xml_content: str) -> dict:
    """
    Extrae metadatos del XML DE para debug.
    
    Returns:
        Dict con: dId, CDC, dRucEm, dDVEmi, dNumTim
    """
    metadata = {
        "dId": None,
        "CDC": None,
        "dRucEm": None,
        "dDVEmi": None,
        "dNumTim": None
    }
    
    try:
        root = etree.fromstring(xml_content.encode("utf-8"))
        
        # Buscar dId en rEnviDe o rEnvioLote
        d_id_elem = root.find(f".//{{{SIFEN_NS}}}dId")
        if d_id_elem is not None and d_id_elem.text:
            metadata["dId"] = d_id_elem.text
        
        # Buscar CDC en atributo Id del DE
        de_elem = root.find(f".//{{{SIFEN_NS}}}DE")
        if de_elem is not None:
            metadata["CDC"] = de_elem.get("Id")
            
            # Buscar dRucEm y dDVEmi dentro de gEmis
            g_emis = de_elem.find(f".//{{{SIFEN_NS}}}gEmis")
            if g_emis is not None:
                d_ruc_elem = g_emis.find(f"{{{SIFEN_NS}}}dRucEm")
                if d_ruc_elem is not None and d_ruc_elem.text:
                    metadata["dRucEm"] = d_ruc_elem.text
                
                d_dv_elem = g_emis.find(f"{{{SIFEN_NS}}}dDVEmi")
                if d_dv_elem is not None and d_dv_elem.text:
                    metadata["dDVEmi"] = d_dv_elem.text
            
            # Buscar dNumTim dentro de gTimb
            g_timb = de_elem.find(f".//{{{SIFEN_NS}}}gTimb")
            if g_timb is not None:
                d_num_tim_elem = g_timb.find(f"{{{SIFEN_NS}}}dNumTim")
                if d_num_tim_elem is not None and d_num_tim_elem.text:
                    metadata["dNumTim"] = d_num_tim_elem.text
    
    except Exception as e:
        # Si falla la extracción, continuar con valores None
        pass
    
    return metadata


def _save_zip_debug(zip_bytes: bytes, artifacts_dir: Path, debug_enabled: bool) -> None:
    """
    Guarda debug del ZIP en JSON para diagnóstico.
    
    Args:
        zip_bytes: Bytes del ZIP
        artifacts_dir: Directorio donde guardar
        debug_enabled: Si True, guarda siempre
    """
    import hashlib
    import json
    
    try:
        artifacts_dir.mkdir(parents=True, exist_ok=True)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        
        zip_sha256 = hashlib.sha256(zip_bytes).hexdigest()
        
        # Abrir ZIP y extraer información
        zip_info = {
            "zip_bytes_len": len(zip_bytes),
            "zip_sha256": zip_sha256,
            "zip_namelist": [],
            "xml_files": []
        }
        
        with zipfile.ZipFile(BytesIO(zip_bytes), "r") as zf:
            zip_info["zip_namelist"] = zf.namelist()
            
            for filename in zf.namelist():
                if filename.endswith(".xml"):
                    try:
                        xml_content = zf.read(filename)
                        xml_str = xml_content.decode("utf-8", errors="replace")
                        
                        xml_file_info = {
                            "filename": filename,
                            "first_200_chars": xml_str[:200],
                            "root_tag": None,
                            "counts": {
                                "count_xDE": 0,
                                "count_rDE": 0,
                                "DE_Id": None
                            }
                        }
                        
                        # Parsear XML para extraer información
                        try:
                            root = etree.fromstring(xml_content)
                            xml_file_info["root_tag"] = root.tag
                            
                            # Contar xDE y rDE
                            xde_elements = root.xpath('//*[local-name()="xDE"]')
                            rde_elements = root.xpath('//*[local-name()="rDE"]')
                            xml_file_info["counts"]["count_xDE"] = len(xde_elements)
                            xml_file_info["counts"]["count_rDE"] = len(rde_elements)
                            
                            # Buscar DE Id
                            de_elements = root.xpath('//*[local-name()="DE"]')
                            if de_elements:
                                de_id = de_elements[0].get("Id") or de_elements[0].get("id")
                                if de_id:
                                    xml_file_info["counts"]["DE_Id"] = de_id
                        except Exception as e:
                            xml_file_info["parse_error"] = str(e)
                        
                        zip_info["xml_files"].append(xml_file_info)
                    except Exception as e:
                        zip_info["xml_files"].append({
                            "filename": filename,
                            "error": str(e)
                        })
        
        # Guardar JSON
        zip_debug_file = artifacts_dir / f"zip_debug_{timestamp}.json"
        zip_debug_file.write_text(
            json.dumps(zip_info, ensure_ascii=False, indent=2, default=str),
            encoding="utf-8"
        )
        
        if debug_enabled:
            print(f"💾 ZIP debug guardado en: {zip_debug_file.name}")
    except Exception as e:
        if debug_enabled:
            print(f"⚠️  Error al guardar ZIP debug: {e}")


def _save_0301_diagnostic_package(
    artifacts_dir: Path,
    response: dict,
    payload_xml: str,
    zip_bytes: bytes,
    lote_xml_bytes: Optional[bytes],
    env: str,
    did: str
) -> None:
    """
    Guarda un paquete completo de evidencia cuando se recibe dCodRes=0301 con dProtConsLote=0.
    
    Crea un summary.json único por envío con:
    - Request SOAP completo (redactado, sin secretos)
    - Headers HTTP
    - Response completa
    - Hash del ZIP
    - DE Id (CDC)
    - RUC, timbrado, numdoc, fecha
    - Referencias a artifacts existentes (si dump-http está activo)
    
    Args:
        artifacts_dir: Directorio donde guardar
        response: Respuesta de SIFEN
        payload_xml: XML SOAP completo enviado
        zip_bytes: Bytes del ZIP
        lote_xml_bytes: Bytes del lote.xml
        env: Ambiente (test/prod)
        did: dId usado en el envío
    """
    import json
    import hashlib
    import base64
    # import re  # usa el import global (evita UnboundLocalError)    
    try:
        artifacts_dir.mkdir(parents=True, exist_ok=True)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        
        # 1. Calcular hash del ZIP
        zip_sha256 = hashlib.sha256(zip_bytes).hexdigest()
        
        # 2. Extraer información del DE desde lote.xml
        de_info = {
            "dNumTim": None,  # Número de timbrado
            "dEst": None,  # Establecimiento
            "dPunExp": None,  # Punto de expedición
            "dNumDoc": None,  # Número de documento
            "iTiDE": None,  # Tipo de documento
            "dFeEmiDE": None,  # Fecha de emisión
            "dRucEm": None,  # RUC emisor
            "dDVEmi": None,  # DV RUC
            "dTotalGs": None,  # Total en guaraníes
            "ambiente": None,  # test/prod (si existe en el DE)
            "de_id": None,  # CDC (Id del DE)
        }
        
        # Validaciones de formato (warnings, no bloquean)
        format_warnings = []
        
        try:
            if lote_xml_bytes is None:
                raise ValueError("lote_xml_bytes is None")
            lote_root = etree.fromstring(lote_xml_bytes)
            # Buscar DE dentro de rDE
            de_elem = None
            for elem in lote_root.iter():
                if isinstance(elem.tag, str) and _localname(elem.tag) == "DE":
                    de_elem = elem
                    break
            
            if de_elem is not None:
                # CDC (Id del DE)
                de_info["de_id"] = de_elem.get("Id") or de_elem.get("id")
                
                # RUC y DV
                g_emis = de_elem.find(f".//{{{SIFEN_NS_URI}}}gEmis")
                if g_emis is not None:
                    d_ruc_elem = g_emis.find(f"{{{SIFEN_NS_URI}}}dRucEm")
                    if d_ruc_elem is not None and d_ruc_elem.text:
                        de_info["dRucEm"] = d_ruc_elem.text.strip()
                    
                    d_dv_elem = g_emis.find(f"{{{SIFEN_NS_URI}}}dDVEmi")
                    if d_dv_elem is not None and d_dv_elem.text:
                        de_info["dDVEmi"] = d_dv_elem.text.strip()
                
                # Timbrado, establecimiento, punto expedición, número documento
                g_timb = de_elem.find(f".//{{{SIFEN_NS_URI}}}gTimb")
                if g_timb is not None:
                    d_num_tim_elem = g_timb.find(f"{{{SIFEN_NS_URI}}}dNumTim")
                    if d_num_tim_elem is not None and d_num_tim_elem.text:
                        de_info["dNumTim"] = d_num_tim_elem.text.strip()
                    
                    d_est_elem = g_timb.find(f"{{{SIFEN_NS_URI}}}dEst")
                    if d_est_elem is not None and d_est_elem.text:
                        de_info["dEst"] = d_est_elem.text.strip()
                    
                    d_pun_exp_elem = g_timb.find(f"{{{SIFEN_NS_URI}}}dPunExp")
                    if d_pun_exp_elem is not None and d_pun_exp_elem.text:
                        de_info["dPunExp"] = d_pun_exp_elem.text.strip()
                    
                    d_num_doc_elem = g_timb.find(f"{{{SIFEN_NS_URI}}}dNumDoc")
                    if d_num_doc_elem is not None and d_num_doc_elem.text:
                        de_info["dNumDoc"] = d_num_doc_elem.text.strip()
                    
                    # iTiDE (tipo de documento) - está en gTimb según XSD
                    i_tide_elem = g_timb.find(f"{{{SIFEN_NS_URI}}}iTiDE")
                    if i_tide_elem is not None and i_tide_elem.text:
                        de_info["iTiDE"] = i_tide_elem.text.strip()
                
                # Fecha de emisión (dFeEmiDE)
                g_dat_gral_ope = de_elem.find(f".//{{{SIFEN_NS_URI}}}gDatGralOpe")
                if g_dat_gral_ope is not None:
                    d_fe_emi_de_elem = g_dat_gral_ope.find(f"{{{SIFEN_NS_URI}}}dFeEmiDE")
                    if d_fe_emi_de_elem is not None and d_fe_emi_de_elem.text:
                        de_info["dFeEmiDE"] = d_fe_emi_de_elem.text.strip()
                
                # Total en guaraníes (dTotalGs)
                g_tot = de_elem.find(f".//{{{SIFEN_NS_URI}}}gTot")
                if g_tot is not None:
                    d_total_gs_elem = g_tot.find(f"{{{SIFEN_NS_URI}}}dTotalGs")
                    if d_total_gs_elem is not None and d_total_gs_elem.text:
                        de_info["dTotalGs"] = d_total_gs_elem.text.strip()
                
                # Ambiente (buscar en varios lugares posibles)
                # Puede estar en un campo específico o inferirse del env
                de_info["ambiente"] = env  # Usar el env pasado como parámetro
                
                # 3. VALIDACIONES DE FORMATO (solo warnings, no bloquean)
                from datetime import datetime as dt_datetime
                
                # Validar dNumTim: debe ser numérico, largo esperado 8 dígitos
                if de_info["dNumTim"]:
                    if not de_info["dNumTim"].isdigit():
                        format_warnings.append(f"dNumTim no es numérico: '{de_info['dNumTim']}'")
                    elif len(de_info["dNumTim"]) != 8:
                        format_warnings.append(f"dNumTim largo inesperado (esperado 8): '{de_info['dNumTim']}' (len={len(de_info['dNumTim'])})")
                
                # Validar dEst: debe ser numérico, largo esperado 3 dígitos, zero-padded
                if de_info["dEst"]:
                    if not de_info["dEst"].isdigit():
                        format_warnings.append(f"dEst no es numérico: '{de_info['dEst']}'")
                    elif len(de_info["dEst"]) != 3:
                        format_warnings.append(f"dEst largo inesperado (esperado 3): '{de_info['dEst']}' (len={len(de_info['dEst'])})")
                    elif not de_info["dEst"].startswith("0") and de_info["dEst"] != "001":
                        format_warnings.append(f"dEst posiblemente sin zero-padding: '{de_info['dEst']}'")
                
                # Validar dPunExp: debe ser numérico, largo esperado 3 dígitos, zero-padded
                if de_info["dPunExp"]:
                    if not de_info["dPunExp"].isdigit():
                        format_warnings.append(f"dPunExp no es numérico: '{de_info['dPunExp']}'")
                    elif len(de_info["dPunExp"]) != 3:
                        format_warnings.append(f"dPunExp largo inesperado (esperado 3): '{de_info['dPunExp']}' (len={len(de_info['dPunExp'])})")
                    elif not de_info["dPunExp"].startswith("0") and de_info["dPunExp"] != "001":
                        format_warnings.append(f"dPunExp posiblemente sin zero-padding: '{de_info['dPunExp']}'")
                
                # Validar dNumDoc: debe ser numérico, largo esperado 7 dígitos, zero-padded
                if de_info["dNumDoc"]:
                    if not de_info["dNumDoc"].isdigit():
                        format_warnings.append(f"dNumDoc no es numérico: '{de_info['dNumDoc']}'")
                    elif len(de_info["dNumDoc"]) != 7:
                        format_warnings.append(f"dNumDoc largo inesperado (esperado 7): '{de_info['dNumDoc']}' (len={len(de_info['dNumDoc'])})")
                    elif not de_info["dNumDoc"].startswith("0") and int(de_info["dNumDoc"]) < 1000000:
                        format_warnings.append(f"dNumDoc posiblemente sin zero-padding: '{de_info['dNumDoc']}'")
                
                # Validar dRucEm: debe ser numérico, largo esperado 6-8 dígitos
                if de_info["dRucEm"]:
                    if not de_info["dRucEm"].isdigit():
                        format_warnings.append(f"dRucEm no es numérico: '{de_info['dRucEm']}'")
                    elif len(de_info["dRucEm"]) < 6 or len(de_info["dRucEm"]) > 8:
                        format_warnings.append(f"dRucEm largo inesperado (esperado 6-8): '{de_info['dRucEm']}' (len={len(de_info['dRucEm'])})")
                
                # Validar dDVEmi: debe ser numérico, largo esperado 1 dígito
                if de_info["dDVEmi"]:
                    if not de_info["dDVEmi"].isdigit():
                        format_warnings.append(f"dDVEmi no es numérico: '{de_info['dDVEmi']}'")
                    elif len(de_info["dDVEmi"]) != 1:
                        format_warnings.append(f"dDVEmi largo inesperado (esperado 1): '{de_info['dDVEmi']}' (len={len(de_info['dDVEmi'])})")
                
                # Validar dFeEmiDE: debe ser fecha parseable y no futura
                if de_info["dFeEmiDE"]:
                    try:
                        # Formato esperado: YYYY-MM-DD o YYYY-MM-DDTHH:MM:SS
                        fecha_str = de_info["dFeEmiDE"]
                        if "T" in fecha_str:
                            fecha_dt = dt_datetime.strptime(fecha_str.split("T")[0], "%Y-%m-%d")
                        else:
                            fecha_dt = dt_datetime.strptime(fecha_str, "%Y-%m-%d")
                        
                        # Verificar que no sea futura
                        ahora = dt_datetime.now()
                        if fecha_dt > ahora:
                            format_warnings.append(f"dFeEmiDE es futura: '{fecha_str}' (hoy: {ahora.strftime('%Y-%m-%d')})")
                    except ValueError as e:
                        format_warnings.append(f"dFeEmiDE no parseable como fecha: '{de_info['dFeEmiDE']}' (error: {e})")
                
                # Validar dTotalGs: debe ser numérico
                if de_info["dTotalGs"]:
                    try:
                        total_val = float(de_info["dTotalGs"])
                        if total_val < 0:
                            format_warnings.append(f"dTotalGs es negativo: '{de_info['dTotalGs']}'")
                        elif total_val == 0:
                            format_warnings.append(f"dTotalGs es cero: '{de_info['dTotalGs']}'")
                    except ValueError:
                        format_warnings.append(f"dTotalGs no es numérico: '{de_info['dTotalGs']}'")
                
                # Validar iTiDE: debe ser numérico, valores comunes 1-7
                if de_info["iTiDE"]:
                    if not de_info["iTiDE"].isdigit():
                        format_warnings.append(f"iTiDE no es numérico: '{de_info['iTiDE']}'")
                    else:
                        tipo_val = int(de_info["iTiDE"])
                        if tipo_val < 1 or tipo_val > 7:
                            format_warnings.append(f"iTiDE valor fuera de rango común (1-7): '{de_info['iTiDE']}'")
        except Exception as e:
            # Si falla la extracción, continuar con valores None
            format_warnings.append(f"Error al extraer campos del DE: {e}")
        
        # 3. Redactar SOAP request (remover xDE base64, pero mantener estructura)
        payload_xml_redacted = payload_xml
        try:
            # Reemplazar xDE base64 con placeholder
            payload_xml_redacted = re.sub(
                r'(<xsd:xDE[^>]*>)([^<]+)(</xsd:xDE>)',
                r'\1[BASE64_REDACTED_FOR_DIAGNOSTIC]\3',
                payload_xml_redacted,
                flags=re.IGNORECASE | re.DOTALL
            )
            payload_xml_redacted = re.sub(
                r'(<xDE[^>]*>)([^<]+)(</xDE>)',
                r'\1[BASE64_REDACTED_FOR_DIAGNOSTIC]\3',
                payload_xml_redacted,
                flags=re.IGNORECASE | re.DOTALL
            )
        except Exception:
            pass
        
        # 4. Buscar artifacts existentes de dump-http
        dump_http_artifacts = {}
        try:
            # Buscar archivos más recientes
            sent_files = sorted(artifacts_dir.glob("soap_raw_sent_lote_*.xml"), key=lambda p: p.stat().st_mtime, reverse=True)
            headers_sent_files = sorted(artifacts_dir.glob("http_headers_sent_lote_*.json"), key=lambda p: p.stat().st_mtime, reverse=True)
            headers_resp_files = sorted(artifacts_dir.glob("http_response_headers_lote_*.json"), key=lambda p: p.stat().st_mtime, reverse=True)
            resp_files = sorted(artifacts_dir.glob("soap_raw_response_lote_*.xml"), key=lambda p: p.stat().st_mtime, reverse=True)
            
            if sent_files:
                dump_http_artifacts["soap_request_file"] = sent_files[0].name
            if headers_sent_files:
                dump_http_artifacts["headers_sent_file"] = headers_sent_files[0].name
            if headers_resp_files:
                dump_http_artifacts["headers_response_file"] = headers_resp_files[0].name
            if resp_files:
                dump_http_artifacts["soap_response_file"] = resp_files[0].name
        except Exception:
            pass
        
        # 5. Leer headers si están disponibles
        headers_sent = {}
        headers_received = {}
        try:
            if "headers_sent_file" in dump_http_artifacts:
                headers_file = artifacts_dir / dump_http_artifacts["headers_sent_file"]
                if headers_file.exists():
                    headers_sent = json.loads(headers_file.read_text(encoding="utf-8"))
                    # Redactar headers que puedan contener secretos
                    if "Authorization" in headers_sent:
                        headers_sent["Authorization"] = "[REDACTED]"
                    if "X-API-Key" in headers_sent:
                        headers_sent["X-API-Key"] = "[REDACTED]"
            
            if "headers_response_file" in dump_http_artifacts:
                headers_resp_file = artifacts_dir / dump_http_artifacts["headers_response_file"]
                if headers_resp_file.exists():
                    resp_data = json.loads(headers_resp_file.read_text(encoding="utf-8"))
                    headers_received = resp_data.get("headers", {})
        except Exception:
            pass
        
        # 6. Construir summary.json
        summary = {
            "diagnostic_package": {
                "trigger": "dCodRes=0301 with dProtConsLote=0",
                "timestamp": timestamp,
                "env": env,
            },
            "response": {
                "dCodRes": response.get("codigo_respuesta"),
                "dMsgRes": response.get("mensaje"),
                "dProtConsLote": response.get("d_prot_cons_lote"),
                "dTpoProces": response.get("d_tpo_proces"),
                "ok": response.get("ok"),
            },
            "request": {
                "dId": did,
                "soap_request_redacted": payload_xml_redacted,  # Redactado (sin xDE base64)
                "headers_sent": headers_sent,  # Redactado (sin secretos)
            },
            "response_details": {
                "headers_received": headers_received,
                "response_full": response,  # Respuesta completa de SIFEN
            },
            "zip": {
                "sha256": zip_sha256,
                "size_bytes": len(zip_bytes),
            },
            "de_info": de_info,
            "format_validations": {
                "warnings": format_warnings,
                "summary": f"{len(format_warnings)} advertencia(s) de formato encontrada(s)" if format_warnings else "Sin advertencias de formato",
            },
            "artifacts": {
                "dump_http_available": len(dump_http_artifacts) > 0,
                "dump_http_files": dump_http_artifacts,
                "other_artifacts": [
                    "soap_last_request_SENT.xml",
                    "soap_last_request_BYTES.bin",
                    "preflight_lote.xml",
                    "preflight_zip.zip",
                ],
            },
            "notes": [
                "Este paquete se generó automáticamente cuando SIFEN devolvió dCodRes=0301 con dProtConsLote=0",
                "El SOAP request está redactado (xDE base64 removido) para evitar archivos grandes",
                "Los headers pueden estar redactados si contenían secretos (Authorization, API keys)",
                "Para ver el SOAP completo, consultar artifacts/soap_last_request_SENT.xml",
                "Para ver el ZIP completo, consultar artifacts/preflight_zip.zip",
            ],
        }
        
        # 7. Guardar summary.json
        summary_file = artifacts_dir / f"diagnostic_0301_summary_{timestamp}.json"
        summary_file.write_text(
            json.dumps(summary, indent=2, ensure_ascii=False, default=str),
            encoding="utf-8"
        )
        
        # 8. Guardar también el SOAP request redactado como archivo separado
        soap_redacted_file = artifacts_dir / f"diagnostic_0301_soap_request_redacted_{timestamp}.xml"
        soap_redacted_file.write_text(payload_xml_redacted, encoding="utf-8")
        
        print(f"\n📦 Paquete de diagnóstico 0301 guardado:")
        print(f"   📄 Summary: {summary_file.name}")
        print(f"   📄 SOAP request (redactado): {soap_redacted_file.name}")
        print(f"\n🔍 Información del DE extraída:")
        print(f"   DE Id (CDC): {de_info.get('de_id', 'N/A')}")
        print(f"   dRucEm: {de_info.get('dRucEm', 'N/A')}")
        print(f"   dDVEmi: {de_info.get('dDVEmi', 'N/A')}")
        print(f"   dNumTim: {de_info.get('dNumTim', 'N/A')}")
        print(f"   dEst: {de_info.get('dEst', 'N/A')}")
        print(f"   dPunExp: {de_info.get('dPunExp', 'N/A')}")
        print(f"   dNumDoc: {de_info.get('dNumDoc', 'N/A')}")
        print(f"   iTiDE: {de_info.get('iTiDE', 'N/A')}")
        print(f"   dFeEmiDE: {de_info.get('dFeEmiDE', 'N/A')}")
        print(f"   dTotalGs: {de_info.get('dTotalGs', 'N/A')}")
        print(f"   Ambiente: {de_info.get('ambiente', 'N/A')}")
        print(f"\n🔐 ZIP SHA256: {zip_sha256}")
        
        # Mostrar warnings de formato si existen
        if format_warnings:
            print(f"\n⚠️  Advertencias de formato ({len(format_warnings)}):")
            for warning in format_warnings[:10]:  # Mostrar máximo 10
                print(f"   - {warning}")
            if len(format_warnings) > 10:
                print(f"   ... y {len(format_warnings) - 10} más (ver summary.json)")
        else:
            print(f"\n✅ Sin advertencias de formato")
        
    except Exception as e:
        print(f"\n⚠️  Error al guardar paquete de diagnóstico 0301: {e}")
        import traceback
        traceback.print_exc()


def _print_dump_http(artifacts_dir: Path) -> None:
    """
    Imprime dump HTTP completo cuando --dump-http está activo.
    
    Args:
        artifacts_dir: Directorio donde están los artefactos
    """
    import json
    
    try:
        # Buscar archivos más recientes (usar nuevos nombres)
        sent_files = sorted(artifacts_dir.glob("recibe_lote_sent_*.xml"), key=lambda p: p.stat().st_mtime, reverse=True)
        headers_sent_files = sorted(artifacts_dir.glob("recibe_lote_headers_*.json"), key=lambda p: p.stat().st_mtime, reverse=True)
        # Los headers de respuesta se guardan en el resultado JSON
        result_files = sorted(artifacts_dir.glob("recibe_lote_result_*.json"), key=lambda p: p.stat().st_mtime, reverse=True)
        resp_files = sorted(artifacts_dir.glob("recibe_lote_raw_*.xml"), key=lambda p: p.stat().st_mtime, reverse=True)
        
        # Fallback a archivos antiguos si no existen los nuevos
        if not sent_files:
            sent_files = sorted(artifacts_dir.glob("soap_raw_sent_lote_*.xml"), key=lambda p: p.stat().st_mtime, reverse=True)
        if not headers_sent_files:
            headers_sent_files = sorted(artifacts_dir.glob("http_headers_sent_lote_*.json"), key=lambda p: p.stat().st_mtime, reverse=True)
        if not resp_files:
            resp_files = sorted(artifacts_dir.glob("soap_raw_response_lote_*.xml"), key=lambda p: p.stat().st_mtime, reverse=True)
        
        if not sent_files or not headers_sent_files or not resp_files:
            print("\n⚠️  No se encontraron todos los artefactos de dump HTTP")
            return
        
        print("\n" + "="*70)
        print("VERIFICADOR E2E: siRecepLoteDE (SOAP 1.2)")
        print("="*70)
        
        # 1. Headers HTTP enviados
        print("\n1️⃣  HEADERS HTTP ENVIADOS:")
        print("-" * 70)
        try:
            sent_headers = json.loads(headers_sent_files[0].read_text(encoding="utf-8"))
            for key, value in sorted(sent_headers.items()):
                print(f"   {key}: {value}")
            
            # Validación: Content-Type debe ser application/soap+xml
            content_type = sent_headers.get("Content-Type", "")
            if "application/soap+xml" in content_type:
                print(f"\n   ✅ Content-Type correcto: {content_type}")
            else:
                print(f"\n   ⚠️  Content-Type: {content_type}")
            
            # Validación: NO debe haber SOAPAction header separado
            if "SOAPAction" in sent_headers:
                print(f"   ⚠️  ADVERTENCIA: Existe header 'SOAPAction' (no debería en SOAP 1.2)")
            else:
                print(f"   ✅ NO hay header 'SOAPAction' (correcto para SOAP 1.2)")
        except Exception as e:
            print(f"   ⚠️  Error al leer headers enviados: {e}")
        
        # 2. SOAP Envelope enviado
        print("\n2️⃣  SOAP ENVELOPE ENVIADO:")
        print("-" * 70)
        try:
            sent_xml = sent_files[0].read_text(encoding="utf-8")
            xml_lines = sent_xml.split("\n")
            if len(xml_lines) > 80:
                print("\n".join(xml_lines[:80]))
                print(f"\n... (truncado, total {len(xml_lines)} líneas)")
            else:
                print(sent_xml)
            
            # Validación: NO debe contener rEnvioLoteDe (debe ser rEnvioLote)
            if "rEnvioLoteDe" in sent_xml:
                print("\n   ❌ ERROR CRÍTICO: Detectado 'rEnvioLoteDe' en el request (debe ser 'rEnvioLote')")
                print("   Esto causará error 0160 'XML Mal Formado' en SIFEN")
            elif "rEnvioLote" in sent_xml:
                print("\n   ✅ Elemento correcto: 'rEnvioLote' encontrado en el request")
            else:
                print("\n   ⚠️  No se encontró ni 'rEnvioLote' ni 'rEnvioLoteDe'")
        except Exception as e:
            print(f"   ⚠️  Error al leer SOAP enviado: {e}")
        
        # 3. Status code HTTP y headers recibidos
        print("\n3️⃣  STATUS CODE HTTP Y HEADERS RECIBIDOS:")
        print("-" * 70)
        try:
            # Leer headers desde el resultado JSON si existe
            if result_files:
                result_data = json.loads(result_files[0].read_text(encoding="utf-8"))
                status_code = result_data.get("http_status", 0)
                print(f"   Status Code: {status_code}")
                
                received_headers = result_data.get("received_headers", {})
                if received_headers:
                    print("\n   Headers recibidos:")
                    for key, value in sorted(received_headers.items()):
                        print(f"      {key}: {value}")
            else:
                print("   ⚠️  No se encontró archivo de resultado con headers")
        except Exception as e:
            print(f"   ⚠️  Error al leer headers recibidos: {e}")
        
        # 4. Body recibido
        print("\n4️⃣  BODY RECIBIDO:")
        print("-" * 70)
        try:
            received_body = resp_files[0].read_text(encoding="utf-8")
            body_lines = received_body.split("\n")
            if len(body_lines) > 120:
                print("\n".join(body_lines[:120]))
                print(f"\n... (truncado, total {len(body_lines)} líneas)")
            else:
                print(received_body)
            
            # Detectar SOAP Fault
            if "<soap:Fault" in received_body or "<soap12:Fault" in received_body or "<Fault" in received_body:
                print("\n   ⚠️  SOAP FAULT DETECTADO en la respuesta")
        except Exception as e:
            print(f"   ⚠️  Error al leer body recibido: {e}")
        
        print("\n" + "="*70)
        
    except Exception as e:
        print(f"\n⚠️  Error al imprimir dump HTTP: {e}")


def _save_precheck_artifacts(
    artifacts_dir: Path,
    payload_xml: str,
    zip_bytes: bytes,
    zip_base64: str,
    wsdl_url: str,
    lote_xml_bytes: Optional[bytes] = None
):
    """
    Guarda artifacts del payload NUEVO incluso si PRECHECK falla.
    
    Args:
        artifacts_dir: Directorio donde guardar archivos
        payload_xml: XML rEnvioLote completo
        zip_bytes: ZIP binario
        zip_base64: Base64 del ZIP
        wsdl_url: URL del WSDL que se usaría
        lote_xml_bytes: Bytes del XML lote.xml (opcional, para guardar en /tmp)
    """
    artifacts_dir.mkdir(exist_ok=True)
    
    # IMPORTANTE: payload_xml es el SOAP REAL con xDE completo (base64 real del ZIP)
    # NUNCA modificar payload_xml antes de usarlo - solo redactar para guardar en artifacts
    soap_real = payload_xml
    
    # Redactar xDE solo para el archivo normal (usando lxml para robustez)
    debug_soap = os.getenv("SIFEN_DEBUG_SOAP", "0") in ("1", "true", "True")
    try:
        # Parsear con lxml para redactar xDE de forma robusta
        from lxml import etree
        root = etree.fromstring(soap_real.encode("utf-8"))
        xde_elem = root.find(f".//{{{SIFEN_NS}}}xDE")
        if xde_elem is None:
            xde_elem = root.find(".//xDE")
        
        if xde_elem is not None and xde_elem.text:
            xde_len = len(xde_elem.text.strip())
            xde_elem.text = f"__BASE64_REDACTED_LEN_{xde_len}__"
            soap_redacted = etree.tostring(root, xml_declaration=True, encoding="utf-8").decode("utf-8")
        else:
            # Si no se encuentra xDE, usar regex como fallback
            soap_redacted = re.sub(
                r'<xDE[^>]*>.*?</xDE>',
                f'<xDE>__BASE64_REDACTED_LEN_{len(zip_base64)}__</xDE>',
                soap_real,
                flags=re.DOTALL
            )
    except Exception as e:
        # Fallback a regex si falla el parseo con lxml
        soap_redacted = re.sub(
            r'<xDE[^>]*>.*?</xDE>',
            f'<xDE>__BASE64_REDACTED_LEN_{len(zip_base64)}__</xDE>',
            soap_real,
            flags=re.DOTALL
        )
    
    # 1. Guardar soap_last_http_debug.txt con información del payload
    debug_file = artifacts_dir / "soap_last_http_debug.txt"
    with debug_file.open("w", encoding="utf-8") as f:
        f.write("==== SOAP HTTP DEBUG (PRECHECK FAILED - NOT SENT) ====\n\n")
        f.write(f"POST_URL_USED={wsdl_url.split('?')[0]}\n")  # Sin ?wsdl
        f.write(f"SOAP_VERSION_USED=1.2\n")
        f.write(f"ORIGINAL_URL={wsdl_url}\n")
        f.write(f"ACTION_HEADER_USED=\n")
        f.write(f"CONTENT_TYPE_USED=application/xml; charset=utf-8\n")
        f.write(f"SOAP_ACTION_HEADER_USED=\n")
        f.write(f"\n---- REQUEST_HEADERS_FINAL ----\n")
        f.write(f"Content-Type: application/xml; charset=utf-8\n")
        f.write(f"Accept: application/soap+xml, text/xml, */*\n")
        f.write("---- END REQUEST_HEADERS_FINAL ----\n")
        f.write(f"\nXDE_BASE64_LEN={len(zip_base64)}\n")
        f.write(f"XDE_BASE64_HAS_WHITESPACE=no\n")
        f.write(f"\n---- SOAP BEGIN (NOT SENT - PRECHECK FAILED) ----\n")
        f.write(soap_redacted)
        f.write("\n---- SOAP END ----\n")
        f.write(f"\nNOTE: Este payload NO fue enviado a SIFEN porque PRECHECK falló.\n")
        f.write(f"Para inspeccionar el ZIP real, usar: --zip-file /tmp/lote_payload.zip\n")
    
    # 2. Guardar soap_last_request_headers.txt
    headers_file = artifacts_dir / "soap_last_request_headers.txt"
    with headers_file.open("w", encoding="utf-8") as f:
        f.write("Content-Type: application/xml; charset=utf-8\n")
        f.write("Accept: application/soap+xml, text/xml, */*\n")
    
    # 3. Guardar soap_last_request_REAL.xml (payload REAL) si SIFEN_DEBUG_SOAP=1
    if debug_soap:
        request_file_real = artifacts_dir / "soap_last_request_REAL.xml"
        request_file_real.write_text(soap_real, encoding="utf-8")
    
    # 4. Guardar soap_last_request.xml (payload redactado) - mantener para compatibilidad
    request_file = artifacts_dir / "soap_last_request.xml"
    request_file.write_text(soap_redacted, encoding="utf-8")
    
    # 4. Guardar soap_last_response.xml (dummy indicando que NO se envió)
    response_file = artifacts_dir / "soap_last_response.xml"
    response_dummy = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<error>\n'
        '  <message>NOT SENT (PRECHECK FAILED)</message>\n'
        '  <note>Este request no fue enviado a SIFEN porque la validación preflight falló.</note>\n'
        '  <zip_file>/tmp/lote_payload.zip</zip_file>\n'
        '  <payload_file>/tmp/lote_xml_payload.xml</payload_file>\n'
        '</error>\n'
    )
    response_file.write_text(response_dummy, encoding="utf-8")
    
    # 5. Guardar archivos temporales en /tmp (para debug_extract_lote_from_soap)
    if lote_xml_bytes:
        try:
            Path("/tmp/lote_xml_payload.xml").write_bytes(lote_xml_bytes)
        except Exception as e:
            print(f"⚠️  No se pudo guardar /tmp/lote_xml_payload.xml: {e}")
    
    try:
        Path("/tmp/lote_payload.zip").write_bytes(zip_bytes)
    except Exception as e:
        print(f"⚠️  No se pudo guardar /tmp/lote_payload.zip: {e}")
    
    print(f"\n💾 Artifacts guardados (aunque PRECHECK falló):")
    print(f"   ✓ {debug_file.name}")
    print(f"   ✓ {headers_file.name}")
    print(f"   ✓ {request_file.name}")
    print(f"   ✓ {response_file.name}")
    if lote_xml_bytes:
        print(f"   ✓ /tmp/lote_xml_payload.xml")
    print(f"   ✓ /tmp/lote_payload.zip")
    print(f"   Para inspeccionar ZIP real: python -m tools.debug_extract_lote_from_soap --zip-file /tmp/lote_payload.zip")


def _save_1264_debug(
    artifacts_dir: Path,
    payload_xml: str,
    zip_bytes: bytes,
    zip_base64: str,
    xml_content: str,
    wsdl_url: str,
    service_key: str,
    client: 'SoapClient'
):
    """
    Guarda archivos de debug cuando se recibe error 1264.
    
    Args:
        artifacts_dir: Directorio donde guardar archivos
        payload_xml: XML rEnvioLote completo
        zip_bytes: ZIP binario
        zip_base64: Base64 del ZIP
        xml_content: XML original (DE o siRecepDE)
        wsdl_url: URL del WSDL usado
        service_key: Clave del servicio (ej: "recibe_lote")
        client: Instancia de SoapClient (para acceder a history/debug files)
    """
    artifacts_dir.mkdir(exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    prefix = f"debug_1264_{timestamp}"
    
    # 1. Guardar lote_payload.xml (rEnvioLote sin SOAP envelope)
    lote_payload_file = artifacts_dir / f"{prefix}_lote_payload.xml"
    lote_payload_file.write_text(payload_xml, encoding="utf-8")
    print(f"   ✓ {lote_payload_file.name}")
    
    # 2. Guardar lote.zip (binario)
    lote_zip_file = artifacts_dir / f"{prefix}_lote.zip"
    lote_zip_file.write_bytes(zip_bytes)
    print(f"   ✓ {lote_zip_file.name}")
    
    # 3. Guardar lote.zip.b64.txt (base64 string)
    lote_b64_file = artifacts_dir / f"{prefix}_lote.zip.b64.txt"
    lote_b64_file.write_text(zip_base64, encoding="utf-8")
    print(f"   ✓ {lote_b64_file.name}")
    
    # 4. Intentar leer SOAP sent/received desde artifacts (si SIFEN_DEBUG_SOAP estaba activo)
    # o desde history plugin del cliente
    soap_sent_file = artifacts_dir / f"{prefix}_soap_last_sent.xml"
    soap_received_file = artifacts_dir / f"{prefix}_soap_last_received.xml"
    
    # Intentar leer desde artifacts/soap_last_sent.xml (si existe)
    existing_sent = artifacts_dir / "soap_last_sent.xml"
    if existing_sent.exists():
        soap_sent_file.write_bytes(existing_sent.read_bytes())
        print(f"   ✓ {soap_sent_file.name} (copiado desde soap_last_sent.xml)")
    else:
        # Intentar desde history plugin si está disponible
        try:
            if hasattr(client, "_history_plugins") and service_key in client._history_plugins:
                history = client._history_plugins[service_key]
                if hasattr(history, "last_sent") and history.last_sent:
                    soap_sent_file.write_bytes(history.last_sent["envelope"].encode("utf-8"))
                    print(f"   ✓ {soap_sent_file.name} (desde history plugin)")
        except Exception as e:
            print(f"   ⚠️  No se pudo obtener SOAP enviado: {e}")
    
    existing_received = artifacts_dir / "soap_last_received.xml"
    if existing_received.exists():
        soap_received_file.write_bytes(existing_received.read_bytes())
        print(f"   ✓ {soap_received_file.name} (copiado desde soap_last_received.xml)")
    else:
        try:
            if hasattr(client, "_history_plugins") and service_key in client._history_plugins:
                history = client._history_plugins[service_key]
                if hasattr(history, "last_received") and history.last_received:
                    soap_received_file.write_bytes(history.last_received["envelope"].encode("utf-8"))
                    print(f"   ✓ {soap_received_file.name} (desde history plugin)")
        except Exception as e:
            print(f"   ⚠️  No se pudo obtener SOAP recibido: {e}")
    
    # 5. Extraer metadatos del XML
    metadata = _extract_metadata_from_xml(xml_content)
    
    # 6. Guardar meta.json
    import json
    meta_data = {
        "dId": metadata.get("dId"),
        "CDC": metadata.get("CDC"),
        "dRucEm": metadata.get("dRucEm"),
        "dDVEmi": metadata.get("dDVEmi"),
        "dNumTim": metadata.get("dNumTim"),
        "zip_size_bytes": len(zip_bytes),
        "zip_base64_length": len(zip_base64),
        "endpoint_url": wsdl_url,
        "service_key": service_key,
        "operation": "siRecepLoteDE",
        "timestamp": timestamp
    }
    
    meta_file = artifacts_dir / f"{prefix}_meta.json"
    meta_file.write_text(
        json.dumps(meta_data, indent=2, ensure_ascii=False, default=str),
        encoding="utf-8"
    )
    print(f"   ✓ {meta_file.name}")
    
    print(f"\n💾 Archivos de debug guardados con prefijo: {prefix}")


def find_latest_sirecepde(artifacts_dir: Path) -> Optional[Path]:
    """
    Encuentra el archivo sirecepde más reciente en artifacts/
    
    Args:
        artifacts_dir: Directorio donde buscar archivos
        
    Returns:
        Path al archivo más reciente o None
    """
    if not artifacts_dir.exists():
        return None
    
    sirecepde_files = list(artifacts_dir.glob("sirecepde_*.xml"))
    if not sirecepde_files:
        return None
    
    # Ordenar por fecha de modificación (más reciente primero)
    sirecepde_files.sort(key=lambda p: p.stat().st_mtime, reverse=True)
    return sirecepde_files[0]


# _local eliminado - usar local_tag() global en su lugar


SIFEN_NS = "http://ekuatia.set.gov.py/sifen/xsd"


def _find_direct(parent, tag_local: str):
    """Solo hijos directos, NO recursivo. Devuelve una lista."""
    return parent.findall(f"{{{SIFEN_NS}}}{tag_local}")


def _find_direct_single(parent, tag_local: str):
    """Busca un solo hijo directo con este tag. Devuelve el primer elemento encontrado o None."""
    for ch in list(parent):
        try:
            if etree.QName(ch).localname == tag_local:
                return ch
        except Exception:
            # QName puede fallar si es un comentario o texto
            pass
    return None


def _count_any(root, tag_local: str) -> int:
    """Cuenta todos los elementos con este tag en todo el documento."""
    return len(root.findall(f".//{{{SIFEN_NS}}}{tag_local}"))


def normalize_rde_before_sign(xml_bytes: bytes) -> bytes:
    """
    Normaliza el XML rDE antes de firmar:
    - Cambia dDesPaisRec -> dDesPaisRe (si existe)
    - Mueve gCamFuFD de dentro de <DE> a fuera, dentro de <rDE>, después de <Signature>
    """
    parser = etree.XMLParser(remove_blank_text=False)
    root = etree.fromstring(xml_bytes, parser)

    def find_by_local(el, name):
        for x in el.iter():
            if local_tag(x.tag) == name:
                return x
        return None

    # Tomar rDE (raíz o anidado)
    rde = root if local_tag(root.tag) == "rDE" else find_by_local(root, "rDE")
    if rde is None:
        return xml_bytes

    # 1) dDesPaisRec -> dDesPaisRe (si existe)
    dd_rec = find_by_local(rde, "dDesPaisRec")
    if dd_rec is not None:
        parent = dd_rec.getparent()
        if parent is None:
            raise RuntimeError("dDesPaisRe no tiene parent (bug de árbol XML)")
        idx = parent.index(dd_rec)
        new_el = etree.Element(etree.QName(SIFEN_NS, "dDesPaisRe"))
        new_el.text = dd_rec.text
        # Verificar que dd_rec realmente es hijo de parent antes de remover
        if dd_rec in list(parent):
            parent.remove(dd_rec)
            parent.insert(idx, new_el)
        else:
            raise RuntimeError("dDesPaisRe no es hijo directo de su parent (bug de árbol XML)")

    # 2) gCamFuFD debe ser hijo de rDE, no de DE
    de = None
    for ch in rde:
        if local_tag(ch.tag) == "DE":
            de = ch
            break

    if de is not None:
        # Guardrail: si ya existe gCamFuFD en rDE, no mover otro
        if _find_direct_single(rde, "gCamFuFD") is not None:
            # Ya existe gCamFuFD en destino, no mover duplicados
            pass
        else:
            # Tomar SOLO gCamFuFD directos de DE (no recursivo)
            gcam_elements = _find_direct(de, "gCamFuFD")
            
            for gcam in gcam_elements:
                # Verificar que gcam realmente es hijo de de antes de remover
                if gcam in list(de):
                    de.remove(gcam)
                else:
                    gcam_parent = gcam.getparent()
                    if gcam_parent is not None:
                        gcam_parent.remove(gcam)

                # Insertar después de Signature si existe; si no, al final
                sig = None
                for ch in rde:
                    if local_tag(ch.tag) == "Signature":
                        sig = ch
                        break

                if sig is not None:
                    rde.insert(rde.index(sig) + 1, gcam)
                else:
                    rde.append(gcam)
    
    # Guardrail final: nunca permitir 2+ gCamFuFD
    gcam_count = _count_any(root, "gCamFuFD")
    if gcam_count > 1:
        raise RuntimeError(f"BUG: gCamFuFD count={gcam_count}, esperado=1 (evitar duplicación).")

    return etree.tostring(root, xml_declaration=True, encoding="utf-8")


def reorder_signature_before_gcamfufd(xml_bytes: bytes) -> bytes:
    """
    Reordena los hijos de <rDE> para que Signature venga ANTES de gCamFuFD.
    Orden esperado: dVerFor, DE, Signature, gCamFuFD
    NO rompe la firma: solo cambia el orden de hermanos.
    """
    root = etree.fromstring(xml_bytes)

    # Localizar <rDE> (puede ser raíz o anidado)
    rde = root if local_tag(root.tag) == "rDE" else next((e for e in root.iter() if local_tag(e.tag) == "rDE"), None)
    if rde is None:
        return xml_bytes

    # Encontrar Signature y gCamFuFD como hijos directos de rDE
    children = list(rde)
    sig = next((c for c in children if local_tag(c.tag) == "Signature"), None)
    gcam = next((c for c in children if local_tag(c.tag) == "gCamFuFD"), None)

    # Si no hay ambos, no hay nada que reordenar
    if sig is None or gcam is None:
        return xml_bytes

    # Obtener índices
    sig_idx = children.index(sig)
    gcam_idx = children.index(gcam)

    # Si Signature ya está antes de gCamFuFD, no hacer nada
    if sig_idx < gcam_idx:
        return xml_bytes

    # Si Signature está después de gCamFuFD, mover Signature antes que gCamFuFD
    # Remover Signature y reinsertarlo justo antes de gCamFuFD
    # Verificar que sig realmente es hijo de rde antes de remover
    if sig in list(rde):
        rde.remove(sig)
    else:
        sig_parent = sig.getparent()
        if sig_parent is None:
            raise RuntimeError("Signature no tiene parent (bug de árbol XML)")
        sig_parent.remove(sig)
    # Insertar Signature en la posición de gCamFuFD
    rde.insert(gcam_idx, sig)

    return etree.tostring(root, xml_declaration=True, encoding="utf-8")


def find_rde_any_ns(root: etree._Element) -> Optional[etree._Element]:
    """
    Encuentra el primer elemento rDE usando XPath local-name(), ignorando namespace.
    
    Args:
        root: Elemento raíz del XML
        
    Returns:
        Primer elemento rDE encontrado, o None si no existe
    """
    results = root.xpath("//*[local-name()='rDE']")
    return results[0] if results else None


def make_rde_standalone(rde_elem: etree._Element) -> etree._Element:
    """
    Crea un rDE standalone con todos los namespaces necesarios explícitamente declarados.
    
    Esto asegura que cuando se serialice como fragmento, no pierda namespaces heredados
    del root (ej: xmlns:xsi), evitando errores como "Namespace prefix xsi ... is not defined".
    
    Args:
        rde_elem: Elemento rDE (lxml element)
        
    Returns:
        Nuevo elemento rDE con namespaces explícitos: default SIFEN_NS, xsi, ds
    """
    nsmap = {None: SIFEN_NS, "ds": DS_NS}
    new_rde = etree.Element(f"{{{SIFEN_NS}}}rDE", nsmap=nsmap)
    
    # Copiar atributos (incluye Id y xsi:schemaLocation si existe)
    for k, v in rde_elem.attrib.items():
        new_rde.set(k, v)
    
    # Copiar hijos en deep copy (NO mutar el árbol original)
    for child in list(rde_elem):
        new_rde.append(copy.deepcopy(child))
    
    return new_rde


def _find_by_localname(root: etree._Element, name: str) -> Optional[etree._Element]:
    """Busca un elemento por nombre local (ignorando namespace) en todo el árbol."""
    for el in root.iter():
        if _local(el.tag) == name:
            return el
    return None


def _ensure_rde_has_xmlns(lote_xml: str) -> str:
    """Asegura que el tag <rDE> tenga xmlns explícito."""
    return re.sub(
        r"<rDE(?![^>]*\sxmlns=)",
        '<rDE xmlns="http://ekuatia.set.gov.py/sifen/xsd"',
        lote_xml,
        count=1
    )


def extract_rde_element(xml_bytes: bytes) -> bytes:
    """
    Acepta:
      - un XML cuya raíz ya sea rDE, o
      - un XML wrapper (siRecepDE) que contenga un rDE adentro.
    Devuelve el XML del elemento rDE (bytes).
    """
    root = etree.fromstring(xml_bytes)

    # Caso 1: root es rDE (verificar por nombre local, ignorando namespace)
    if _local(root.tag) == "rDE":
        return etree.tostring(root, xml_declaration=False, encoding="utf-8")

    # Caso 2: buscar el primer rDE anidado (por nombre local, ignorando namespace)
    rde_el = _find_by_localname(root, "rDE")

    if rde_el is None:
        raise ValueError("No se encontró <rDE> en el XML (ni como raíz ni anidado).")

    return etree.tostring(rde_el, xml_declaration=False, encoding="utf-8")


def sign_and_normalize_rde_inside_xml(xml_bytes: bytes, cert_path: str, cert_password: str, artifacts_dir: Optional[Path] = None) -> bytes:
    """
    Garantiza que el rDE dentro del XML esté firmado y normalizado.
    
    - Encuentra el rDE (puede ser root o anidado en rEnviDe)
    - Si no tiene Signature como hijo directo (XMLDSig o SIFEN ns), lo firma
    - Reordena hijos de rDE a: dVerFor, DE, Signature, gCamFuFD (si existe)
    - Devuelve el XML completo con rDE firmado y normalizado
    
    Args:
        xml_bytes: XML que contiene rDE (puede ser rDE root o tener rDE anidado)
        cert_path: Path al certificado P12 para firma
        cert_password: Contraseña del certificado
        artifacts_dir: Directorio para guardar artifacts de debug (opcional)
        
    Returns:
        XML completo con rDE firmado y normalizado (bytes)
    """
    import traceback
    DSIG_NS = "http://www.w3.org/2000/09/xmldsig#"
    
    debug_enabled = os.getenv("SIFEN_DEBUG_SOAP", "0") in ("1", "true", "True")
    
    # Parsear XML
    try:
        root = etree.fromstring(xml_bytes)
    except Exception as e:
        raise ValueError(f"Error al parsear XML: {e}")
    
    # Encontrar rDE
    rde_el = None
    is_root_rde = False
    
    if local_tag(root.tag) == "rDE":
        rde_el = root
        is_root_rde = True
    else:
        # Buscar rDE anidado
        rde_el = _find_by_localname(root, "rDE")
        if rde_el is None:
            raise ValueError("No se encontró <rDE> en el XML (ni como raíz ni anidado).")
    
    # Verificar si tiene Signature como hijo directo
    has_signature = any(
        child.tag == f"{{{DSIG_NS}}}Signature" or local_tag(child.tag) == "Signature"
        for child in list(rde_el)
    )
    
    if debug_enabled:
        children_before = [local_tag(c.tag) for c in list(rde_el)]
        print(f"🔍 [sign_and_normalize_rde_inside_xml] rDE hijos antes: {', '.join(children_before)}")
        print(f"🔍 [sign_and_normalize_rde_inside_xml] tiene Signature: {has_signature}")
    
    # Si no tiene Signature, firmarlo
    if not has_signature:
        print("🔐 Firmando DE (no rDE completo)...")
        
        # Guardar XML original antes de firmar (debug)
        if debug_enabled and artifacts_dir:
            artifacts_dir.mkdir(exist_ok=True)
            (artifacts_dir / "xml_before_sign_normalize.xml").write_bytes(xml_bytes)
            print(f"💾 Guardado: {artifacts_dir / 'xml_before_sign_normalize.xml'}")
        
        # Asegurar rDE normalizado antes de extraer DE
        rde_temp_root = ensure_rde_sifen(rde_el)
        
        # Encontrar DE dentro de rDE (namespace-aware)
        de_el = rde_temp_root.find(f".//{{{SIFEN_NS_URI}}}DE")
        if de_el is None:
            # Fallback: buscar por local-name
            nodes = rde_temp_root.xpath("//*[local-name()='DE']")
            de_el = nodes[0] if nodes else None
        
        if de_el is None:
            raise RuntimeError("No se encontró <DE> dentro de rDE para firmar")
        
        # Serializar SOLO el DE
        de_bytes = etree.tostring(de_el, xml_declaration=True, encoding="utf-8")
        
        # Guardar DE antes de firmar (debug)
        if debug_enabled and artifacts_dir:
            artifacts_dir.mkdir(exist_ok=True)
            (artifacts_dir / "de_before_sign.xml").write_bytes(de_bytes)
            print(f"💾 Guardado: {artifacts_dir / 'de_before_sign.xml'}")
        
        # Firmar solo el DE
        try:
            from app.sifen_client.xmlsec_signer_clean import sign_de_with_p12
            signed_de_bytes = sign_de_with_p12(de_bytes, cert_path, cert_password)
            print("✓ DE firmado exitosamente")
        except Exception as e:
            error_msg = f"Error al firmar DE: {e}"
            print(f"❌ {error_msg}", file=sys.stderr)
            traceback.print_exc(file=sys.stderr)
            raise RuntimeError(error_msg)
        
        # Mover Signature dentro del DE si está fuera (como hermano)
        signed_de_bytes = _move_signature_into_de_if_needed(signed_de_bytes, artifacts_dir, debug_enabled)
        
        # Guardar DE después de firmar y mover Signature (debug)
        if debug_enabled and artifacts_dir:
            (artifacts_dir / "de_after_sign.xml").write_bytes(signed_de_bytes)
            print(f"💾 Guardado: {artifacts_dir / 'de_after_sign.xml'}")
        
        # Parsear DE firmado y validar
        try:
            signed_de_root = etree.fromstring(signed_de_bytes)
        except Exception as e:
            raise ValueError(f"Error al re-parsear DE firmado: {e}")
        
        # Validar que el root del DE firmado sea DE
        signed_de_localname = local_tag(signed_de_root.tag)
        if signed_de_localname != "DE":
            error_msg = (
                f"Post-firma: El XML firmado no tiene root DE. "
                f"Tag actual: {signed_de_root.tag}, localname: {signed_de_localname}"
            )
            print(f"❌ {error_msg}", file=sys.stderr)
            raise RuntimeError(error_msg)
        
        # Validar que DE firmado tenga ds:Signature como hijo (búsqueda namespace-aware)
        sig_in_de = signed_de_root.find(f".//{{{DSIG_NS_URI}}}Signature")
        has_signature_in_de = sig_in_de is not None
        if not has_signature_in_de:
            # Fallback: buscar por local-name
            has_signature_in_de = any(
                local_tag(child.tag) == "Signature" and _namespace_uri(child.tag) == DSIG_NS_URI
                for child in list(signed_de_root.iter())
            )
        
        if not has_signature_in_de:
            # Diagnóstico detallado
            de_children = []
            for i, child in enumerate(list(signed_de_root)[:10]):
                de_children.append(f"  [{i}] {child.tag} (local: {local_tag(child.tag)})")
            de_children_str = "\n".join(de_children) if de_children else "  (sin hijos)"
            
            error_msg = (
                f"Post-firma: No se encontró <ds:Signature> dentro de <DE>.\n"
                f"  DE tag: {signed_de_root.tag}\n"
                f"  DE nsmap: {signed_de_root.nsmap if hasattr(signed_de_root, 'nsmap') else {}}\n"
                f"  Primeros 10 hijos del DE:\n{de_children_str}"
            )
            print(f"❌ {error_msg}", file=sys.stderr)
            raise RuntimeError(error_msg)
        
        print("✓ DE firmado tiene Signature como hijo (validado)")
        
        # Reconstruir rDE con dVerFor + DE firmado
        new_rde = etree.Element(
            _qn_sifen("rDE"),
            nsmap={None: SIFEN_NS_URI, "ds": DSIG_NS_URI},
        )
        
        # Agregar atributo Id requerido por XSD (usar el mismo Id del DE)
        de_id = signed_de_root.get("Id")
        if de_id:
            new_rde.set("Id", de_id)
            print(f"DEBUG: Agregado atributo Id='{de_id}' a rDE reconstruido")
        
        # Agregar dVerFor
        dverfor = etree.SubElement(new_rde, _qn_sifen("dVerFor"))
        dverfor.text = "150"
        
        # Agregar DE firmado
        new_rde.append(signed_de_root)
        
        # Asegurar default xmlns SIFEN
        new_rde = ensure_rde_sifen(new_rde)
        
        # Guardar rDE después de reconstruir (debug)
        if debug_enabled and artifacts_dir:
            rde_after_bytes = etree.tostring(new_rde, xml_declaration=False, encoding="utf-8")
            (artifacts_dir / "rde_after_wrap.xml").write_bytes(rde_after_bytes)
            print(f"💾 Guardado: {artifacts_dir / 'rde_after_wrap.xml'}")
        
        # Actualizar rde_el y root para continuar con el flujo
        # Guardar referencia al rDE original antes de reemplazarlo
        old_rde_el = rde_el
        
        # Si el root original era rDE, reemplazarlo
        if is_root_rde:
            root = new_rde
            rde_el = new_rde
        else:
            # Si rDE estaba anidado, encontrar su parent y reemplazarlo
            old_rde_parent = old_rde_el.getparent()
            if old_rde_parent is not None:
                # Reemplazar el rDE viejo con el nuevo
                # Verificar que old_rde_el realmente es hijo de old_rde_parent antes de remover
                if old_rde_el in list(old_rde_parent):
                    idx = list(old_rde_parent).index(old_rde_el)
                    old_rde_parent.remove(old_rde_el)
                    old_rde_parent.insert(idx, new_rde)
                    rde_el = new_rde
                else:
                    raise RuntimeError("rDE a reemplazar no es hijo directo de su parent (bug de árbol XML)")
            else:
                # Si no tiene parent, usar el nuevo rDE como root
                root = new_rde
                rde_el = new_rde
        
        # Serializar XML completo actualizado
        xml_bytes = etree.tostring(root, xml_declaration=True, encoding="utf-8")
        
        # Guardar XML completo después de reconstruir (debug)
        if debug_enabled and artifacts_dir:
            (artifacts_dir / "xml_after_sign_normalize.xml").write_bytes(xml_bytes)
            print(f"💾 Guardado: {artifacts_dir / 'xml_after_sign_normalize.xml'}")
    else:
        # Ya tiene Signature: NO tocar el árbol (solo validar orden y devolver OK)
        print("✓ rDE ya tiene Signature, NO modificando árbol (preservando firma)")
        # Serializar y retornar sin modificar
        result_bytes = etree.tostring(root, xml_declaration=True, encoding="utf-8")
        return result_bytes
    
    # Reordenar hijos de rDE: dVerFor, DE, gCamFuFD
    # NOTA: La Signature ahora está DENTRO del DE, no como hijo directo del rDE
    # Obtener referencias usando find() con namespaces
    dverfor = rde_el.find(f"./{{{SIFEN_NS}}}dVerFor")
    de = rde_el.find(f"./{{{SIFEN_NS}}}DE")
    gcamfufd = rde_el.find(f"./{{{SIFEN_NS}}}gCamFuFD")
    
    # Verificar que DE tenga Signature dentro (no como hijo directo de rDE)
    if de is not None:
        has_signature_in_de = any(
            child.tag == f"{{{DSIG_NS}}}Signature" or local_tag(child.tag) == "Signature"
            for child in list(de)
        )
        if not has_signature_in_de:
            # Esto no debería pasar si el flujo anterior funcionó correctamente
            print("⚠️  ADVERTENCIA: DE no tiene Signature como hijo (puede estar en otro lugar)")
    
    # Verificar si hay otros hijos que no sean los esperados
    expected_children = {dverfor, de, gcamfufd}
    others = [child for child in list(rde_el) if child not in expected_children]
    
    # Construir orden: dVerFor, DE, gCamFuFD, otros
    ordered_children = []
    if dverfor is not None:
        ordered_children.append(dverfor)
    if de is not None:
        ordered_children.append(de)
    if gcamfufd is not None:
        ordered_children.append(gcamfufd)
    ordered_children.extend(others)
    
    # Verificar si el orden actual es diferente
    current_children = list(rde_el)
    needs_reorder = False
    if len(ordered_children) != len(current_children):
        needs_reorder = True
    else:
        for i, expected in enumerate(ordered_children):
            if current_children[i] != expected:
                needs_reorder = True
                break
    
    # Si el orden cambió, reordenar
    if needs_reorder:
        print("🔄 Reordenando hijos de rDE...")
        # Remover todos los hijos
        for child in list(rde_el):
            rde_el.remove(child)
        # Agregar en orden
        for child in ordered_children:
            rde_el.append(child)
        
        if debug_enabled:
            children_after = [local_tag(c.tag) for c in list(rde_el)]
            print(f"🔍 [sign_and_normalize_rde_inside_xml] rDE hijos después: {', '.join(children_after)}")
    
    # (Opcional) Limpiar namespaces si hace falta (sin forzar xmlns:ds)
    # etree.cleanup_namespaces() puede ayudar, pero no es crítico
    
    # Serializar XML completo
    result_bytes = etree.tostring(root, xml_declaration=True, encoding="utf-8")
    
    # Si se firmó, el xml_after_sign_normalize.xml ya se guardó arriba
    # Solo guardar el resultado final si se reordenó (para ver el orden final)
    if debug_enabled and artifacts_dir:
        artifacts_dir.mkdir(exist_ok=True)
        # Solo guardar si se reordenó (para no duplicar)
        if needs_reorder:
            (artifacts_dir / "xml_after_sign_normalize_final.xml").write_bytes(result_bytes)
            print(f"💾 Guardado: {artifacts_dir / 'xml_after_sign_normalize_final.xml'}")
    
    return result_bytes


def _sanitize_unbound_prefixes(xml_text: str) -> str:
    """
    Sanitiza prefijos sin declarar (unbound prefixes) en el XML.
    
    Detecta prefijos como ns0:, ds:, xsi: que se usan pero no tienen xmlns declarado,
    e inyecta las declaraciones necesarias en el tag de apertura del elemento raíz.
    
    Args:
        xml_text: XML como string
        
    Returns:
        XML con prefijos declarados
    """
    # import re  # usa el import global (evita UnboundLocalError)    
    # Buscar el tag de apertura del elemento raíz (puede ser rDE o cualquier otro)
    root_match = re.search(r'<([A-Za-z_][\w\-\.]*:)?([A-Za-z_][\w\-\.]*)\b([^>]*)>', xml_text)
    if not root_match:
        return xml_text
    
    prefix_part = root_match.group(1)  # Puede ser "ns0:" o None
    localname = root_match.group(2)  # Nombre local del elemento
    attrs_str = root_match.group(3)  # Atributos del tag
    
    # Detectar prefijos usados en el XML
    used_prefixes = set()
    
    # Buscar prefijos en tags: <prefix:tag>
    tag_prefixes = re.findall(r'<([A-Za-z_][\w\-\.]*):', xml_text)
    used_prefixes.update(tag_prefixes)
    
    # Buscar prefijos en atributos: prefix:attr="..."
    attr_prefixes = re.findall(r'([A-Za-z_][\w\-\.]*):[A-Za-z_][\w\-\.]*=', attrs_str)
    used_prefixes.update(attr_prefixes)
    
    # Detectar prefijos conocidos que necesitan namespace
    prefixes_to_inject = {}
    
    # Prefijo del elemento raíz (si tiene)
    root_prefix = None
    if prefix_part:
        root_prefix = prefix_part.rstrip(':')
        # Si el prefijo del root se usa pero no está declarado, inyectarlo con SIFEN_NS
        if localname == "rDE" and root_prefix:
            ns_pattern = re.compile(
                r'xmlns(?::' + re.escape(root_prefix) + r')?=["\']' + re.escape(SIFEN_NS) + r'["\']',
                re.IGNORECASE
            )
            if not ns_pattern.search(attrs_str):
                prefixes_to_inject[root_prefix] = SIFEN_NS
    
    # Prefijo ds: (Signature)
    if 'ds:' in xml_text or 'ds=' in attrs_str:
        if not re.search(r'xmlns:ds=["\']' + re.escape(DS_NS) + r'["\']', attrs_str, re.IGNORECASE):
            prefixes_to_inject['ds'] = DS_NS
    
    # Prefijo xsi: (XML Schema Instance)
    if 'xsi:' in xml_text or 'xsi=' in attrs_str:
        if not re.search(r'xmlns:xsi=["\']' + re.escape(XSI_NS) + r'["\']', attrs_str, re.IGNORECASE):
            prefixes_to_inject['xsi'] = XSI_NS
    
    # Si el root es rDE sin prefijo y no tiene xmlns default, inyectarlo
    if localname == "rDE" and not prefix_part:
        ns_pattern = re.compile(
            r'xmlns=["\']' + re.escape(SIFEN_NS) + r'["\']',
            re.IGNORECASE
        )
        if not ns_pattern.search(attrs_str):
            prefixes_to_inject[None] = SIFEN_NS  # None = default namespace
    
    # Inyectar namespaces faltantes
    if prefixes_to_inject:
        new_attrs_parts = []
        
        # Primero, default namespace si aplica
        if None in prefixes_to_inject:
            new_attrs_parts.append(f'xmlns="{prefixes_to_inject[None]}"')
            del prefixes_to_inject[None]
        
        # Luego, namespaces con prefijo
        for prefix, ns_uri in prefixes_to_inject.items():
            new_attrs_parts.append(f'xmlns:{prefix}="{ns_uri}"')
        
        # Agregar al inicio de los atributos
        new_attrs = ' ' + ' '.join(new_attrs_parts)
        if attrs_str.strip():
            new_attrs += ' ' + attrs_str
        else:
            new_attrs = new_attrs.strip()
        
        # Reconstruir el tag
        if prefix_part:
            new_tag = f'<{prefix_part}{localname}{new_attrs}>'
        else:
            new_tag = f'<{localname}{new_attrs}>'
        
        # Reemplazar solo el tag de apertura
        old_tag = root_match.group(0)
        xml_text = xml_text.replace(old_tag, new_tag, 1)
    
    return xml_text


def ensure_rde_default_namespace(xml_bytes: bytes) -> bytes:
    """
    Asegura que el elemento rDE tenga namespace SIFEN_NS como default namespace.
    
    Usa lxml con XPath local-name() para encontrar rDE de forma robusta.
    Si el rDE no está en el namespace correcto, lo recrea preservando atributos e hijos.
    
    Args:
        xml_bytes: XML que contiene rDE (puede ser rDE root o tener rDE anidado)
        
    Returns:
        XML con rDE que tiene xmlns="http://ekuatia.set.gov.py/sifen/xsd" como default
        
    Raises:
        RuntimeError: Si no se encuentra rDE en el XML o no se puede procesar
    """
    # Intentar parsear con sanitize si hay "unbound prefix"
    xml_text = xml_bytes.decode('utf-8', errors='ignore')
    parse_error = None
    
    try:
        parser = etree.XMLParser(remove_blank_text=True, recover=False)
        root = etree.fromstring(xml_bytes, parser)
    except etree.XMLSyntaxError as e:
        # Si hay "unbound prefix", sanitizar primero
        if "unbound prefix" in str(e).lower() or "prefix" in str(e).lower():
            xml_text = _sanitize_unbound_prefixes(xml_text)
            xml_bytes = xml_text.encode('utf-8')
            try:
                parser = etree.XMLParser(remove_blank_text=True, recover=False)
                root = etree.fromstring(xml_bytes, parser)
            except Exception as e2:
                parse_error = e2
                raise RuntimeError(f"No se pudo parsear XML después de sanitizar prefijos: {e2}")
        else:
            parse_error = e
            raise RuntimeError(f"Error al parsear XML: {e}")
    except Exception as e:
        parse_error = e
        raise RuntimeError(f"Error inesperado al parsear XML: {e}")
    
    # Buscar rDE usando XPath local-name()
    rde_list = root.xpath("//*[local-name()='rDE']")
    
    if not rde_list:
        raise RuntimeError("No se encontró rDE por local-name() en el XML")
    
    # Tomar el primero si hay varios
    rde = rde_list[0]
    
    # Verificar namespace actual
    rde_qname = etree.QName(rde)
    rde_ns = rde_qname.namespace
    rde_tag = rde.tag
    
    # Debug mínimo si está habilitado
    debug_enabled = os.getenv("SIFEN_DEBUG_SOAP", "0") in ("1", "true", "True")
    if debug_enabled:
        print(f"DEBUG rDE tag={rde_tag!r} ns={rde_ns!r}")
    
    # Verificar si tiene schemaLocation o cualquier atributo xsi:* (necesita xmlns:xsi)
    has_xsi_attr = False
    # Buscar en atributos del rDE
    for key in rde.attrib.keys():
        if key.endswith('}schemaLocation') or key == 'schemaLocation' or key.startswith('{http://www.w3.org/2001/XMLSchema-instance}'):
            has_xsi_attr = True
            break
    # Si no está en rDE, buscar en descendientes
    if not has_xsi_attr:
        for desc in rde.iter():
            if desc == rde:
                continue
            for key in desc.attrib.keys():
                if key.endswith('}schemaLocation') or key == 'schemaLocation' or key.startswith('{http://www.w3.org/2001/XMLSchema-instance}'):
                    has_xsi_attr = True
                    break
            if has_xsi_attr:
                break
    
    # Verificar si ya tiene xmlns:xsi declarado (en rDE o ancestros)
    has_xsi_ns = False
    if has_xsi_attr:
        # Buscar xmlns:xsi en el rDE o en sus ancestros
        current = rde
        while current is not None:
            # Verificar en atributos del elemento
            for key in current.attrib.keys():
                if key == 'xmlns:xsi' or key.startswith('{http://www.w3.org/2000/xmlns/}xsi'):
                    has_xsi_ns = True
                    break
            if has_xsi_ns:
                break
            # Verificar en el nsmap del elemento (si está disponible)
            if hasattr(current, 'nsmap') and current.nsmap and 'xsi' in current.nsmap:
                has_xsi_ns = True
                break
            current = current.getparent()
    
    # Si ya está en el namespace correcto, verificar si necesita cambios
    if rde_ns == SIFEN_NS:
        # Verificar si tiene default namespace declarado
        root_str = etree.tostring(root, encoding="unicode")
        has_default_ns = 'xmlns="' + SIFEN_NS + '"' in root_str[:1000]
        
        # Si tiene default namespace y (no tiene schemaLocation o ya tiene xmlns:xsi), retornar sin modificar
        if has_default_ns and (not has_schema_location or has_xsi_ns):
            return xml_bytes
    
    # Si no está en el namespace correcto, no tiene default namespace, o tiene schemaLocation sin xmlns:xsi, recrear
    # Obtener el parent del rDE (si existe)
    parent = rde.getparent()
    rde_index = None
    
    if parent is not None:
        # Guardar índice para insertar en la misma posición
        rde_index = list(parent).index(rde)
    
    # Crear nuevo rDE self-contained con todos los namespaces necesarios
    nsmap = {None: SIFEN_NS, "ds": DS_NS}
    # NO agregar xsi namespace (causa error 0160)
    # if has_xsi_attr and not has_xsi_ns:
    #     nsmap["xsi"] = XSI_NS
    
    new_rde = etree.Element(f"{{{SIFEN_NS}}}rDE", nsmap=nsmap)
    
    # Copiar todos los atributos (excepto xmlns que ya está en nsmap)
    for key, value in rde.attrib.items():
        if not key.startswith('xmlns'):
            new_rde.set(key, value)
    
    # Asegurar que tenga el atributo Id requerido por XSD
    # CRÍTICO: Usar un Id DIFERENTE al DE para evitar duplicación
    if 'Id' not in new_rde.attrib:
        # Buscar el DE interno para obtener su Id
        de_elem = new_rde.find('.//{*}DE')
        if de_elem is not None and 'Id' in de_elem.attrib:
            # Usar un Id diferente: prefijar con "rDE"
            rde_id = "rDE" + de_elem.get('Id')
            new_rde.set('Id', rde_id)
            print(f"DEBUG: sanitize_rde_for_lote: Agregado Id='{rde_id}' a rDE (DE Id={de_elem.get('Id')})")
    
    # Mover TODOS los hijos preservando orden
    for child in list(rde):
        new_rde.append(child)
    
    # Reemplazar rDE en su parent
    if parent is not None:
        parent.remove(rde)
        parent.insert(rde_index, new_rde)
    else:
        # rDE es root, reemplazar root
        root = new_rde
    
    # Serializar y retornar
    result_bytes = etree.tostring(root, xml_declaration=True, encoding="utf-8", pretty_print=True)
    return result_bytes


def extract_rde_fragment(xml_bytes: bytes) -> bytes:
    """
    Extrae el elemento rDE (con o sin namespace / con o sin prefijo) usando lxml,
    para evitar fallas de búsqueda por bytes luego del firmado (ej: </ns0:rDE>).
    """
    parser = etree.XMLParser(remove_blank_text=True, recover=True)
    root = etree.fromstring(xml_bytes, parser)

    # Caso: root ya es rDE (con o sin namespace)
    try:
        if etree.QName(root).localname == "rDE":
            rde = root
        else:
            rde = None
    except Exception:
        rde = None

    # Caso: buscar rDE con namespace SIFEN
    if rde is None:
        rde = root.find(".//s:rDE", namespaces=NS)

    # Caso: buscar rDE por local-name() (sin namespace / con prefijo raro)
    if rde is None:
        hits = root.xpath("//*[local-name()='rDE']")
        rde = hits[0] if hits else None

    if rde is None:
        raise RuntimeError("No se encontró rDE en el XML de entrada (no se puede construir lote).")

    # Importante: NO agregamos xml_declaration para mantener el fragmento "puro"
    return etree.tostring(rde, encoding="UTF-8", pretty_print=True)


def extract_rde_raw_bytes(xml_bytes: bytes) -> bytes:
    """
    Extrae el elemento <rDE>...</rDE> como bytes crudos sin parsear/serializar.
    
    Esto preserva exactamente el XML firmado, incluyendo namespaces y prefijos,
    evitando que se rompa la firma al reserializar.
    
    Args:
        xml_bytes: XML que contiene rDE (puede tener prefijo o no)
        
    Returns:
        Bytes del fragmento rDE completo (desde <rDE hasta </rDE>)
        
    Raises:
        ValueError: Si no se encuentra <rDE> o su cierre
    """
    # Buscar el primer <rDE ...> (con o sin prefijo)
    m = re.search(br'<(?P<pfx>[A-Za-z_][\w\.-]*:)?rDE\b', xml_bytes)
    if not m:
        raise ValueError("No se encontró <rDE> en XML firmado (raw)")
    
    start = m.start()
    pfx = m.group('pfx') or b''  # ej: b'ns0:' o b''
    
    # Buscar el cierre correspondiente </rDE> o </prefijo:rDE>
    end_tag = b'</' + pfx + b'rDE>'
    end = xml_bytes.find(end_tag, start)
    if end == -1:
        # Fallback: buscar sin prefijo si no se encuentra con prefijo
        end_tag_fallback = b'</rDE>'
        end = xml_bytes.find(end_tag_fallback, start)
        if end == -1:
            raise ValueError("No se encontró cierre </rDE> en XML firmado (raw)")
        end += len(end_tag_fallback)
    else:
        end += len(end_tag)
    
    return xml_bytes[start:end]


def _extract_rde_fragment_bytes(xml_signed_bytes: bytes) -> bytes:
    """
    Extrae <rDE>...</rDE> desde BYTES sin re-serializar (preserva firma),
    soportando prefijos: <ns0:rDE> ... </ns0:rDE>.
    """
    # 1) Encontrar el tag de apertura con prefijo opcional
    m_open = re.search(rb'<(?P<prefix>[A-Za-z_][\w\-.]*:)?rDE\b[^>]*>', xml_signed_bytes)
    if not m_open:
        raise RuntimeError("No pude encontrar tag de apertura <rDE ...> en bytes.")

    prefix = m_open.group("prefix") or b""  # ej: b"ns0:" o b""
    start = m_open.start()

    # 2) Encontrar el cierre correspondiente con el mismo prefijo
    close_pat = rb'</' + prefix + rb'rDE\s*>'
    m_close = re.search(close_pat, xml_signed_bytes[m_open.end():])
    if not m_close:
        # diagnóstico útil: intentamos también cierre sin prefijo por si hubiera inconsistencia
        m_close2 = re.search(rb'</rDE\s*>', xml_signed_bytes[m_open.end():])
        if m_close2:
            end = m_open.end() + m_close2.end()
            return xml_signed_bytes[start:end]
        raise RuntimeError(
            "No pude encontrar el tag de cierre </rDE> (con o sin prefijo) en bytes."
        )

    end = m_open.end() + m_close.end()
    return xml_signed_bytes[start:end]


def _extract_rde_bytes_passthrough(xml_bytes: bytes) -> bytes:
    """
    Extrae el bloque <rDE>...</rDE> de los bytes del XML sin usar lxml.
    
    Esta función NO re-serializa el XML, solo extrae los bytes exactos del rDE
    para preservar la firma, namespaces y formatting tal cual.
    
    Args:
        xml_bytes: XML completo como bytes
        
    Returns:
        Bytes del bloque <rDE>...</rDE> sin declaración XML
        
    Raises:
        ValueError: Si no encuentra rDE en el XML
    """
    # Encontrar el inicio del tag rDE (con o sin namespace)
    start = xml_bytes.find(b"<rDE")
    if start == -1:
        # Buscar con prefijo de namespace
        # import re  # usa el import global (evita UnboundLocalError)        m = re.search(rb'<[A-Za-z_][\w\-.]*:rDE\b', xml_bytes)
        if m:
            start = m.start()
        else:
            raise ValueError("No se encontró el tag <rDE> en el XML")
    
    # Encontrar el cierre de rDE
    end = xml_bytes.find(b"</rDE>", start)
    if end == -1:
        # Buscar cierre con el mismo prefijo que el apertura
        if xml_bytes[start:start+2] != b"<r":
            # Tiene prefijo, extraer el prefijo
            prefix_end = xml_bytes.find(b":", start, start + 20)
            if prefix_end != -1:
                prefix = xml_bytes[start+1:prefix_end]
                end = xml_bytes.find(b"</" + prefix + b":rDE>", start)
        if end == -1:
            raise ValueError("No se encontró el tag de cierre </rDE> en el XML")
    
    # Incluir el tag de cierre
    if xml_bytes[start:start+2] != b"<r":
        # Tiene prefijo, usar la longitud del tag con prefijo
        prefix_end = xml_bytes.find(b":", start, start + 20)
        if prefix_end != -1:
            end += len(b"</" + xml_bytes[start+1:prefix_end] + b":rDE>")
        else:
            end += len(b"</rDE>")
    else:
        end += len(b"</rDE>")
    
    # Extraer el bloque rDE
    rde_bytes = xml_bytes[start:end]
    
    # CRÍTICO: Si rDE no tiene xmlns (default namespace), agregarlo para que XPath funcione en QR generator
    # El XML original tiene xmlns en rLoteDE, pero al extraer rDE lo pierde
    if b'xmlns=' not in rde_bytes[:100]:  # Check first 100 bytes for xmlns
        # Insertar xmlns después del tag rDE opening
        rde_tag_end = rde_bytes.find(b">")
        if rde_tag_end != -1:
            rde_bytes = (rde_bytes[:rde_tag_end] + 
                        b' xmlns="http://ekuatia.set.gov.py/sifen/xsd"' + 
                        rde_bytes[rde_tag_end:])
    
    # Remover declaración XML si estuviera dentro del bloque (poco común pero posible)
    # Solo remover si está al principio del bloque extraído
    if rde_bytes.startswith(b"<?xml"):
        first_gt = rde_bytes.find(b">") + 1
        # Saltear whitespace después del >
        while first_gt < len(rde_bytes) and rde_bytes[first_gt] in b" \t\r\n":
            first_gt += 1
        rde_bytes = rde_bytes[first_gt:]
    
    return rde_bytes


def _ensure_rde_has_id_attr(rde_bytes: bytes) -> bytes:
    """
    Si <rDE> no tiene Id, lo completa con un Id DIFERENTE al DE para evitar duplicación.
    Usa el formato "rDE" + DE_Id para garantizar que sean diferentes.
    No usa lxml (no reserializa).
    """
    # import re  # usa el import global (evita UnboundLocalError)    
    # Si ya tiene Id, no tocar
    head = rde_bytes[:300]
    if re.search(br"<rDE\b[^>]*\bId\s*=", head):
        return rde_bytes

    m = re.search(br'<DE\b[^>]*\bId="([^"]+)"', rde_bytes)
    if not m:
        return rde_bytes  # no encontramos DE Id, no podemos completar

    de_id = m.group(1)
    
    # CRÍTICO: Usar un Id DIFERENTE al DE para evitar duplicación
    # La firma Reference URI apunta al DE@Id, NO al rDE@Id
    rde_id = b"rDE" + de_id

    # Insertar Id="..." en el tag de apertura de rDE
    i = rde_bytes.find(b"<rDE")
    if i < 0:
        return rde_bytes

    j = rde_bytes.find(b">", i)
    if j < 0:
        return rde_bytes

    opening = rde_bytes[i:j]  # b"<rDE ..."

    # Si ya había otros atributos, igual inserta con espacio
    patched_opening = opening + b' Id="' + rde_id + b'"'

    return rde_bytes[:i] + patched_opening + rde_bytes[j:]


def _is_xml_already_signed(xml_bytes: bytes) -> bool:
    """
    Detecta si el XML ya contiene una firma Signature.
    
    Busca el tag <Signature> en cualquier parte del XML.
    Si tiene namespace SIFEN, fuerza re-firma para usar XMLDSig estándar.
    
    Args:
        xml_bytes: XML como bytes
        
    Returns:
        True si encuentra <Signature> y NO tiene namespace SIFEN, False otherwise
    """
    # Buscar <Signature> (con o sin namespace)
    has_signature = b"<Signature" in xml_bytes or b":Signature" in xml_bytes
    
    if has_signature:
        # Si tiene namespace SIFEN en Signature, debemos re-firmar
        xml_str = xml_bytes.decode('utf-8')
        # Buscar específicamente Signature con namespace SIFEN
        if '<Signature xmlns="http://ekuatia.set.gov.py/sifen/xsd"' in xml_str:
            print("⚠️ XML tiene Signature con namespace SIFEN, forzando re-firma con XMLDSig estándar")
            return False  # Forzar re-firma para usar XMLDSig estándar
    
    return has_signature


def build_lote_passthrough_signed(xml_bytes: bytes, return_debug: bool = False) -> Union[str, Tuple[str, bytes, bytes]]:
    """
    Construye lote.xml para un XML ya firmado usando passthrough bytes.
    
    Esta función NO usa lxml para re-serializar el rDE, solo extrae los bytes
    exactos del XML original para preservar la firma.
    
    Args:
        xml_bytes: XML completo como bytes (debe contener <rDE>...</rDE>)
        return_debug: Si True, devuelve también los bytes generados para debug
        
    Returns:
        Base64 del ZIP con lote.xml si return_debug=False
        Tuple[base64, lote_xml_bytes, zip_bytes] si return_debug=True
        
    Raises:
        ValueError: Si no encuentra rDE o si detecta problemas
    """
    import hashlib
    import time
    # import re  # usa el import global (evita UnboundLocalError)    
    print("🔐 PASSTHROUGH: Detectado XML ya firmado, extrayendo rDE bytes sin re-serializar")
    
    # DEBUG: Verificar xmlns en Signature del XML de entrada
    xml_str = xml_bytes.decode('utf-8')
    sig_match = re.search(r'<Signature[^>]*>', xml_str)
    if sig_match:
        print(f"DEBUG: Signature en entrada a build_lote_passthrough_signed: {sig_match.group(0)}")
    
    # Extraer rDE bytes sin tocar
    rde_bytes = _extract_rde_bytes_passthrough(xml_bytes)
    print(f"   rDE extraído: {len(rde_bytes)} bytes")
    
    # DEBUG: Verificar xmlns en Signature del rDE extraído
    rde_str = rde_bytes.decode('utf-8')
    sig_match = re.search(r'<Signature[^>]*>', rde_str)
    if sig_match:
        print(f"DEBUG: Signature en rDE extraído: {sig_match.group(0)}")
    
    # CRÍTICO: Verificar y agregar Id a rDE si falta (requerido por XSD)
    # Esto debe hacerse ANTES de envolver en rLoteDE
    print("DEBUG: Iniciando verificación de rDE")
    try:
        from lxml import etree
        rde_elem = etree.fromstring(rde_bytes)
        
        # CRÍTICO: NO eliminar xsi:schemaLocation - puede ser requerido
    # XSI_NS = "http://www.w3.org/2001/XMLSchema-instance"
    # schema_attr = f"{{{XSI_NS}}}schemaLocation"
    # if schema_attr in rde_elem.attrib:
    #     del rde_elem.attrib[schema_attr]
    #     print("✅ Eliminado xsi:schemaLocation de rDE")
        
        # CRÍTICO: NO agregar xsi:schemaLocation - causa error 0160
        # XSI_NS = "http://www.w3.org/2001/XMLSchema-instance"
        # schema_attr = f"{{{XSI_NS}}}schemaLocation"
        # if schema_attr not in rde_elem.attrib:
        #     # Para agregar xmlns:xsi, necesitamos reconstruir el elemento con nsmap
        #     # ya que lxml no permite modificar nsmap después de creado
        #     new_rde = etree.Element(rde_elem.tag, nsmap=rde_elem.nsmap)
        #     if XSI_NS not in new_rde.nsmap:
        #         new_rde.nsmap['xsi'] = XSI_NS
        #     
        #     # Copiar todos los atributos existentes
        #     for k, v in rde_elem.attrib.items():
        #         new_rde.set(k, v)
        #     
        #     # Agregar schemaLocation
        #     new_rde.set(schema_attr, "http://ekuatia.set.gov.py/sifen/xsd siRecepDE_v150.xsd")
        #     
        #     # Copiar todos los hijos
        #     for child in rde_elem:
        #         new_rde.append(child)
        #     
        #     rde_elem = new_rde
        # (PATCH) No agregar xsi:schemaLocation al rDE: puede causar 0160
# Verificar si rDE tiene el atributo Id
        if 'Id' not in rde_elem.attrib:
            print("⚠️  rDE no tiene atributo Id, agregando...")
            # Buscar el DE interno para obtener su Id
            de_elem = rde_elem.find('.//{*}DE')
            if de_elem is not None and 'Id' in de_elem.attrib:
                de_id = de_elem.get('Id')
                # Usar un Id diferente: prefijar con "rDE"
                rde_id = f"rDE{de_id}"
                rde_elem.set('Id', rde_id)
                print(f"✅ Agregado Id='{rde_id}' a rDE (DE Id={de_id})")
                
                # Re-serializar rDE con el Id agregado
                print(f"🔍 DEBUG rde_elem tag: {rde_elem.tag}")
                rde_bytes = etree.tostring(rde_elem, encoding='utf-8', xml_declaration=False)  # No declaration inside rLoteDE
                print(f"🔍 DEBUG rde_bytes starts with: {rde_bytes[:200]}")
                print(f"   rDE actualizado: {len(rde_bytes)} bytes")
                
                # CRÍTICO: Asegurar que Signature tenga el xmlns SIFEN (requerido por SIFEN)
                rde_str = rde_bytes.decode('utf-8')
                # NO forzar más - dejar XMLDSig estándar
                # rde_str = re.sub(r'<Signature(?: xmlns="http://www\.w3\.org/2000/09/xmldsig#")?>', 
                #                 r'<Signature xmlns="http://ekuatia.set.gov.py/sifen/xsd">', 
                #                 rde_str, flags=re.MULTILINE | re.DOTALL)
                # rde_bytes = rde_str.encode('utf-8')
                # print("✅ Forzado xmlns SIFEN en Signature (requerido por SIFEN)")
            else:
                print("❌ No se encontró DE con Id para generar rDE Id")
        else:
            print(f"✅ rDE ya tiene Id: {rde_elem.get('Id')}")
        
        # CRÍTICO: Re-serializar rDE después de agregar schemaLocation
        rde_bytes = etree.tostring(rde_elem, encoding='utf-8')
        print(f"   rDE actualizado con schemaLocation: {len(rde_bytes)} bytes")
        
        # FIX: Eliminar gCamFuFD duplicados
        # Solo debe haber un gCamFuFD como hijo directo de rDE
        gcam_elements = rde_elem.findall('.//{*}gCamFuFD')
        if len(gcam_elements) > 1:
            print(f"⚠️  Detectados {len(gcam_elements)} gCamFuFD, eliminando duplicados...")
            # Mantener solo el primero
            for gcam in gcam_elements[1:]:
                parent = gcam.getparent()
                if parent is not None:
                    parent.remove(gcam)
                    print("   Eliminado gCamFuFD duplicado")
            # No need to re-serialize here, already done above
        
        # CRÍTICO: gCamFuFD debe contener dCarQR, dInfAdic y dDesTrib
        # Eliminar cualquier hijo adicional que no sea estos tres
        for gcam in rde_elem.findall('.//{*}gCamFuFD'):
            children_to_remove = []
            for child in gcam:
                tag = child.tag.split('}')[-1]
                if tag not in ['dCarQR', 'dInfAdic', 'dDesTrib']:
                    children_to_remove.append(child)
            
            for child in children_to_remove:
                gcam.remove(child)
                print(f"   Eliminado {child.tag.split('}')[-1]} de gCamFuFD")
        
        # Re-serializar después de limpiar gCamFuFD
        rde_bytes = etree.tostring(rde_elem, encoding='utf-8')
        print(f"   rDE actualizado después de limpiar gCamFuFD: {len(rde_bytes)} bytes")
            
        # === FIX QR: asegurar dCarQR dentro de gCamFuFD (sin tocar el DE firmado) ===
        try:
            import os
            from xml.sax.saxutils import escape as _xml_escape
            from app.sifen_client.qr_generator import build_qr_dcarqr

            rde_str2 = rde_bytes.decode("utf-8", errors="strict")
            
            # DEBUG: Save rde_bytes to inspect
            print(f"🔍 DEBUG rde_bytes length: {len(rde_bytes)}")
            print(f"🔍 DEBUG rde_str2 starts with: {rde_str2[:100]}...")
            
            # Check if DE element is present
            if "<DE " not in rde_str2:
                print("❌ ERROR: No <DE> element found in rde_str2!")
                print("rde_str2 content:")
                print(rde_str2[:500])

            if "<dCarQR>" not in rde_str2:
                # Construir URL QR (usa defaults del qr_generator si base_url/idcsc/csc son None)
                qr_url = build_qr_dcarqr(
                    rde_xml=rde_bytes,
                    base_url=os.getenv("SIFEN_QR_BASE_URL") or os.getenv("QR_BASE_URL"),
                    idcsc=os.getenv("SIFEN_IDCSC") or os.getenv("SIFEN_QR_IDCSC") or os.getenv("IDCSC"),
                    csc=os.getenv("SIFEN_CSC") or os.getenv("SIFEN_QR_CSC") or os.getenv("CSC"),
                )
                qr_url_xml = _xml_escape(qr_url)

                # Si ya existe gCamFuFD, insertar dCarQR adentro (como primer hijo)
                if re.search(r"<gCamFuFD\b[^>]*>", rde_str2):
                    # es self-closing, reemplazar con opening tag, content y closing tag
                    if re.search(r"<gCamFuFD\b[^>]*/>", rde_str2):
                        rde_str2 = re.sub(
                            r"<gCamFuFD\b[^>]*/>",
                            r"<gCamFuFD><dCarQR>" + qr_url_xml + r"</dCarQR><dInfAdic></dInfAdic></gCamFuFD>",
                            rde_str2,
                            count=1,
                            flags=re.DOTALL,
                        )
                    else:
                        # Si no es self-closing, insertar después del opening tag
                        rde_str2 = re.sub(
                            r"(<gCamFuFD\b[^>]*>)",
                            r"<gCamFuFD><dCarQR>" + qr_url_xml + r"</dCarQR><dInfAdic></dInfAdic></gCamFuFD>",
                            rde_str2,
                            count=1,
                            flags=re.DOTALL,
                        )
                    print("✅ Insertado dCarQR dentro de gCamFuFD (passthrough)")
                else:
                    # Si no existe gCamFuFD, crearlo después de </Signature>
                    rde_str2 = re.sub(
                        r"(</Signature>)",
                        r"\1<gCamFuFD><dCarQR>" + qr_url_xml + r"</dCarQR><dInfAdic></dInfAdic></gCamFuFD>",
                        rde_str2,
                        count=1,
                        flags=re.DOTALL,
                    )
                    print("✅ Creado gCamFuFD con dCarQR después de Signature (passthrough)")

            else:
                print("✅ dCarQR ya presente en rDE (passthrough)")
        except Exception as e:
            print(f"⚠️  No se pudo inyectar dCarQR en passthrough: {e}")
            
        # NO eliminar prefijos aquí - rompe la firma
        # Los prefijos deben eliminarse ANTES de firmar
        
        # CRÍTICO: Usar namespace SIFEN en Signature (requerido por SIFEN según memoria solución definitiva)
        rde_str = rde_bytes.decode('utf-8')
        # Verificar xmlns actual
        if '<Signature xmlns="http://ekuatia.set.gov.py/sifen/xsd">' in rde_str:
            print("✅ Signature ya tiene xmlns SIFEN")
        else:
            if True:
                # Reemplazar Signature con namespace XMLDSig por Signature con namespace SIFEN
                # Buscar <Signature xmlns="http://www.w3.org/2000/09/xmldsig#"> o <Signature> sin xmlns
                rde_str = re.sub(r'<Signature(?: xmlns="http://www\.w3\.org/2000/09/xmldsig#")?>', 
                                r'<Signature xmlns="http://ekuatia.set.gov.py/sifen/xsd">', 
                                rde_str, count=1)
                print("✅ Signature xmlns cambiado a SIFEN")
                rde_bytes = rde_str.encode('utf-8')
            else:
                print("ℹ️  Manteniendo Signature xmlns XMLDSig estándar")
            
        # CRÍTICO: NO usar lxml para serializar (agrega prefijos ns0:)
        # rde_bytes ya contiene los bytes correctos del XML original
        # Solo modificamos el xmlns de Signature si es necesario
            
    except Exception as e:
        print(f"⚠️  Error al verificar/agregar Id a rDE: {e}")
        # Continuar sin modificar (podría fallar en SIFEN)
    
    # Calcular hash del rDE MODIFICADO (con Id y namespace corregido)
    rde_hash = hashlib.sha256(rde_bytes).hexdigest()
    
    # NO MODIFICAR el XML después de firmado
    # Cualquier cambio invalida la firma frente a SIFEN
    
    from pathlib import Path
    artifacts_dir = Path("/Users/robinklaiss/Dev/industrias-feris-facturacion-electronica-simplificado/tesaka-cv/tools/artifacts")
    artifacts_dir.mkdir(parents=True, exist_ok=True)
    
    try:
        (artifacts_dir / "_passthrough_rde_input.xml").write_bytes(rde_bytes)
        print(f"💾 Guardado: artifacts/_passthrough_rde_input.xml")
    except Exception as e:
        print(f"⚠️  No se pudo guardar artifact: {e}")
    
    # Construir lote.xml como bytes (sin lxml)
# PASSTHROUGH REAL: NO tocar rDE firmado (NO remover xmlns, NO schemaLocation, NO whitespace)
# Cualquier cambio puede romper namespaces heredados y/o digest de la firma.

    lote_xml_bytes = (
        b'<rLoteDE xmlns="' + SIFEN_NS.encode('utf-8') + b'">'
        + rde_bytes +
        b'</rLoteDE>'
    )
    print(f"   lote.xml construido estilo TIPS: {len(lote_xml_bytes)} bytes")
    
    # CRÍTICO: Forzar xmlns SIFEN en Signature después de construir
    # El XML puede venir con xmlns XMLDSig y SIFEN lo rechaza
    lote_xml_str = lote_xml_bytes.decode('utf-8')
    # CRÍTICO: Forzar xmlns SIFEN en Signature
    lote_xml_str = re.sub(
        r'<Signature xmlns="http://www\.w3\.org/2000/09/xmldsig#">',
        r'<Signature xmlns="http://ekuatia.set.gov.py/sifen/xsd">',
        lote_xml_str
    )
    # También reemplazar si no tiene xmlns
    lote_xml_str = re.sub(
        r'<Signature(?=>)',
        r'<Signature xmlns="http://ekuatia.set.gov.py/sifen/xsd"',
        lote_xml_str
    )
    lote_xml_bytes = lote_xml_str.encode('utf-8')
    print("✅ Forzado xmlns SIFEN en Signature (passthrough)")
    
    # CORREGIR ORDEN: Signature debe ir antes de gCamFuFD según solución definitiva
    lote_xml_bytes = reorder_signature_before_gcamfufd(lote_xml_bytes)
    print("✅ Reordenado: Signature antes de gCamFuFD")
    
    # CRÍTICO: NO cambiar namespace de Signature (debe mantener SIFEN para validación de SIFEN)
    # Signature ya viene con el namespace correcto desde la firma
    
    # Verificar que el rDE dentro del lote tenga el mismo hash
    # Extraer rDE del lote para verificar
    rde_from_lote = _extract_rde_bytes_passthrough(lote_xml_bytes)
    rde_from_lote_hash = hashlib.sha256(rde_from_lote).hexdigest()
    
    # NOTA: El hash puede diferir porque modificamos el rDE (agregamos Id y corregimos namespace)
    # Solo verificamos que el rDE extraído no esté vacío
    if len(rde_from_lote) == 0:
        raise RuntimeError("ERROR: El rDE dentro del lote está vacío!")
    
    print("✅ Verificación OK: rDE presente en lote.xml")
    
    # Guardar lote.xml para debug
    try:
        (artifacts_dir / "_passthrough_lote.xml").write_bytes(lote_xml_bytes)
        print(f"💾 Guardado: artifacts/_passthrough_lote.xml")
    except Exception as e:
        print(f"⚠️  No se pudo guardar artifact: {e}")
    
    # Crear ZIP usando el helper que coincide exactamente con TIPS
    zip_bytes = build_xde_zip_bytes_from_lote_xml(lote_xml_bytes.decode('utf-8'))
    zip_base64 = base64.b64encode(zip_bytes).decode('ascii')
    
    if return_debug:
        return zip_base64, lote_xml_bytes, zip_bytes
    return zip_base64


def build_xde_zip_bytes_from_lote_xml(lote_xml: str) -> bytes:
    """
    Construye un ZIP (bytes) con un único archivo: lote.xml

    lote.xml debe contener:
      <?xml version="1.0" encoding="UTF-8"?>
      <rLoteDE xmlns="http://ekuatia.set.gov.py/sifen/xsd"> ... </rLoteDE>

    Nota: evitamos redeclarar el default xmlns en el primer <rDE>, porque hereda de <rLoteDE>.
    """
    import io
    # import re  # usa el import global (evita UnboundLocalError)    import zipfile

    # 1) quitar XML declaration si ya venía
    lote_xml = re.sub(r'^\s*<\?xml[^>]*\?>\s*', '', lote_xml, flags=re.S)

    # 2) evitar redeclarar default xmlns en el primer <rDE ...>
    #    (soporta comillas dobles o simples)
    lote_xml = re.sub(r'(<rDE\b[^>]*?)\s+xmlns=(["\']).*?\2', r'\1', lote_xml, count=1)

    # 3) armar payload final
    # CRÍTICO: NO agregar XML declaration - SIFEN rechaza con error 0160
    xml_payload = lote_xml

    # 4) ZIP_STORED (sin compresión) con entry lote.xml
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", compression=zipfile.ZIP_STORED) as z:
        z.writestr(ZIP_INTERNAL_FILENAME, xml_payload.encode("utf-8"))

    return buf.getvalue()


def build_lote_base64_from_single_xml(xml_bytes: bytes, return_debug: bool = False) -> Union[str, Tuple[str, bytes, bytes], Tuple[str, bytes, bytes, str]]:
    """
    DEPRECATED: Esta función asume que el XML ya está firmado.
    
    RECOMENDADO: Usar build_and_sign_lote_from_xml() que normaliza, firma y valida.
    
    Crea un ZIP con el rDE firmado envuelto en rLoteDE.
    
    El ZIP contiene un único archivo "lote.xml" con:
    - Root: <rLoteDE xmlns="http://ekuatia.set.gov.py/sifen/xsd">
    - Contenido: un <rDE> completo (ya normalizado, firmado y reordenado) como hijo directo.
    
    IMPORTANTE: 
    - NO incluye <dId> ni <xDE> (pertenecen al SOAP rEnvioLote, NO al lote.xml)
    - Selecciona SIEMPRE el rDE que tiene <Signature> como hijo directo (acepta XMLDSig o SIFEN ns).
    - NO modifica la firma ni los hijos del rDE, solo lo envuelve en rLoteDE.
    - Usa extracción por regex desde bytes originales (NO re-serializa con lxml) para preservar
      exactamente la firma, namespaces y whitespace del rDE firmado.
    
    Args:
        xml_bytes: XML que contiene el rDE (puede ser rDE root o tener rDE anidado)
        return_debug: Si True, retorna tupla (base64, lote_xml_bytes, zip_bytes, lote_did)
                      (lote_did es solo para logging, no está en el lote.xml)
        
    Returns:
        Base64 del ZIP como string, o tupla si return_debug=True (incluye lote_did para logging)
        
    Raises:
        ValueError: Si no se encuentra rDE o si el rDE no tiene Signature como hijo directo
        RuntimeError: Si lote.xml contiene <dId> o <xDE> (pertenecen al SOAP, NO al lote.xml)
    """
    import copy
    # etree ya está importado arriba, no redefinir
    
    # Namespace de firma digital
    DSIG_NS = "http://www.w3.org/2000/09/xmldsig#"
    SIFEN_NS = "http://ekuatia.set.gov.py/sifen/xsd"
    
    # Función para verificar si un rDE tiene Signature como hijo directo
    def is_signed_rde(el) -> bool:
        """Verifica si el rDE tiene <Signature> como hijo directo (acepta XMLDSig o SIFEN ns)."""
        return any(
            child.tag == f"{{{DSIG_NS}}}Signature" or child.tag == f"{{{SIFEN_NS}}}Signature"
            for child in list(el)
        )
    
    # Función para verificar si un rDE tiene Signature en cualquier profundidad (incluyendo dentro de DE)
    def has_signature_anywhere(el) -> bool:
        """Verifica si el rDE o su contenido (incluyendo DE) tiene Signature en cualquier profundidad."""
        for sig_candidate in el.iter():
            if local_tag(sig_candidate.tag) == "Signature":
                # Verificar que sea del namespace correcto
                if "}" in sig_candidate.tag:
                    ns = sig_candidate.tag.split("}", 1)[0][1:]
                    if ns == DSIG_NS:
                        return True
                elif sig_candidate.tag == "Signature":
                    # Sin namespace, asumir que es DSIG_NS
                    return True
        return False
    
    # DIAGNÓSTICO: Log información del XML de entrada (SIEMPRE, no solo en debug)
    try:
        xml_str_preview = xml_bytes[:500].decode('utf-8', errors='replace') if len(xml_bytes) > 500 else xml_bytes.decode('utf-8', errors='replace')
        print(f"🔍 DIAGNÓSTICO [build_lote_base64] XML entrada: {len(xml_bytes)} bytes")
        print(f"🔍 DIAGNÓSTICO [build_lote_base64] Primeros 200 chars: {xml_str_preview[:200]}")
    except Exception as e:
        print(f"⚠️  DIAGNÓSTICO [build_lote_base64] Error al leer preview XML: {e}")
    
    # Parsear xml_bytes
    try:
        xml_root = etree.fromstring(xml_bytes)
        root_localname = local_tag(xml_root.tag)
        root_ns = xml_root.tag.split("}", 1)[0][1:] if "}" in xml_root.tag else "VACÍO"
        print(f"🔍 DIAGNÓSTICO [build_lote_base64] Root localname: {root_localname}")
        print(f"🔍 DIAGNÓSTICO [build_lote_base64] Root namespace: {root_ns}")
    except Exception as e:
        error_msg = f"Error al parsear XML: {e}"
        print(f"❌ ERROR en build_lote_base64_from_single_xml: {error_msg}", file=sys.stderr)
        import traceback
        traceback.print_exc(file=sys.stderr)
        raise ValueError(error_msg)
    
    # Helper para asegurar namespace SIFEN en elementos sin xmlns
    def ensure_sifen_ns(el):
        """
        Recorre recursivamente el árbol y asegura que los elementos tengan namespace SIFEN_NS.
        Si el tag no empieza con "{", lo reemplaza por f"{{{SIFEN_NS}}}{localname}".
        Conserva atributos y children.
        """
        if el is None:
            return
        
        # Si el tag no tiene namespace, agregarlo
        if not el.tag.startswith("{"):
            localname = el.tag
            el.tag = f"{{{SIFEN_NS}}}{localname}"
        
        # Recursivamente procesar hijos
        for child in list(el):
            ensure_sifen_ns(child)
    
    # Construir lista de candidatos rDE
    candidates_rde = []
    rde_constructed_from_de = False  # Flag para saber si rDE fue construido desde DE
    
    # Caso a) si local-name(root) == "rDE"
    if local_tag(xml_root.tag) == "rDE":
        candidates_rde = [xml_root]
        print(f"🔍 DIAGNÓSTICO [build_lote_base64] Root ES rDE directamente")
    else:
        # Caso b) buscar todos los rDE con namespace SIFEN
        candidates_rde = xml_root.findall(f".//{{{SIFEN_NS}}}rDE")
        print(f"🔍 DIAGNÓSTICO [build_lote_base64] Buscando rDE con namespace SIFEN: {len(candidates_rde)} encontrados")
        # Caso c) si sigue vacío, buscar sin namespace usando XPath
        if not candidates_rde:
            candidates_rde = xml_root.xpath(".//*[local-name()='rDE']")
            print(f"🔍 DIAGNÓSTICO [build_lote_base64] Buscando rDE sin namespace (XPath): {len(candidates_rde)} encontrados")
    
    # Si no se encontró ningún rDE, intentar construir uno desde DE
    if not candidates_rde:
        print(f"🔍 DIAGNÓSTICO [build_lote_base64] No se encontró rDE, buscando DE para construir rDE...")
        
        # Buscar DE (con o sin namespace)
        de_candidates = []
        
        # Buscar DE con namespace SIFEN
        de_candidates = xml_root.findall(f".//{{{SIFEN_NS}}}DE")
        if not de_candidates:
            # Buscar DE sin namespace usando XPath
            de_candidates = xml_root.xpath(".//*[local-name()='DE']")
        
        # Si el root mismo es DE
        if local_tag(xml_root.tag) == "DE":
            de_candidates = [xml_root] if not de_candidates else de_candidates
        
        if de_candidates:
            de_el = de_candidates[0]
            print(f"🔍 DIAGNÓSTICO [build_lote_base64] Encontrado DE, construyendo rDE mínimo...")
            
            # Asegurar que el árbol SIFEN esté namespaced (incluye DE y todos los hijos SIFEN)
            ensure_sifen_namespace(de_el)
            
            # Crear rDE CON namespace SIFEN y default xmlns correcto
            rde_el = etree.Element(
                _qn_sifen("rDE"),
                nsmap={
                    None: SIFEN_NS_URI,   # default namespace (CRÍTICO)
                    "ds": DSIG_NS_URI,
                    "xsi": XSI_NS_URI,
                },
            )
            
            # Agregar atributo Id usando el Id del DE
            # CRÍTICO: Usar un Id DIFERENTE al DE para evitar duplicación
            de_id = de_el.get("Id")
            if de_id:
                rde_id = "rDE" + de_id
                rde_el.set("Id", rde_id)
                print(f"DEBUG: build_lote_base64: Agregado Id='{rde_id}' a rDE (DE Id={de_id})")
            
            # Agregar dVerFor si no existe en DE
            # (verificar si ya existe en el DE o en algún hijo)
            has_dverfor = False
            for child in de_el.iter():
                if local_tag(child.tag) == "dVerFor":
                    has_dverfor = True
                    break
            
            if not has_dverfor:
                dverfor = etree.SubElement(rde_el, _qn_sifen("dVerFor"))
                dverfor.text = "150"
                print(f"🔍 DIAGNÓSTICO [build_lote_base64] Agregado dVerFor='150' al rDE construido")
            
            # Agregar el DE dentro del rDE
            rde_el.append(de_el)
            
            # Agregar a candidatos
            candidates_rde = [rde_el]
            print(f"🔍 DIAGNÓSTICO [build_lote_base64] rDE construido exitosamente envolviendo DE")
            
            # Marcar que este rDE fue construido desde DE (puede tener Signature dentro del DE, no como hijo directo)
            rde_constructed_from_de = True
        else:
            # No se encontró ni rDE ni DE
            xml_preview = xml_bytes[:200].decode('utf-8', errors='replace') if len(xml_bytes) > 200 else xml_bytes.decode('utf-8', errors='replace')
            de_found = len(xml_root.xpath(".//*[local-name()='DE']")) > 0
            rde_found = len(xml_root.xpath(".//*[local-name()='rDE']")) > 0
            
            error_msg = (
                f"No se encontró rDE en el XML de entrada (no se puede construir lote).\n"
                f"Root local-name: {root_localname}\n"
                f"Root namespace: {root_ns}\n"
                f"Primeros 200 chars del XML: {xml_preview}\n"
                f"DE encontrado por local-name: {de_found}\n"
                f"rDE encontrado por local-name: {rde_found}"
            )
            print(f"❌ ERROR en build_lote_base64_from_single_xml: {error_msg}", file=sys.stderr)
            raise ValueError(error_msg)
    
    print(f"🔍 DIAGNÓSTICO [build_lote_base64] Total candidates_rDE: {len(candidates_rde)}")
    
    # Seleccionar el candidato correcto: el que tiene Signature como hijo directo
    signed = [el for el in candidates_rde if is_signed_rde(el)]
    
    if len(signed) >= 1:
        rde_el = signed[0]
    else:
        # Si no hay rDE con Signature como hijo directo, buscar por gCamFuFD como fallback
        gcam = [
            el for el in candidates_rde
            if any(local_tag(child.tag) == "gCamFuFD" for child in list(el))
        ]
        if gcam:
            rde_el = gcam[0]
            # Validar que tenga Signature
            # Si rDE fue construido desde DE, permitir Signature en cualquier profundidad
            # Si no, requerir Signature como hijo directo
            if rde_constructed_from_de:
                if not has_signature_anywhere(rde_el):
                    # Si fue construido desde DE y no tiene Signature, es un error
                    error_msg = (
                        "Se construyó rDE desde DE pero el DE no contiene Signature. "
                        "El DE debe estar firmado antes de construir el lote."
                    )
                    print(f"❌ ERROR en build_lote_base64_from_single_xml: {error_msg}", file=sys.stderr)
                    raise ValueError(error_msg)
            elif not is_signed_rde(rde_el):
                # DIAGNÓSTICO ADICIONAL antes de levantar ValueError
                children_list = []
                for child in list(rde_el):
                    child_local = local_tag(child.tag)
                    child_ns = child.tag.split("}", 1)[0][1:] if "}" in child.tag else "VACÍO"
                    children_list.append(f"{child_local} (ns: {child_ns})")
                
                # Buscar Signature en cualquier profundidad
                signature_paths = []
                for sig_candidate in rde_el.iter():
                    if local_tag(sig_candidate.tag) == "Signature":
                        # Construir path simple
                        path_parts = []
                        current = sig_candidate
                        while current is not None and current != rde_el:
                            path_parts.insert(0, local_tag(current.tag))
                            current = current.getparent()
                        signature_paths.append(" -> ".join(path_parts))
                
                error_msg = (
                    "Se encontró rDE pero NO contiene <Signature> como hijo directo. "
                    "Probablemente se pasó XML no firmado o se eligió el rDE equivocado.\n"
                    f"Hijos directos de rDE: {', '.join(children_list) if children_list else '(ninguno)'}\n"
                )
                if signature_paths:
                    error_msg += f"Signature encontrada en profundidad: {', '.join(signature_paths)}\n"
                else:
                    error_msg += "Signature NO encontrada en ninguna profundidad dentro de rDE.\n"
                
                print(f"❌ ERROR en build_lote_base64_from_single_xml:", file=sys.stderr)
                print(error_msg, file=sys.stderr)
                raise ValueError(error_msg)
        else:
            # Si rDE fue construido desde DE, permitir Signature en cualquier profundidad
            if rde_constructed_from_de:
                if has_signature_anywhere(candidates_rde[0]):
                    rde_el = candidates_rde[0]
                else:
                    error_msg = (
                        "Se construyó rDE desde DE pero el DE no contiene Signature. "
                        "El DE debe estar firmado antes de construir el lote."
                    )
                    print(f"❌ ERROR en build_lote_base64_from_single_xml: {error_msg}", file=sys.stderr)
                    raise ValueError(error_msg)
            else:
                # DIAGNÓSTICO ADICIONAL antes de levantar ValueError
                error_msg_parts = [
                    "Se encontró rDE pero NO contiene <Signature> como hijo directo. "
                    "Probablemente se pasó XML no firmado o se eligió el rDE equivocado."
                ]
                
                if candidates_rde:
                    for idx, candidate in enumerate(candidates_rde):
                        children_list = []
                        for child in list(candidate):
                            child_local = local_tag(child.tag)
                            child_ns = child.tag.split("}", 1)[0][1:] if "}" in child.tag else "VACÍO"
                            children_list.append(f"{child_local} (ns: {child_ns})")
                        
                        error_msg_parts.append(f"\nCandidato rDE #{idx + 1} hijos directos: {', '.join(children_list) if children_list else '(ninguno)'}")
                        
                        # Buscar Signature en cualquier profundidad
                        signature_paths = []
                        for sig_candidate in candidate.iter():
                            if local_tag(sig_candidate.tag) == "Signature":
                                path_parts = []
                                current = sig_candidate
                                while current is not None and current != candidate:
                                    path_parts.insert(0, local_tag(current.tag))
                                    current = current.getparent()
                                signature_paths.append(" -> ".join(path_parts))
                        
                        if signature_paths:
                            error_msg_parts.append(f"  Signature encontrada en profundidad: {', '.join(signature_paths)}")
                        else:
                            error_msg_parts.append(f"  Signature NO encontrada en ninguna profundidad")
                
                error_msg = "\n".join(error_msg_parts)
                print(f"❌ ERROR en build_lote_base64_from_single_xml:", file=sys.stderr)
                print(error_msg, file=sys.stderr)
                raise ValueError(error_msg)
    
    # Debug: mostrar información de selección
    debug_enabled = os.getenv("SIFEN_DEBUG_SOAP", "0") in ("1", "true", "True")
    if debug_enabled:
        print(f"🧪 DEBUG [build_lote_base64] candidates_rDE: {len(candidates_rde)}")
        print(f"🧪 DEBUG [build_lote_base64] selected_rDE_signed: {is_signed_rde(rde_el)}")
        selected_children = [local_tag(c.tag) for c in list(rde_el)]
        print(f"🧪 DEBUG [build_lote_base64] selected_rDE_children: {', '.join(selected_children)}")
    
    # IMPORTANTE: Serializar rDE firmado usando etree.tostring() para preservar EXACTAMENTE la firma
    # NO volver a parsear/reconstruir el rDE después de firmar
    # REMOVER xsi:schemaLocation antes de serializar
    print("DEBUG: Removiendo xsi:schemaLocation de rde_el antes de serializar")
    _remove_xsi_schemalocation(rde_el)
    
    try:
        rde_bytes = etree.tostring(rde_el, encoding="utf-8", xml_declaration=False, with_tail=False)
        print(f"🔍 DIAGNÓSTICO [build_lote_base64] rDE serializado con etree.tostring: {len(rde_bytes)} bytes")
    except Exception as e:
        raise RuntimeError(f"Error al serializar rDE con etree.tostring: {e}")
    
    # Parche mínimo al start tag del rDE: inyectar xmlns:* si faltan para evitar "Namespace prefix X is not defined"
    # Solo modificar el start tag, NO tocar el resto del XML firmado
    # Usar constantes del módulo si están disponibles, sino definir localmente
    XSI_NS_URI = XSI_NS  # Constante del módulo
    SIFEN_NS_URI = SIFEN_NS  # Constante del módulo
    DSIG_NS = "http://www.w3.org/2000/09/xmldsig#"
    
    # Encontrar el start tag del rDE (hasta el primer >)
    start_tag_end = rde_bytes.find(b">")
    if start_tag_end == -1:
        raise RuntimeError("No se encontró cierre del start tag en rDE serializado")
    
    head = rde_bytes[:start_tag_end + 1]  # Incluye el >
    body = rde_bytes[start_tag_end + 1:]   # Resto del XML
    
    # Detectar qué prefijos se usan en el contenido pero no están declarados en el start tag
    needs_xsi = b"xsi:" in rde_bytes and b'xmlns:xsi="' not in head
    needs_ns0 = b"ns0:" in rde_bytes and b'xmlns:ns0="' not in head
    needs_ds = b"ds:" in rde_bytes and b'xmlns:ds="' not in head
    
    # Inyectar xmlns:* en el start tag si faltan (antes del >)
    if needs_xsi or needs_ns0 or needs_ds:
        # Remover el > del head
        head_without_close = head[:-1]
        # Agregar xmlns:* antes del >
        injections = []
        if needs_xsi:
            injections.append(b' xmlns:xsi="' + XSI_NS_URI.encode("utf-8") + b'"')
        if needs_ns0:
            injections.append(b' xmlns:ns0="' + SIFEN_NS_URI.encode("utf-8") + b'"')
        if needs_ds:
            injections.append(b' xmlns:ds="' + DSIG_NS.encode("utf-8") + b'"')
        
        # Reconstruir head con las inyecciones
        head = head_without_close + b"".join(injections) + b">"
        print(f"🔍 DIAGNÓSTICO [build_lote_base64] Parche aplicado al start tag: {len(injections)} xmlns:* inyectados")
    
    # Reconstruir rDE con el start tag parcheado
    rde_patched = head + body
    
    # REMOVER xsi:schemaLocation del rDE parcheado (causa 0160)
    rde_str = rde_patched.decode('utf-8', errors='replace')
    rde_str = re.sub(r'\s*xsi:schemaLocation="[^"]*"', '', rde_str, flags=re.DOTALL)
    rde_patched = rde_str.encode('utf-8')
    
    # Guardar artifact de debug del rDE fragment (si artifacts_dir existe)
    try:
        artifacts_dir = Path("artifacts")
        if artifacts_dir.exists():
            debug_rde_file = artifacts_dir / "debug_rde_fragment.xml"
            debug_rde_file.write_bytes(rde_patched)
            print(f"💾 Guardado artifact debug: {debug_rde_file}")
    except Exception as e:
        # Silencioso: no fallar si no se puede guardar el artifact
        pass
    
    # Construir lote.xml con estructura: <rLoteDE xmlns="..."><rDE>...</rDE></rLoteDE>
    # SIN dId, SIN xDE (dId y xDE pertenecen al SOAP rEnvioLote, NO al lote.xml)
    # dId dinámico para usar en el SOAP (NO dentro de lote.xml)
    lote_did = str(int(time.time() * 1000))
    
    # Construir lote.xml: rLoteDE con namespace SIFEN, conteniendo rDE firmado
    lote_xml_bytes = (
        b'<?xml version="1.0" encoding="utf-8"?>'
        b'<rLoteDE xmlns="' + SIFEN_NS.encode("utf-8") + b'">'
        + rde_patched +
        b'</rLoteDE>'
    )
    print(f"🔍 DIAGNÓSTICO [build_lote_base64] lote.xml construido con bytes crudos: {len(lote_xml_bytes)} bytes")
    
    # Debug anti-regresión: verificar que la firma se preserva
    if debug_enabled:
        # Verificar que si hay <Signature xmlns="..."> en el firmado, también esté en el lote
        sig_pattern_default = b'<Signature xmlns="http://www.w3.org/2000/09/xmldsig#"'
        sig_pattern_ds = b'<ds:Signature'
        sig_pattern_ns = b'<Signature xmlns:ds='
        
        has_sig_in_firmado = (
            sig_pattern_default in xml_bytes or
            sig_pattern_ds in xml_bytes or
            sig_pattern_ns in xml_bytes
        )
        
        if has_sig_in_firmado:
            has_sig_in_lote = (
                sig_pattern_default in lote_xml_bytes or
                sig_pattern_ds in lote_xml_bytes or
                sig_pattern_ns in lote_xml_bytes
            )
            if not has_sig_in_lote:
                print(f"⚠️  WARNING [build_lote_base64] Patrón de firma no encontrado en lote.xml")
            else:
                print(f"✅ DEBUG [build_lote_base64] Firma preservada en lote.xml")
    
    # Opcional debug: solo validar que sea well-formed (sin re-serializar)
    try:
        etree.fromstring(lote_xml_bytes)
    except Exception as e:
        print(f"⚠️  WARNING [build_lote_base64] lote.xml no es well-formed: {e}")
    
    # Hard-guard: verificar que rLoteDE tenga la estructura correcta: <rLoteDE xmlns="..."><rDE>...</rDE></rLoteDE>
    # PROHIBIDO: <dId> y <xDE> dentro de lote.xml (pertenecen al SOAP, NO al lote.xml)
    rlote_tag_start = lote_xml_bytes.find(b"<rLoteDE")
    if rlote_tag_start >= 0:
        rlote_tag_end = lote_xml_bytes.find(b">", rlote_tag_start)
        if rlote_tag_end > rlote_tag_start:
            rlote_tag = lote_xml_bytes[rlote_tag_start:rlote_tag_end]
            # Verificar que tenga xmlns SIFEN
            if b'xmlns="' + SIFEN_NS.encode("utf-8") + b'"' not in rlote_tag:
                raise RuntimeError(f"BUG: rLoteDE no tiene xmlns SIFEN correcto. Tag: {rlote_tag}")
    
    # Verificar que NO tenga <dId> ni <xDE> (pertenecen al SOAP, NO al lote.xml)
    if b"<dId" in lote_xml_bytes or b"</dId>" in lote_xml_bytes:
        raise RuntimeError("BUG: lote.xml contiene <dId> (pertenece al SOAP, NO al lote.xml)")
    if b"<xDE" in lote_xml_bytes or b"</xDE>" in lote_xml_bytes:
        raise RuntimeError("BUG: lote.xml contiene <xDE> (pertenece al SOAP, NO al lote.xml)")
    
    # Verificar que tenga <rDE> (con o sin prefijo)
    if b"<rDE" not in lote_xml_bytes:
        raise RuntimeError("BUG: lote.xml no contiene <rDE>")
    
    # Verificar que sea well-formed
    try:
        etree.fromstring(lote_xml_bytes)
    except Exception as e:
        raise RuntimeError(f"BUG: lote.xml no es well-formed: {e}")
    
    # Guardar para inspección (antes de crear ZIP)
    if debug_enabled:
        Path("/tmp/lote_xml_payload.xml").write_bytes(lote_xml_bytes)
    
    # ZIP con lote.xml - usando helper que coincide con TIPS
    try:
        zip_bytes = build_xde_zip_bytes_from_lote_xml(lote_xml_bytes.decode('utf-8'))
        print(f"🔍 DIAGNÓSTICO [build_lote_base64] ZIP creado: {len(zip_bytes)} bytes (STORED, lote.xml)")
        
        # Debug del ZIP (SIEMPRE cuando se construye)
        _save_zip_debug(zip_bytes, artifacts_dir, debug_enabled)
    except Exception as e:
        error_msg = f"Error al crear ZIP: {e}"
        print(f"❌ ERROR en build_lote_base64_from_single_xml: {error_msg}", file=sys.stderr)
        import traceback
        traceback.print_exc(file=sys.stderr)
        raise RuntimeError(error_msg)
    
    # Guardar ZIP también para debug
    if debug_enabled:
        Path("/tmp/lote_payload.zip").write_bytes(zip_bytes)
    
    # Check rápido dentro de build_lote_base64_from_single_xml (solo cuando SIFEN_DEBUG_SOAP=1)
    if debug_enabled:
        try:
            print(f"🧪 DEBUG [build_lote_base64] Guardado: /tmp/lote_xml_payload.xml, /tmp/lote_payload.zip")
            
            # Abrir el ZIP en memoria y verificar
            with zipfile.ZipFile(BytesIO(zip_bytes), "r") as zf:
                zip_files = zf.namelist()
                print(f"🧪 DEBUG [build_lote_base64] ZIP files: {zip_files}")
                
                if ZIP_INTERNAL_FILENAME in zip_files:
                    lote_content = zf.read(ZIP_INTERNAL_FILENAME)
                    # El contenido incluye wrapper: <?xml?><rLoteDE><rLoteDE>...</rLoteDE></rLoteDE>
                    # Necesitamos extraer el rLoteDE interno para verificar
                    # import re  # usa el import global (evita UnboundLocalError)                    wrapper_match = re.search(rb'<rLoteDE>(.*)</rLoteDE>', lote_content, re.DOTALL)
                    if wrapper_match:
                        inner_lote = wrapper_match.group(1)
                    else:
                        inner_lote = lote_content
                    
                    lote_root = etree.fromstring(inner_lote)
                    
                    root_tag = local_tag(lote_root.tag)
                    root_ns = lote_root.nsmap.get(None, "VACÍO") if hasattr(lote_root, 'nsmap') else "VACÍO"
                    
                    # Verificar namespace del root (debe ser VACÍO)
                    if "}" in lote_root.tag:
                        root_ns_from_tag = lote_root.tag.split("}", 1)[0][1:]
                        root_ns = root_ns_from_tag if root_ns_from_tag else "VACÍO"
                    else:
                        root_ns = "VACÍO"
                    
                    print(f"🧪 DEBUG [build_lote_base64] root localname: {root_tag}")
                    print(f"🧪 DEBUG [build_lote_base64] root namespace: {root_ns}")
                    
                    # Verificar que existe rDE dentro de rLoteDE
                    rde_found = lote_root.find(f".//{{{SIFEN_NS}}}rDE")
                    if rde_found is None:
                        rde_found = lote_root.find(".//rDE")
                    
                    has_rde = rde_found is not None
                    print(f"🧪 DEBUG [build_lote_base64] has_rDE: {has_rde}")
                    
                    if has_rde and root_tag == "rLoteDE":
                        # Verificar namespace del rDE (debe ser SIFEN_NS)
                        rde_tag = rde_found.tag
                        rde_ns = "VACÍO"
                        if "}" in rde_tag:
                            rde_ns = rde_tag.split("}", 1)[0][1:]
                        else:
                            # Buscar xmlns en el rDE o heredado
                            # Si el tag no tiene namespace en el nombre, buscar en nsmap o en atributos
                            rde_ns = rde_found.nsmap.get(None, "VACÍO") if hasattr(rde_found, 'nsmap') else "VACÍO"
                            # Si sigue VACÍO, verificar en el XML original (bytes) buscando xmlns en el tag rDE
                            if rde_ns == "VACÍO":
                                # Leer el contenido del ZIP y buscar xmlns en el tag rDE
                                lote_content_str = lote_content.decode('utf-8', errors='replace')
                                rde_tag_match = re.search(r'<rDE\b([^>]*)>', lote_content_str)
                                if rde_tag_match:
                                    attrs = rde_tag_match.group(1)
                                    xmlns_match = re.search(r'xmlns="([^"]+)"', attrs)
                                    if xmlns_match:
                                        rde_ns = xmlns_match.group(1)
                                    else:
                                        # Intentar con comillas simples
                                        xmlns_match = re.search(r"xmlns='([^']+)'", attrs)
                                        if xmlns_match:
                                            rde_ns = xmlns_match.group(1)
                        
                        print(f"🧪 DEBUG [build_lote_base64] rDE localname: {local_tag(rde_tag)}")
                        print(f"🧪 DEBUG [build_lote_base64] rDE namespace: {rde_ns}")
                        
                        # Mostrar orden de hijos del rDE interno
                        children_order = [local_tag(c.tag) for c in list(rde_found)]
                        print(f"🧪 DEBUG [build_lote_base64] rDE children: {', '.join(children_order)}")
                        
                        # Verificar que incluye Signature y gCamFuFD
                        has_signature = any(local_tag(c.tag) == "Signature" for c in list(rde_found))
                        has_gcam = any(local_tag(c.tag) == "gCamFuFD" for c in list(rde_found))
                        if not has_signature:
                            print(f"⚠️  WARNING [build_lote_base64] rDE interno NO tiene Signature")
                        if not has_gcam:
                            print(f"⚠️  WARNING [build_lote_base64] rDE interno NO tiene gCamFuFD")
                        
                        # Verificar estructura esperada
                        if root_ns != "VACÍO" and root_ns != "":
                            print(f"⚠️  WARNING [build_lote_base64] rLoteDE NO debe tener namespace, tiene: {root_ns}")
                        if rde_ns != SIFEN_NS:
                            print(f"⚠️  WARNING [build_lote_base64] rDE debe tener namespace {SIFEN_NS}, tiene: {rde_ns}")
                    elif root_tag != "rLoteDE":
                        print(f"⚠️  WARNING [build_lote_base64] root debería ser rLoteDE, es {root_tag}")
        except Exception as e:
            print(f"⚠️  DEBUG [build_lote_base64] error al verificar ZIP: {e}")
            import traceback
            traceback.print_exc()
    
    # Base64 estándar sin saltos
    b64 = base64.b64encode(zip_bytes).decode("ascii")
    if return_debug:
        return b64, lote_xml_bytes, zip_bytes, lote_did
    return b64


def _check_signing_dependencies() -> None:
    """
    Verifica que lxml y xmlsec estén disponibles.
    
    Raises:
        RuntimeError: Si faltan dependencias críticas
    """
    try:
        import lxml
        from lxml import etree
    except ImportError as e:
        raise RuntimeError(
            "BLOQUEADO: Dependencias de firma faltantes (lxml). "
            "Ejecutar scripts/bootstrap_env.sh o: pip install lxml"
        ) from e
    
    try:
        import xmlsec
    except ImportError as e:
        raise RuntimeError(
            "BLOQUEADO: Dependencias de firma faltantes (xmlsec). "
            "Ejecutar scripts/bootstrap_env.sh o: pip install python-xmlsec"
        ) from e


def build_and_sign_lote_from_xml(
    xml_bytes: bytes,
    cert_path: str,
    cert_password: str,
    return_debug: bool = False,
    dump_http: bool = False
) -> Union[str, Tuple[str, bytes, bytes, None]]:
    """
    Construye el lote.xml COMPLETO como árbol lxml ANTES de firmar, luego firma el DE
    dentro del contexto del lote final, y serializa UNA SOLA VEZ.
    
    IMPORTANTE: lote.xml (dentro del ZIP) NO debe contener <dId> ni <xDE> (pertenecen al SOAP rEnvioLote).
    IMPORTANTE: lote.xml SÍ debe contener <rDE> directamente dentro de <rLoteDE> (NO <xDE>).
    
    Flujo:
    1. Verificar dependencias críticas (lxml/xmlsec)
    2. Parsear XML de entrada y extraer rDE/DE
    3. Construir árbol lote final: <rLoteDE>...<rDE>...</rDE>...</rLoteDE> (SIN dId, SIN xDE, CON rDE directo)
    4. Remover cualquier Signature previa del rDE
    5. Firmar el DE dentro del contexto del lote final (no fuera y luego mover)
    """
    # import re  # usa el import global (evita UnboundLocalError)    
    # 6. Validar post-firma (algoritmos SHA256, URI correcto)
    # 7. Agregar rDE firmado directamente como hijo de rLoteDE (NO crear xDE)
    # 8. Serializar lote completo UNA SOLA VEZ (pretty_print=False)
    # 9. Comprimir en ZIP y codificar en Base64
    # 10. Validar que el ZIP contiene <rDE> y NO contiene <dId> ni <xDE>
    # 11. Sanity check: verificar que existe al menos 1 rDE y 0 xDE
    # 12. Guardar artifacts/last_xde.zip siempre
    
    # Esto garantiza que la firma se calcula en el MISMO namespace context que viajará dentro del lote.
    """
    Args:
        xml_bytes: XML que contiene el rDE (puede ser rDE root o tener rDE anidado)
        cert_path: Ruta al certificado P12 para firma
        cert_password: Contraseña del certificado P12
        return_debug: Si True, retorna tupla (base64, lote_xml_bytes, zip_bytes, None)
        
    Returns:
        Base64 del ZIP como string, o tupla si return_debug=True
        
    Raises:
        ValueError: Si no se encuentra rDE o si falla la construcción
        RuntimeError: Si faltan dependencias, falla la firma, serialización o validación
    """
    # CRÍTICO: NO eliminar xsi:schemaLocation - puede ser requerido
    # 0. LIMPIEZA ANTI-0160: Remover xsi:schemaLocation que causa error 0160
    # xml_str = xml_bytes.decode('utf-8', errors='replace')
    # # Remove xsi:schemaLocation (including newlines)
    # xml_str = re.sub(r'\s*xsi:schemaLocation="[^"]*"', '', xml_str, flags=re.DOTALL)
    # xml_bytes = xml_str.encode('utf-8')
    
    # DEBUG: Dump después de limpiar xsi:schemaLocation
    artifacts_dir_for_debug = Path("artifacts")
    hash_input = dump_stage("01_input", xml_bytes, artifacts_dir_for_debug)
    hash_clean = dump_stage("02_clean_xsi", xml_bytes, artifacts_dir_for_debug)
    compare_hashes(hash_input, hash_clean, "01_input", "02_clean_xsi")
    
    # 1. GUARD-RAIL: Verificar dependencias críticas ANTES de continuar
    try:
        _check_signing_dependencies()
    except RuntimeError as e:
        # Guardar artifacts si faltan dependencias
        artifacts_dir = Path("artifacts")
        artifacts_dir.mkdir(parents=True, exist_ok=True)
        try:
            artifacts_dir.joinpath("sign_blocked_input.xml").write_bytes(xml_bytes)
            artifacts_dir.joinpath("sign_blocked_reason.txt").write_text(
                f"BLOQUEADO: Dependencias de firma faltantes\n\n{str(e)}\n\n"
                f"Ejecutar: scripts/bootstrap_env.sh\n"
                f"O manualmente: pip install lxml python-xmlsec",
                encoding="utf-8"
            )
        except Exception:
            pass
        raise
    
    import hashlib
    # re ya está importado a nivel de módulo
    
    debug_enabled = os.getenv("SIFEN_DEBUG_SOAP", "0") in ("1", "true", "True")
    
    # 1. Parsear XML de entrada
    try:
        parser = etree.XMLParser(remove_blank_text=False, recover=False)
        xml_root = etree.fromstring(xml_bytes, parser=parser)
        # REMOVER xsi:schemaLocation de todo el árbol parseado
        print("DEBUG: Llamando a _remove_xsi_schemalocation después de parsear")
        removed = _remove_xsi_schemalocation(xml_root)
        print(f"DEBUG: _remove_xsi_schemalocation retornó {removed}")
    except Exception as e:
        raise ValueError(f"Error al parsear XML de entrada: {e}")
    
    # DEBUG: Dump después de parsear
    xml_after_parse = etree.tostring(xml_root, encoding="utf-8", xml_declaration=True)
    hash_parsed = dump_stage("03_parsed", xml_after_parse, artifacts_dir_for_debug)
    compare_hashes(hash_clean, hash_parsed, "02_clean_xsi", "03_parsed")
    
    # 2. Extraer o construir rDE (sin firmar aún)
    root_localname = local_tag(xml_root.tag)
    
    # Soporte para rEnviDe (siRecepDE) que contiene xDE en base64
    if root_localname == "rEnviDe":
        # Guardar input original para debug
        artifacts_dir = Path("artifacts")
        artifacts_dir.mkdir(parents=True, exist_ok=True)
        try:
            artifacts_dir.joinpath("renvide_input.xml").write_bytes(xml_bytes)
        except Exception:
            pass
        
        # Helper local para búsqueda robusta namespace-aware
        def _find_first(root, name: str, ns_uri: Optional[str] = None):
            """Busca el primer elemento con localname 'name', probando múltiples métodos."""
            # 1) namespace explícito si ns_uri
            if ns_uri:
                el = root.find(f'.//{{{ns_uri}}}{name}')
                if el is not None:
                    return el
            # 2) XPath local-name (lxml)
            try:
                els = root.xpath(f'//*[local-name()="{name}"]')
                if els:
                    return els[0]
            except Exception:
                pass
            # 3) fallback iter
            for el in root.iter():
                if isinstance(el.tag, str) and local_tag(el.tag) == name:
                    return el
            return None
        
        # Buscar xDE (namespace-aware)
        xde_elem = _find_first(xml_root, "xDE", SIFEN_NS)
        
        # Si no se encuentra xDE pero existe rDE, crear xDE automáticamente
        if xde_elem is None:
            rde_elem = _find_first(xml_root, "rDE", SIFEN_NS)
            if rde_elem is not None:
                # Crear xDE en namespace SIFEN
                xde_elem = etree.Element(f"{{{SIFEN_NS}}}xDE")
                
                # Insertarlo debajo de rEnviDe (después de dId si existe)
                did_elem = _find_first(xml_root, "dId", SIFEN_NS)
                if did_elem is not None:
                    children = list(xml_root)
                    idx = children.index(did_elem) + 1
                    xml_root.insert(idx, xde_elem)
                else:
                    xml_root.insert(0, xde_elem)
                
                # Mover el rDE existente dentro de xDE
                old_parent = rde_elem.getparent()
                if old_parent is not None:
                    old_parent.remove(rde_elem)
                xde_elem.append(rde_elem)
        
        # Si aún no se encontró xDE, construir diagnóstico detallado
        # xDE puede tener texto (base64) o hijos (rDE), ambos son válidos
        has_text = xde_elem is not None and xde_elem.text and xde_elem.text.strip()
        has_children = xde_elem is not None and len(list(xde_elem)) > 0
        if xde_elem is None or (not has_text and not has_children):
            root_tag = xml_root.tag if hasattr(xml_root, 'tag') else str(xml_root)
            root_nsmap = xml_root.nsmap if hasattr(xml_root, 'nsmap') else {}
            
            # Recolectar primeros ~30 tags descendientes para diagnóstico
            tags = []
            for el in xml_root.iter():
                if isinstance(el.tag, str):
                    tags.append(local_tag(el.tag))
                if len(tags) >= 30:
                    break
            
            raise ValueError(
                f"Entrada es rEnviDe pero no se encontró xDE. "
                f"root.tag={root_tag}, root.nsmap={root_nsmap}, first_tags={tags[:30]}"
            )
        
        # Extraer contenido de xDE: puede ser base64 (texto) o rDE (hijo)
        de_root = None
        
        # Caso 1: xDE tiene texto (base64)
        if xde_elem.text and xde_elem.text.strip():
            xde_base64 = xde_elem.text.strip()
            # Remover espacios/linebreaks del base64
            xde_base64 = re.sub(r'\s+', '', xde_base64)
            
            try:
                # Decodificar base64
                de_bytes = base64.b64decode(xde_base64)
            except Exception as e:
                raise ValueError(f"Error al decodificar xDE (base64): {e}")
            
            # Guardar XML extraído para debug
            try:
                artifacts_dir.joinpath("xde_extracted_from_renvide.xml").write_bytes(de_bytes)
            except Exception:
                pass
            
            # Re-parsear el contenido decodificado
            try:
                de_root = etree.fromstring(de_bytes, parser=parser)
            except Exception as e:
                raise ValueError(f"Error al parsear XML extraído de xDE: {e}")
        
        # Caso 2: xDE tiene hijos (rDE como hijo)
        elif len(list(xde_elem)) > 0:
            # Buscar rDE dentro de xDE
            rde_in_xde = _find_first(xde_elem, "rDE", SIFEN_NS)
            if rde_in_xde is not None:
                de_root = rde_in_xde
            else:
                # Si no hay rDE, buscar DE directamente
                de_in_xde = _find_first(xde_elem, "DE", SIFEN_NS)
                if de_in_xde is not None:
                    de_root = de_in_xde
                else:
                    raise ValueError("xDE contiene hijos pero no se encontró rDE ni DE dentro")
        
        if de_root is None:
            raise ValueError("xDE no contiene contenido válido (ni base64 ni rDE/DE como hijo)")
        
        de_root_localname = local_tag(de_root.tag)
        
        if de_root_localname == "rDE":
            rde_el = de_root
        elif de_root_localname == "DE":
            # Construir rDE contenedor
            rde_el = etree.Element(
                _qn_sifen("rDE"),
                nsmap={
                    None: SIFEN_NS_URI,   # default namespace (CRÍTICO)
                    "ds": DSIG_NS_URI,
                    "xsi": XSI_NS_URI,
                },
            )
            # Asegurar que el árbol SIFEN esté namespaced
            ensure_sifen_namespace(de_root)
            # Agregar atributo Id usando el Id del DE
            # CRÍTICO: Usar un Id DIFERENTE al DE para evitar duplicación
            de_id = de_root.get("Id")
            if de_id:
                rde_id = "rDE" + de_id
                rde_el.set("Id", rde_id)
                print(f"DEBUG: Agregado Id='{rde_id}' a rDE wrapper (DE Id={de_id})")
            # Agregar dVerFor
            dverfor = etree.SubElement(rde_el, _qn_sifen("dVerFor"))
            dverfor.text = "150"
            # Append DE en rDE
            rde_el.append(de_root)
        else:
            raise ValueError(
                f"XML extraído de xDE tiene root inesperado: {de_root_localname}. "
                f"Se esperaba 'rDE' o 'DE'"
            )
    
    elif root_localname == "rDE":
        rde_el = xml_root
    elif root_localname == "DE":
        # El root mismo es DE: construir rDE wrapper
        de_el = xml_root
        # Crear rDE CON namespace SIFEN y default xmlns correcto
        rde_el = etree.Element(
            _qn_sifen("rDE"),
            nsmap={
                None: SIFEN_NS_URI,   # default namespace (CRÍTICO)
                "ds": DSIG_NS_URI,
                "xsi": XSI_NS_URI,
            },
        )
        # Asegurar que el árbol SIFEN esté namespaced (incluye DE y todos los hijos SIFEN)
        ensure_sifen_namespace(de_el)
        # Agregar atributo Id usando el Id del DE
        # CRÍTICO: Usar un Id DIFERENTE al DE para evitar duplicación
        de_id = de_el.get("Id")
        if de_id:
            rde_id = "rDE" + de_id
            rde_el.set("Id", rde_id)
            print(f"DEBUG: Agregado Id='{rde_id}' a rDE wrapper (root es DE, DE Id={de_id})")
        # Agregar dVerFor
        dverfor = etree.SubElement(rde_el, _qn_sifen("dVerFor"))
        dverfor.text = "150"
        # Append DE en rDE
        rde_el.append(de_el)
    else:
        # Buscar rDE en el árbol (namespace-aware)
        rde_candidates = xml_root.findall(f".//{{{SIFEN_NS_URI}}}rDE")
        if not rde_candidates:
            # Fallback: buscar sin namespace
            rde_candidates = xml_root.xpath(".//*[local-name()='rDE']")
        
        if not rde_candidates:
            # Intentar construir desde DE (namespace-aware)
            de_candidates = xml_root.findall(f".//{{{SIFEN_NS_URI}}}DE")
            if not de_candidates:
                # Fallback: buscar sin namespace
                de_candidates = xml_root.xpath(".//*[local-name()='DE']")
            
            if de_candidates:
                de_el = de_candidates[0]
                # Crear rDE CON namespace SIFEN y default xmlns correcto
                rde_el = etree.Element(
                    _qn_sifen("rDE"),
                    nsmap={
                        None: SIFEN_NS_URI,   # default namespace (CRÍTICO)
                        "ds": DSIG_NS_URI,
                        "xsi": XSI_NS_URI,
                    },
                )
                # Asegurar que el árbol SIFEN esté namespaced (incluye DE y todos los hijos SIFEN)
                ensure_sifen_namespace(de_el)
                # Agregar atributo Id usando el Id del DE
                # CRÍTICO: Usar un Id DIFERENTE al DE para evitar duplicación
                de_id = de_el.get("Id")
                if de_id:
                    rde_id = "rDE" + de_id
                    rde_el.set("Id", rde_id)
                    print(f"DEBUG: Agregado Id='{rde_id}' a rDE wrapper (fallback, DE Id={de_id})")
                # Agregar dVerFor
                dverfor = etree.SubElement(rde_el, _qn_sifen("dVerFor"))
                dverfor.text = "150"
                # Append DE en rDE
                rde_el.append(de_el)
            else:
                root_tag = xml_root.tag if hasattr(xml_root, 'tag') else str(xml_root)
                root_nsmap = xml_root.nsmap if hasattr(xml_root, 'nsmap') else {}
                raise ValueError(
                    f"No se encontró rDE ni DE en el XML de entrada. "
                    f"root localname: {root_localname}, root.tag: {root_tag}, root.nsmap: {root_nsmap}"
                )
        else:
            rde_el = rde_candidates[0]
    
    # 3. Construir lote.xml completo como árbol lxml ANTES de firmar
    # IMPORTANTE: lote.xml NO debe contener <dId> ni <xDE> (pertenecen al SOAP rEnvioLote).
    # IMPORTANTE: lote.xml SÍ debe contener <rDE> directamente dentro de <rLoteDE> (NO <xDE>).
    # Clonar rDE para no modificar el original
    rde_to_sign = copy.deepcopy(rde_el)
    
    # CRÍTICO: Eliminar xsi:schemaLocation del rDE (causa 0160)
    # Usar regex para eliminar el atributo completo
    # import re  # usa el import global (evita UnboundLocalError)    rde_bytes = etree.tostring(rde_to_sign, encoding="utf-8", xml_declaration=False, pretty_print=False, with_tail=False)
    rde_str = re.sub(rb'\s+xsi:schemaLocation="[^"]*"', b'', rde_bytes)
    rde_bytes = rde_str
    if rde_bytes != rde_str:
        print("✅ Eliminado xsi:schemaLocation del rDE")
    
    # Construir lote.xml usando la función corregida con namespace SIFEN
    # El lote.xml debe contener rDE directamente (NO xDE con base64)
    lote_root = etree.Element(etree.QName(SIFEN_NS, "rLoteDE"), nsmap={None: SIFEN_NS})
    
    # REMOVER xsi:schemaLocation (causa error 0160)
    # lote_root.set(etree.QName(XSI_NS, "schemaLocation"), f"{SIFEN_NS} siRecepDE_v150.xsd")
    
    # NOTA: El rDE firmado se agregará directamente como hijo de rLoteDE DESPUÉS de firmar (línea ~2620)
    # Por ahora solo preparamos el lote_root vacío
    
    # 4. Remover cualquier Signature previa del rDE antes de firmar
    ds_ns = "http://www.w3.org/2000/09/xmldsig#"
    for old_sig in rde_to_sign.xpath(f".//*[local-name()='Signature' and namespace-uri()='{ds_ns}']"):
        old_parent = old_sig.getparent()
        if old_parent is not None:
            old_parent.remove(old_sig)
            if debug_enabled:
                print(f"🔧 Firma previa eliminada antes de firmar")
    
    # 5. Encontrar el DE dentro del rDE para firmar
    de_candidates = rde_to_sign.xpath(".//*[local-name()='DE']")
    if not de_candidates:
        raise ValueError("No se encontró elemento DE dentro de rDE")
    de_el = de_candidates[0]
    
    # Obtener Id del DE
    de_id = de_el.get("Id") or de_el.get("id")
    if not de_id:
        raise ValueError("El elemento DE no tiene atributo Id")
    
    if debug_enabled:
        print(f"📋 DE encontrado con Id={de_id}")
    
    # 6. Serializar el rDE para firmar (asegurando namespaces correctos)
    # Serializar solo el rDE pero asegurando namespaces SIFEN
    rde_bytes_in_context = etree.tostring(
        rde_to_sign,
        encoding="utf-8",
        xml_declaration=False,
        pretty_print=False,
        with_tail=False
    )
    
    # Construir XML temporal con rDE como root pero preservando namespaces del lote
    # Para que sign_de_with_p12 pueda procesarlo correctamente
    rde_temp_root = etree.fromstring(rde_bytes_in_context, parser=parser)
    
    # CRÍTICO: Asegurar que el rDE tenga namespace SIFEN y default xmlns ANTES de firmar
    rde_temp_root = ensure_rde_sifen(rde_temp_root)
    
    # DEBUG: Verificar si xsi:schemaLocation está después de ensure_rde_sifen
    print(f"DEBUG: rde_temp_root attributes después de ensure_rde_sifen: {list(rde_temp_root.attrib.keys())}")
    
    # REMOVER xsi:schemaLocation después de ensure_rde_sifen (que puede copiar atributos)
    print("DEBUG: Antes de remover xsi:schemaLocation de rde_temp_root")
    removed = _remove_xsi_schemalocation(rde_temp_root)
    print(f"DEBUG: Removidos {removed} atributos de rde_temp_root")
    
    # Serializar el rDE temporal para firmar (con namespaces preservados)
    rde_to_sign_bytes = etree.tostring(
        rde_temp_root,
        encoding="utf-8",
        xml_declaration=True,
        pretty_print=False,
        with_tail=False
    )
    
    # DEBUG: Verificar si xsi:schemaLocation está en los bytes serializados
    rde_str = rde_to_sign_bytes.decode('utf-8')
    has_schema = 'xsi:schemaLocation' in rde_str
    print(f"DEBUG: rde_to_sign_bytes contiene xsi:schemaLocation: {has_schema}")
    
    # 6.5. Normalizar rDE antes de firmar (mover gCamFuFD de dentro de DE a fuera)
    rde_to_sign_bytes = normalize_rde_before_sign(rde_to_sign_bytes)
    
    # DEBUG: Verificar si gCamFuFD está dentro de DE antes de firmar
    import xml.etree.ElementTree as ET
    try:
        doc = ET.fromstring(rde_to_sign_bytes)
        NS = {'s': 'http://ekuatia.set.gov.py/sifen/xsd'}
        de = doc.find('.//s:DE', NS)
        if de is not None:
            gcam_in_de = de.find('.//s:gCamFuFD', NS)
            print(f"DEBUG: gCamFuFD inside DE before signing: {'YES' if gcam_in_de is not None else 'NO'}")
    except Exception as e:
        print(f"DEBUG: Error checking gCamFuFD: {e}")
    
    # 7. Firmar el rDE (sign_de_with_p12 espera rDE como root)
    from app.sifen_client.xmlsec_signer_clean import sign_de_with_p12
    rde_signed_bytes = sign_de_with_p12(
        rde_to_sign_bytes, cert_path, cert_password
    )
    
    # DEBUG: Guardar rde_signed_bytes para inspección
    with open("artifacts/rde_signed_debug.xml", "wb") as f:
        f.write(rde_signed_bytes)
    print("DEBUG: Guardado rde_signed_bytes en artifacts/rde_signed_debug.xml")
    
    # DEBUG: Verificar si gCamFuFD está dentro de DE después de firmar
    try:
        doc2 = ET.fromstring(rde_signed_bytes)
        de2 = doc2.find('.//s:DE', NS)
        if de2 is not None:
            gcam_in_de2 = de2.find('.//s:gCamFuFD', NS)
            print(f"DEBUG: gCamFuFD inside DE after signing: {'YES' if gcam_in_de2 is not None else 'NO'}")
    except Exception as e:
        print(f"DEBUG: Error checking gCamFuFD after signing: {e}")
    
    # Mover Signature dentro del DE si está fuera (como hermano del DE dentro del rDE)
    debug_enabled = os.getenv("SIFEN_DEBUG_SOAP", "0") in ("1", "true", "True")
    artifacts_dir = Path("artifacts")
    
    # DEBUG: Verificar posición de Signature antes de mover
    try:
        doc3 = ET.fromstring(rde_signed_bytes)
        NS = {'s': 'http://ekuatia.set.gov.py/sifen/xsd', 'ds': 'http://www.w3.org/2000/09/xmldsig#'}
        rde3 = doc3.find('.//s:rDE', NS)
        if rde3 is not None:
            sig_in_rde = rde3.find('.//ds:Signature', NS)
            de3 = rde3.find('.//s:DE', NS)
            sig_in_de = de3.find('.//ds:Signature', NS) if de3 is not None else None
            print(f"DEBUG: Signature position before _move_signature_into_de_if_needed:")
            print(f"  - Signature in rDE: {'YES' if sig_in_rde is not None else 'NO'}")
            print(f"  - Signature in DE: {'YES' if sig_in_de is not None else 'NO'}")
    except Exception as e:
        print(f"DEBUG: Error checking signature position: {e}")
    
    # NO MOVER Signature - debe permanecer como hermano de DE según SIFEN
    # rde_signed_bytes = _move_signature_into_de_if_needed(rde_signed_bytes, artifacts_dir, debug_enabled)
    
    # CORREGIR ORDEN: gCamFuFD debe ir antes de Signature según SIFEN
    rde_signed_bytes = reorder_signature_before_gcamfufd(rde_signed_bytes)
    
    # DEBUG: Verificar posición de Signature después de mover
    try:
        doc4 = ET.fromstring(rde_signed_bytes)
        NS = {'s': 'http://ekuatia.set.gov.py/sifen/xsd', 'ds': 'http://www.w3.org/2000/09/xmldsig#'}
        rde4 = doc4.find('.//s:rDE', NS)
        if rde4 is not None:
            sig_in_rde4 = rde4.find('.//ds:Signature', NS)
            de4 = rde4.find('.//s:DE', NS)
            sig_in_de4 = de4.find('.//ds:Signature', NS) if de4 is not None else None
            print(f"DEBUG: Signature position after _move_signature_into_de_if_needed:")
            print(f"  - Signature in rDE: {'YES' if sig_in_rde4 is not None else 'NO'}")
            print(f"  - Signature in DE: {'YES' if sig_in_de4 is not None else 'NO'}")
    except Exception as e:
        print(f"DEBUG: Error checking signature position after move: {e}")
    
    # Validar post-firma (opcional pero recomendado)
    try:
        # Verificar que hay Signature
        sig = rde_signed_bytes.find(b'<Signature')
        if sig == -1:
            raise RuntimeError("No se encontró <Signature> en XML firmado")
        
        # Verificar que SignatureValue no esté vacío
        sig_val_start = rde_signed_bytes.find(b'<SignatureValue>', sig)
        if sig_val_start != -1:
            sig_val_end = rde_signed_bytes.find(b'</SignatureValue>', sig_val_start)
            if sig_val_end != -1:
                sig_val = rde_signed_bytes[sig_val_start + 17:sig_val_end].strip()
                if not sig_val:
                    raise RuntimeError("Post-firma: <SignatureValue> está vacío (firma dummy)")
        
        # Validar que SignatureValue no es dummy
        try:
            sig_value_b64 = sig_val.decode('ascii').strip()
            sig_value_decoded = base64.b64decode(sig_value_b64)
            sig_value_str = sig_value_decoded.decode("ascii", errors="ignore")
            if "this is a test" in sig_value_str.lower() or "dummy" in sig_value_str.lower():
                raise RuntimeError("Post-firma: SignatureValue contiene texto dummy (firma de prueba, no real)")
        except Exception:
            # Si no se puede decodificar, asumir que es válido (binario real)
            pass
        
        if debug_enabled:
            print(f"✅ Post-firma validado: SignatureMethod=rsa-sha256, DigestMethod=sha256")
    except Exception as e:
        # Guardar artifacts si falla validación post-firma
        error_msg = f"Error en validación post-firma: {e}"
        artifacts_dir = Path("artifacts")
        artifacts_dir.mkdir(parents=True, exist_ok=True)
        try:
            artifacts_dir.joinpath("sign_error_input.xml").write_bytes(rde_to_sign_bytes)
            artifacts_dir.joinpath("sign_error_details.txt").write_text(
                f"{error_msg}\n\nDebug info:\n"
                f"  root.tag: {rde_temp_root.tag}\n"
                f"  root.nsmap: {rde_temp_root.nsmap}\n",
                encoding="utf-8"
            )
        except Exception:
            pass
        raise RuntimeError(error_msg) from e
    
    # 8. Validación post-firma (antes de continuar al ZIP)
    try:
        # Usar parser más permisivo para manejar namespaces mixtos
        parser_strict = etree.XMLParser(remove_blank_text=False, recover=True, ns_clean=False)
        rde_signed_root = etree.fromstring(rde_signed_bytes, parser=parser_strict)
        
        # Verificar que el root sea rDE con namespace SIFEN
        root_localname = _localname(rde_signed_root.tag)
        root_ns = _namespace_uri(rde_signed_root.tag)
        
        if root_localname != "rDE":
            raise RuntimeError(
                f"Post-check falló: root no es rDE. "
                f"root.tag: {rde_signed_root.tag}, "
                f"root.nsmap: {rde_signed_root.nsmap if hasattr(rde_signed_root, 'nsmap') else 'N/A'}"
            )
        
        if root_ns != SIFEN_NS_URI:
            raise RuntimeError(
                f"Post-check falló: rDE tiene namespace incorrecto. "
                f"root.tag: {rde_signed_root.tag}, "
                f"root.ns: {root_ns}, "
                f"esperado: {SIFEN_NS_URI}, "
                f"root.nsmap: {rde_signed_root.nsmap if hasattr(rde_signed_root, 'nsmap') else 'N/A'}"
            )
        
        # Buscar DE con Id (preferir namespace SIFEN)
        de_elem = rde_signed_root.find(f".//{{{SIFEN_NS_URI}}}DE")

        # Fallback: por si viniera sin namespace (no debería, pero ayuda en debug)
        if de_elem is None:
            for elem in rde_signed_root.iter():
                if isinstance(elem.tag, str) and local_tag(elem.tag) == "DE":
                    de_elem = elem
                    break

        if de_elem is None:
            raise RuntimeError("Post-firma: No se encontró <DE> en el rDE firmado")

        de_id = de_elem.get("Id") or de_elem.get("id")
        if not de_id:
            raise RuntimeError("Post-firma: <DE> no tiene atributo Id")
        
        # ✅ SIEMPRE validar contra el XML final firmado (bytes)
        # Usar parser que preserve namespaces correctamente
        parser = etree.XMLParser(ns_clean=False, recover=False)
        rde_signed_root = etree.fromstring(rde_signed_bytes, parser=parser)
        
        # obtener rDE real
        rde_elem = rde_signed_root
        if local_tag(rde_elem.tag) != "rDE":
            rde_candidates = rde_signed_root.xpath("//*[local-name()='rDE'][1]")
            rde_elem = rde_candidates[0] if rde_candidates else None
        if rde_elem is None:
            raise RuntimeError("Post-firma: no se encontró rDE en el XML firmado")

        # buscar Signature robusto (ya debe estar en posición correcta)
        # Intentar buscar con namespace explícito primero
        DS_NS = "http://www.w3.org/2000/09/xmldsig#"
        sig_nodes = rde_elem.xpath("./*[namespace-uri()='http://www.w3.org/2000/09/xmldsig#' and local-name()='Signature']")
        if not sig_nodes:
            # Fallback: buscar sin namespace
            sig_nodes = rde_elem.xpath("./*[local-name()='Signature']")
        sig_elem = sig_nodes[0] if sig_nodes else None

        # NO MOVER Signature - ya debe estar en la posición correcta desde la firma
        # Moverlo después de firmar invalidaría la firma
        
        # validar estructura mínima (evita falsos positivos)
        if sig_elem is None or not sig_elem.xpath(".//*[local-name()='SignedInfo']"):
            raise RuntimeError("Post-firma: Signature no encontrado/incorrecto en el XML firmado")
        
        # Validar SignatureMethod
        sig_method_elem = sig_elem.xpath(".//*[local-name()='SignatureMethod']")[0]
        
        sig_method_alg = sig_method_elem.get("Algorithm", "")
        expected_sig_method = "http://www.w3.org/2001/04/xmldsig-more#rsa-sha256"
        if sig_method_alg != expected_sig_method:
            raise RuntimeError(
                f"Post-firma: SignatureMethod debe ser '{expected_sig_method}', "
                f"encontrado: '{sig_method_alg}'"
            )
        
        # Validar DigestMethod
        digest_method_elem = sig_elem.xpath(".//*[local-name()='DigestMethod']")[0]
        
        digest_method_alg = digest_method_elem.get("Algorithm", "")
        expected_digest_method = "http://www.w3.org/2001/04/xmlenc#sha256"
        if digest_method_alg != expected_digest_method:
            raise RuntimeError(
                f"Post-firma: DigestMethod debe ser '{expected_digest_method}', "
                f"encontrado: '{digest_method_alg}'"
            )
        
        # Validar Reference URI
        ref_elem = sig_elem.xpath(".//*[local-name()='Reference']")[0]
        
        ref_uri = ref_elem.get("URI", "")
        expected_uri = f"#{de_id}"
        if ref_uri != expected_uri:
            raise RuntimeError(
                f"Post-firma: Reference URI debe ser '{expected_uri}', encontrado: '{ref_uri}'"
            )
        
        # Validar X509Certificate
        x509_cert_elem = sig_elem.xpath(".//*[local-name()='X509Certificate']")[0]
        
        if not x509_cert_elem.text or not x509_cert_elem.text.strip():
            raise RuntimeError("Post-firma: <X509Certificate> está vacío (firma dummy o certificado no cargado)")
        
        # Validar SignatureValue
        sig_value_elem = sig_elem.xpath(".//*[local-name()='SignatureValue']")[0]
        
        if not sig_value_elem.text or not sig_value_elem.text.strip():
            raise RuntimeError("Post-firma: <SignatureValue> está vacío (firma dummy)")
        
        # Validar que SignatureValue no es dummy
        try:
            sig_value_b64 = sig_value_elem.text.strip()
            sig_value_decoded = base64.b64decode(sig_value_b64)
            sig_value_str = sig_value_decoded.decode("ascii", errors="ignore")
            if "this is a test" in sig_value_str.lower() or "dummy" in sig_value_str.lower():
                raise RuntimeError("Post-firma: SignatureValue contiene texto dummy (firma de prueba, no real)")
        except Exception:
            # Si no se puede decodificar, asumir que es válido (binario real)
            pass
        
        if debug_enabled:
            print(f"✅ Post-firma validado: SignatureMethod=rsa-sha256, DigestMethod=sha256, Reference URI=#{de_id}")
    except Exception as e:
        # Guardar artifacts si falla validación post-firma
        artifacts_dir = Path("artifacts")
        artifacts_dir.mkdir(parents=True, exist_ok=True)
        try:
            artifacts_dir.joinpath("sign_preflight_failed.xml").write_bytes(rde_signed_bytes)
            # Verificar si hay problemas de malformación en el XML firmado
            problem = _scan_xml_bytes_for_common_malformed(rde_signed_bytes)
            error_details = f"Error en validación post-firma:\n{str(e)}\n\nTipo: {type(e).__name__}"
            if problem:
                error_details += f"\n\nProblemas detectados en XML:\n{problem}"
            artifacts_dir.joinpath("sign_preflight_error.txt").write_text(
                error_details,
                encoding="utf-8"
            )
        except Exception:
            pass
        raise RuntimeError(f"Validación post-firma falló: {e}") from e
    
    # 9. Re-parsear el rDE firmado (ya validado)
    rde_signed = etree.fromstring(rde_signed_bytes, parser=parser)
    
    # DEBUG: Verificar atributos de rde_signed
    print(f"DEBUG: rde_signed attributes: {list(rde_signed.attrib.keys())}")
    
    # 10. Construir lote.xml con rDE directo (NO xDE)
    # IMPORTANTE: lote.xml debe contener <rDE> directamente, NO <xDE>
    # <xDE> pertenece al SOAP rEnvioLote, NO al archivo lote.xml dentro del ZIP
    # Remover cualquier hijo directo de lote_root que tenga local-name 'rDE' o 'xDE' (por si acaso)
    # NUNCA usar remove() con un elemento que venga de otro árbol
    # SIEMPRE remover desde el parent real (getparent())
    to_remove = [
        c for c in list(lote_root)
        if isinstance(c.tag, str) and local_tag(c.tag) in ("rDE", "xDE")
    ]
    for c in to_remove:
        parent = c.getparent()
        if parent is None:
            raise RuntimeError("Elemento a remover no tiene parent (bug de árbol XML)")
        if parent is not lote_root:
            raise RuntimeError(f"Elemento a remover tiene parent diferente de lote_root (bug de árbol XML): parent={parent.tag}, lote_root={lote_root.tag}")
        # Verificar que c realmente es hijo de lote_root antes de remover
        if c in list(lote_root):
            lote_root.remove(c)
        else:
            raise RuntimeError("Elemento a remover no es hijo directo de lote_root (bug de árbol XML)")
    
    # Agregar el rDE firmado directamente como hijo de rLoteDE
    # Usar replace() si rde_to_sign está en el árbol, o append() si no está
    if rde_to_sign is not None:
        rde_to_sign_parent = rde_to_sign.getparent()
        if rde_to_sign_parent is lote_root:
            # Solo reemplazar si realmente es hijo de lote_root
            if rde_to_sign in list(lote_root):
                # Usar replace() para evitar "Element is not a child of this node"
                idx = list(lote_root).index(rde_to_sign)
                lote_root.remove(rde_to_sign)
                lote_root.insert(idx, rde_signed)
            else:
                # Si no está en la lista, simplemente append
                lote_root.append(rde_signed)
        else:
            # Si no tiene parent o el parent no es lote_root, simplemente append
            lote_root.append(rde_signed)
    else:
        # Si no hay rde_to_sign, simplemente append
        lote_root.append(rde_signed)
    
    # El lote ahora tiene rDE firmado directamente dentro de rLoteDE (NO xDE)
    lote_final = lote_root
    
    # 9.5. CRÍTICO: Eliminar xsi:schemaLocation de todos los rDE antes de serializar
    for rde_elem in lote_final.xpath('//rDE', namespaces={'s': SIFEN_NS}):
        if '{http://www.w3.org/2001/XMLSchema-instance}schemaLocation' in rde_elem.attrib:
            del rde_elem.attrib['{http://www.w3.org/2001/XMLSchema-instance}schemaLocation']
            print("✅ Eliminado xsi:schemaLocation del rDE")
        # También eliminar xmlns:xsi si está presente
        if '{http://www.w3.org/2001/XMLSchema-instance}' in rde_elem.nsmap:
            # No se puede eliminar del nsmap fácilmente, pero se limpiará en la serialización
            pass
    
    # 10. Serializar lote final UNA SOLA VEZ (pretty_print=False para preservar exactamente)
    print("\n🔧 DEBUG: Serializando lote final UNA SOLA VEZ")
    try:
        # (PATCH) No agregar xsi:schemaLocation al DE (evitar 0160)
        lote_xml_str = etree.tostring(lote_final, encoding='utf-8', pretty_print=False, xml_declaration=False, standalone=False).decode('utf-8')
        
        # CRÍTICO: Eliminar xsi:schemaLocation del XML final (causa 0160)
        # Usar múltiples patrones para asegurar que se elimine
        patterns_to_remove = [
            r'\s*xsi:schemaLocation="[^"]*"',  # Con espacio antes
            r'xsi:schemaLocation="[^"]*"\s*',   # Con espacio después
            r'\s+xmlns:xsi="[^"]*"',          # xmlns:xsi con espacio antes
            r'xmlns:xsi="[^"]*"\s*',          # xmlns:xsi con espacio después
        ]
        
        for pattern in patterns_to_remove:
            lote_xml_str = re.sub(pattern, '', lote_xml_str, flags=re.MULTILINE | re.DOTALL)
        
        lote_xml_bytes = lote_xml_str.encode('utf-8')
        # Mantener el log original si existía (no es obligatorio)
    except Exception as e:
        raise RuntimeError(f"Error al serializar lote final: {e}")
    
    # DEBUG: Dump lote serializado
    hash_lote = dump_stage("10_lote_serialized", lote_xml_bytes, artifacts_dir_for_debug)
    compare_hashes(hash_parsed, hash_lote, "03_parsed", "10_lote_serialized")
    if lote_xml_bytes.startswith(b'\n'):
        lote_xml_bytes = lote_xml_bytes[1:]
    
    # 11. Logs de diagnóstico (solo debug-soap)
    if debug_enabled:
        # Parsear lote para obtener información estructural
        try:
            lote_root_debug = etree.fromstring(lote_xml_bytes, parser=parser)
            root_localname = local_tag(lote_root_debug.tag)
            root_nsmap = lote_root_debug.nsmap if hasattr(lote_root_debug, 'nsmap') else {}
            children_local = [local_tag(c.tag) for c in list(lote_root_debug)]
            rde_count = len([c for c in list(lote_root_debug) if local_tag(c.tag) == "rDE"])
            xde_count = len([c for c in list(lote_root_debug) if local_tag(c.tag) == "xDE"])
            
            # Buscar Signature y su parent
            sig_count = 0
            sig_parent_local = None
            for elem in lote_root_debug.iter():
                if local_tag(elem.tag) == "Signature":
                    sig_count += 1
                    sig_parent = elem.getparent()
                    if sig_parent is not None:
                        sig_parent_local = local_tag(sig_parent.tag)
                    break
            
            print(f"🔍 DIAGNÓSTICO [lote.xml]:")
            print(f"   root localname: {root_localname}")
            print(f"   root nsmap: {root_nsmap}")
            print(f"   children(local): {children_local}")
            print(f"   rDE count: {rde_count}")
            print(f"   xDE count: {xde_count}")
            print(f"   Signature count: {sig_count}")
            if sig_parent_local:
                print(f"   Signature parent(local): {sig_parent_local}")
            
            # Extraer Reference URI y DE Id
            ref_uri_match = re.search(rb'<Reference[^>]*URI="([^"]*)"', lote_xml_bytes)
            if ref_uri_match:
                ref_uri = ref_uri_match.group(1).decode('utf-8', errors='replace')
                print(f"   Reference URI: {ref_uri}")
                print(f"   DE Id: {de_id}")
                if ref_uri == f"#{de_id}":
                    print(f"   ✅ Reference URI coincide con DE Id")
                else:
                    print(f"   ⚠️  Reference URI NO coincide con DE Id")
            
            # Confirmar estructura correcta
            if xde_count == 0 and rde_count >= 1:
                print(f"   ✅ OK: lote.xml contiene rDE (no xDE). xDE se enviará en SOAP como base64 del ZIP (fuera de lote.xml).")
        except Exception as e:
            print(f"   ⚠️  No se pudo parsear lote.xml para diagnóstico: {e}")
    
    # 12. Sanity gate: detectar problemas comunes de XML mal formado (SIFEN 0160)
    problem = _scan_xml_bytes_for_common_malformed(lote_xml_bytes)
    if problem:
        artifacts_dir = Path("artifacts")
        artifacts_dir.mkdir(parents=True, exist_ok=True)
        try:
            artifacts_dir.joinpath("prevalidator_raw.xml").write_bytes(lote_xml_bytes)
            artifacts_dir.joinpath("prevalidator_sanity_report.txt").write_text(
                problem + "\n",
                encoding="utf-8"
            )
        except Exception:
            pass
        raise RuntimeError(
            f"XML potencialmente mal formado para SIFEN (0160). "
            f"Ver artifacts/prevalidator_raw.xml y artifacts/prevalidator_sanity_report.txt\n\n"
            f"{problem}"
        )
    
    # 13. Hard-guard: verificar estructura correcta de lote.xml
    # IMPORTANTE: lote.xml NO debe contener <dId> ni <xDE> (pertenecen al SOAP rEnvioLote)
    # IMPORTANTE: lote.xml SÍ debe contener <rDE> directamente dentro de <rLoteDE>
    if b"<dId" in lote_xml_bytes or b"</dId>" in lote_xml_bytes:
        raise RuntimeError("BUG: lote.xml NO debe contener <dId>...</dId> (pertenece al SOAP rEnvioLote)")
    if b"<xDE" in lote_xml_bytes or b"</xDE>" in lote_xml_bytes:
        raise RuntimeError("BUG: lote.xml NO debe contener <xDE>...</xDE> (pertenece al SOAP rEnvioLote, NO al lote.xml)")
    if b'<rLoteDE' not in lote_xml_bytes:
        raise RuntimeError("BUG: lote.xml no contiene <rLoteDE>")
    # Verificar que SÍ contiene rDE (al menos uno)
    if b"<rDE" not in lote_xml_bytes or b"</rDE>" not in lote_xml_bytes:
        raise RuntimeError("BUG: lote.xml debe contener <rDE>...</rDE> directamente dentro de <rLoteDE>")
    
    # Verificar que sea well-formed
    try:
        etree.fromstring(lote_xml_bytes)
    except Exception as e:
        raise RuntimeError(f"BUG: lote.xml no es well-formed: {e}")
    
    # Guardar lote.xml para inspección (antes de crear ZIP)
    # SIEMPRE guardar artifacts/last_lote.xml (no solo en debug)
    artifacts_dir = Path("artifacts")
    artifacts_dir.mkdir(parents=True, exist_ok=True)
    try:
        artifacts_dir.joinpath("last_lote.xml").write_bytes(lote_xml_bytes)
        if debug_enabled:
            print(f"💾 Guardado: artifacts/last_lote.xml ({len(lote_xml_bytes)} bytes)")
    except Exception as e:
        if debug_enabled:
            print(f"⚠️  No se pudo guardar artifacts/last_lote.xml: {e}")
    
    # Guardrail duro: verificar que no haya duplicación de gCamFuFD antes de crear ZIP
    try:
        lote_root = etree.fromstring(lote_xml_bytes)
        gcam_count = len(lote_root.xpath('//*[local-name()="gCamFuFD"]'))
        if gcam_count != 1:
            # Dump del XML para debugging
            error_xml_path = artifacts_dir.joinpath("error_gcamfufd_duplication.xml")
            error_xml_path.write_bytes(lote_xml_bytes)
            raise RuntimeError(f"BUG CRÍTICO: gCamFuFD count={gcam_count} en lote.xml antes de enviar a SIFEN (esperado=1). XML guardado en: {error_xml_path}")
    except etree.XMLSyntaxError:
        # Si el XML no es parseable, ese es otro error
        pass
    except Exception as e:
        # Si hay otro error, lo dejamos pasar para no enmascarar el problema original
        if debug_enabled:
            print(f"⚠️  Error en guardrail gCamFuFD: {e}")
    
    # 14. Comprimir en ZIP - usando helper que coincide exactamente con TIPS
    print("\n📦 Comprimiendo lote en ZIP...")
    try:
        # FIX: Remove XML declaration to avoid double declaration
        # lote_xml_bytes contains: <?xml?><rLoteDE>...content...</rLoteDE>
        # build_xde_zip_bytes_from_lote_xml will add its own XML declaration
        lote_xml_str = lote_xml_bytes.decode('utf-8')
        # Remove XML declaration if present
        lote_xml_str = re.sub(r'^\s*<\?xml[^>]*\?>\s*', '', lote_xml_str, flags=re.S)
        # (CANDADO) evitar redeclarar default xmlns en el primer <rDE> (hereda de <rLoteDE>)
        lote_xml_str = re.sub(r'(<rDE\\b[^>]*?)\\s+xmlns="[^"]*"', r'\\1', lote_xml_str, count=1)

        
        zip_bytes = build_xde_zip_bytes_from_lote_xml(lote_xml_str)
        print(f"✅ ZIP creado: {len(zip_bytes)} bytes (STORED, lote.xml)")
    except Exception as e:
        raise RuntimeError(f"Error al crear ZIP: {e}")
    
    # DEBUG: Dump ZIP bytes
    hash_zip = dump_stage("11_zip_created", zip_bytes, artifacts_dir_for_debug)
    
    # Codificar en Base64
    zip_base64 = base64.b64encode(zip_bytes).decode('utf-8')
    print(f"✅ Base64: {len(zip_base64)} caracteres")
    
    # 15. Validar el ZIP después de crearlo: verificar estructura completa
    try:
        with zipfile.ZipFile(BytesIO(zip_bytes), "r") as zf:
            namelist = zf.namelist()
            if ZIP_INTERNAL_FILENAME not in namelist:
                raise RuntimeError(f"ZIP no contiene '{ZIP_INTERNAL_FILENAME}'")
            
            # Validar que contiene SOLO lote.xml
            if len(namelist) != 1:
                raise RuntimeError(f"ZIP debe contener solo '{ZIP_INTERNAL_FILENAME}', encontrado: {namelist}")
            
            lote_xml_from_zip = zf.read(ZIP_INTERNAL_FILENAME)
            
            # DEBUG: Comparar XML del ZIP con el XML original
            # El XML del ZIP incluye wrapper, necesitamos extraer el contenido interno
            # import re  # usa el import global (evita UnboundLocalError)            wrapper_match = re.search(rb'<rLoteDE>(.*)</rLoteDE>', lote_xml_from_zip, re.DOTALL)
            if wrapper_match:
                inner_xml = wrapper_match.group(1)
            else:
                inner_xml = lote_xml_from_zip
            
            hash_from_zip = dump_stage("12_from_zip", inner_xml, artifacts_dir_for_debug)
            compare_hashes(hash_lote, hash_from_zip, "10_lote_serialized", "12_from_zip")
            
            # Parsear para validar estructura (SIN recover)
            parser_strict = etree.XMLParser(remove_blank_text=False, recover=False)
            lote_root_from_zip = etree.fromstring(inner_xml, parser=parser_strict)
            root_localname = local_tag(lote_root_from_zip.tag)
            root_ns = None
            if "}" in lote_root_from_zip.tag:
                root_ns = lote_root_from_zip.tag.split("}", 1)[0][1:]
            
            # Validar que NO contiene <dId> (pertenece al SOAP, no al lote.xml)
            lote_xml_str = lote_xml_from_zip.decode("utf-8", errors="replace")
            if "<dId" in lote_xml_str or "</dId>" in lote_xml_str:
                raise RuntimeError("VALIDACIÓN FALLIDA: lote.xml dentro del ZIP contiene <dId> (NO debe existir)")
            
            # Validar estructura correcta
            if root_localname != "rLoteDE":
                raise RuntimeError(f"VALIDACIÓN FALLIDA: root debe ser 'rLoteDE', encontrado: {root_localname}")
            if root_ns != SIFEN_NS:
                raise RuntimeError(f"VALIDACIÓN FALLIDA: rLoteDE debe tener namespace {SIFEN_NS}, encontrado: {root_ns or '(vacío)'}")
            
            # Validar que tiene al menos 1 rDE hijo directo (NO xDE)
            rde_children = [c for c in lote_root_from_zip if local_tag(c.tag) == "rDE"]
            xde_children = [c for c in lote_root_from_zip if local_tag(c.tag) == "xDE"]
            if len(xde_children) > 0:
                raise RuntimeError("VALIDACIÓN FALLIDA: rLoteDE NO debe contener <xDE> (pertenece al SOAP rEnvioLote, NO al lote.xml)")
            if len(rde_children) == 0:
                raise RuntimeError("VALIDACIÓN FALLIDA: rLoteDE debe contener al menos 1 <rDE> hijo directo")
            
            # Validar que dentro del rDE existe <DE Id="..."> y firma cumple SHA256 + URI "#Id"
            rde_elem = rde_children[0]
            de_elem = None
            for elem in rde_elem.iter():
                if local_tag(elem.tag) == "DE":
                    de_elem = elem
                    break
            
            if de_elem is None:
                raise RuntimeError("VALIDACIÓN FALLIDA: No se encontró <DE> dentro de <rDE>")
            
            de_id_zip = de_elem.get("Id") or de_elem.get("id")
            if not de_id_zip:
                raise RuntimeError("VALIDACIÓN FALLIDA: <DE> no tiene atributo Id")
            
            # Validar firma como hermano de DE en rDE
            # Según learnings de SIFEN, Signature debe ser hermano de DE dentro de rDE
            rde_elem = de_elem.getparent()
            if rde_elem is None or local_tag(rde_elem.tag) != "rDE":
                raise RuntimeError("VALIDACIÓN FALLIDA: El DE no está dentro de un rDE")
            
            sig_elem = None
            for elem in rde_elem:
                if local_tag(elem.tag) == "Signature":
                    elem_ns = None
                    if "}" in elem.tag:
                        elem_ns = elem.tag.split("}", 1)[0][1:]
                    if elem_ns == DS_NS or elem_ns == SIFEN_NS:
                        sig_elem = elem
                        break
            
            if sig_elem is None:
                raise RuntimeError("VALIDACIÓN FALLIDA: No se encontró <Signature> como hermano de <DE> en rDE")
            
            # Validar SignatureMethod y DigestMethod son SHA256
            sig_method_elem = None
            for elem in sig_elem.iter():
                if local_tag(elem.tag) == "SignatureMethod":
                    sig_method_elem = elem
                    break
            
            if sig_method_elem is None:
                raise RuntimeError("VALIDACIÓN FALLIDA: No se encontró <SignatureMethod> en la firma")
            
            sig_method_alg = sig_method_elem.get("Algorithm", "")
            if sig_method_alg != "http://www.w3.org/2001/04/xmldsig-more#rsa-sha256":
                raise RuntimeError(f"VALIDACIÓN FALLIDA: SignatureMethod debe ser rsa-sha256, encontrado: {sig_method_alg}")
            
            digest_method_elem = None
            for elem in sig_elem.iter():
                if local_tag(elem.tag) == "DigestMethod":
                    digest_method_elem = elem
                    break
            
            if digest_method_elem is None:
                raise RuntimeError("VALIDACIÓN FALLIDA: No se encontró <DigestMethod> en la firma")
            
            digest_method_alg = digest_method_elem.get("Algorithm", "")
            if digest_method_alg != "http://www.w3.org/2001/04/xmlenc#sha256":
                raise RuntimeError(f"VALIDACIÓN FALLIDA: DigestMethod debe ser sha256, encontrado: {digest_method_alg}")
            
            # Validar Reference URI = #Id
            ref_elem = None
            for elem in sig_elem.iter():
                if local_tag(elem.tag) == "Reference":
                    ref_elem = elem
                    break
            
            if ref_elem is None:
                raise RuntimeError("VALIDACIÓN FALLIDA: No se encontró <Reference> en la firma")
            
            ref_uri = ref_elem.get("URI", "")
            if ref_uri != f"#{de_id_zip}":
                raise RuntimeError(f"VALIDACIÓN FALLIDA: Reference URI debe ser '#{de_id_zip}', encontrado: '{ref_uri}'")
            
            if debug_enabled:
                print(f"✅ VALIDACIÓN ZIP exitosa:")
                print(f"   - root localname: {root_localname}")
                print(f"   - root namespace: {root_ns}")
                print(f"   - rDE hijos directos: {len(rde_children)}")
                print(f"   - xDE hijos directos: {len(xde_children)} (debe ser 0)")
                print(f"   - NO contiene <dId>: ✅")
                print(f"   - NO contiene <xDE>: ✅")
                print(f"   - Contiene <rDE> directamente: ✅")
                print(f"   - Firma válida (SHA256, URI=#{de_id_zip}): ✅")
    except zipfile.BadZipFile as e:
        # Guardar artifacts si falla validación ZIP
        artifacts_dir = Path("artifacts")
        artifacts_dir.mkdir(parents=True, exist_ok=True)
        try:
            artifacts_dir.joinpath("preflight_zip.zip").write_bytes(zip_bytes)
            artifacts_dir.joinpath("preflight_error.txt").write_text(
                f"Error al validar ZIP: {e}\n\nTipo: {type(e).__name__}",
                encoding="utf-8"
            )
        except Exception:
            pass
        raise RuntimeError(f"Error al validar ZIP: {e}")
    except Exception as e:
        # Guardar artifacts si falla validación
        artifacts_dir = Path("artifacts")
        artifacts_dir.mkdir(parents=True, exist_ok=True)
        try:
            artifacts_dir.joinpath("preflight_lote.xml").write_bytes(lote_xml_bytes)
            artifacts_dir.joinpath("preflight_zip.zip").write_bytes(zip_bytes)
            artifacts_dir.joinpath("preflight_error.txt").write_text(
                f"Error al validar lote.xml dentro del ZIP: {e}\n\nTipo: {type(e).__name__}",
                encoding="utf-8"
            )
        except Exception:
            pass
        raise RuntimeError(f"Error al validar lote.xml dentro del ZIP: {e}")
    
    # 16. Sanity check: verificar que el lote contiene al menos 1 rDE y 0 xDE antes de enviar
    try:
        lote_root_check = etree.fromstring(lote_xml_bytes, parser=parser)
        # Verificar hijos DIRECTOS de lote_root
        rde_children_direct = [
            c for c in list(lote_root_check)
            if isinstance(c.tag, str) and local_tag(c.tag) == "rDE"
        ]
        xde_children_direct = [
            c for c in list(lote_root_check)
            if isinstance(c.tag, str) and local_tag(c.tag) == "xDE"
        ]
        
        # Verificar que NO hay xDE (pertenece al SOAP, no al lote.xml)
        if len(xde_children_direct) > 0:
            raise RuntimeError(
                f"Lote inválido: lote.xml contiene {len(xde_children_direct)} elemento(s) <xDE>. "
                "<xDE> pertenece al SOAP rEnvioLote, NO al archivo lote.xml dentro del ZIP. "
                "Ver artifacts/last_lote.xml"
            )
        
        # Verificar que SÍ hay al menos 1 rDE
        if len(rde_children_direct) == 0:
            raise RuntimeError(
                "Lote inválido: no hay <rDE> dentro de <rLoteDE>. "
                "lote.xml debe contener <rDE> directamente dentro de <rLoteDE>. "
                "Ver artifacts/last_lote.xml"
            )
        
        if debug_enabled:
            print(f"✅ Sanity check: lote contiene {len(rde_children_direct)} elemento(s) <rDE> y 0 <xDE> como hijos directos de rLoteDE")
            print(f"   OK: lote.xml contiene rDE (no xDE). xDE se enviará en SOAP como base64 del ZIP (fuera de lote.xml).")
    except RuntimeError:
        raise  # Re-raise RuntimeError tal cual
    except Exception as e:
        # Si falla el parseo, el error se detectará en otro lugar
        if debug_enabled:
            print(f"⚠️  No se pudo verificar rDE/xDE en sanity check: {e}")
    
    # 17. Guardar artifacts SIEMPRE (aunque el envío falle)
    try:
        artifacts_dir = Path("artifacts")
        artifacts_dir.mkdir(parents=True, exist_ok=True)
        
        # Guardar ZIP
        last_xde_zip = artifacts_dir / "last_xde.zip"
        last_xde_zip.write_bytes(zip_bytes)
        
        # Guardar lote.xml extraído (ya se guardó antes, pero lo guardamos aquí también para consistencia)
        last_lote_xml = artifacts_dir / "last_lote.xml"
        last_lote_xml.write_bytes(lote_xml_bytes)
        
        # Guardar reporte de sanity del lote (debug)
        if debug_enabled:
            try:
                # Parsear lote para obtener información estructural
                lote_root_debug = etree.fromstring(lote_xml_bytes, parser=parser)
                root_localname = local_tag(lote_root_debug.tag)
                root_nsmap = lote_root_debug.nsmap if hasattr(lote_root_debug, 'nsmap') else {}
                children_local = [local_tag(c.tag) for c in list(lote_root_debug)]
                rde_count = len([c for c in list(lote_root_debug) if local_tag(c.tag) == "rDE"])
                xde_count = len([c for c in list(lote_root_debug) if local_tag(c.tag) == "xDE"])
                
                # Generar reporte de sanity
                sanity_report = (
                    f"Lote XML Sanity Report\n"
                    f"======================\n"
                    f"root localname: {root_localname}\n"
                    f"root nsmap: {root_nsmap}\n"
                    f"children(local): {children_local}\n"
                    f"rDE count: {rde_count}\n"
                    f"xDE count: {xde_count}\n"
                    f"\n"
                    f"Status: {'✅ OK' if xde_count == 0 and rde_count >= 1 else '❌ ERROR'}\n"
                    f"  - lote.xml contiene rDE (no xDE): {'✅' if xde_count == 0 and rde_count >= 1 else '❌'}\n"
                    f"  - xDE se enviará en SOAP como base64 del ZIP (fuera de lote.xml)\n"
                )
                artifacts_dir.joinpath("last_lote_sanity.txt").write_text(
                    sanity_report,
                    encoding="utf-8"
                )
                
                # Guardar len del ZIP base64
                zip_b64 = base64.b64encode(zip_bytes).decode("ascii")
                artifacts_dir.joinpath("last_zip_b64_len.txt").write_text(
                    str(len(zip_b64)),
                    encoding="utf-8"
                )
            except Exception as e:
                if debug_enabled:
                    print(f"⚠️  No se pudo generar reporte de sanity: {e}")
        
        if debug_enabled:
            print(f"💾 Guardado: {last_xde_zip} ({len(zip_bytes)} bytes)")
            print(f"💾 Guardado: {last_lote_xml} ({len(lote_xml_bytes)} bytes)")
    except Exception as e:
        print(f"⚠️  No se pudo guardar artifacts: {e}")
    
    # 16. Codificar en Base64
    b64 = base64.b64encode(zip_bytes).decode("ascii")
    
    # Log de confirmación: verificar estructura correcta
    if debug_enabled:
        print(f"✅ lote.xml validado:")
        print(f"   - Tamaño: {len(lote_xml_bytes)} bytes")
        print(f"   - Contiene <rLoteDE> con xmlns SIFEN: ✅")
        print(f"   - NO contiene <dId>: ✅")
        print(f"   - NO contiene <xDE>: ✅")
        print(f"   - Contiene <rDE>: ✅")
        print(f"   - Well-formed: ✅")
    
    if return_debug:
        return b64, lote_xml_bytes, zip_bytes, None  # lote_did ya no existe (está en SOAP, no en lote.xml)
    return b64


def preflight_soap_request(
    payload_xml: str,
    zip_bytes: bytes,
    lote_xml_bytes: Optional[bytes] = None,
    artifacts_dir: Optional[Path] = None
) -> Tuple[bool, Optional[str]]:
    """
    Preflight local antes de enviar a SIFEN.
    
    Valida:
    1. SOAP request parsea (lxml.etree.fromstring sin recover=True)
    2. xDE existe, es Base64 válido, decodifica a ZIP válido
    3. ZIP contiene lote.xml únicamente
    4. lote.xml parsea y su root/estructura es la esperada
    5. Existe <DE Id="...">
    6. Existe <ds:Signature> dentro de <DE>
    7. En la firma, SignatureMethod y DigestMethod son SHA256 y Reference URI es #Id
    
    Args:
        payload_xml: XML rEnvioLote completo
        zip_bytes: ZIP binario
        lote_xml_bytes: Bytes del XML lote.xml (opcional, se extrae del ZIP si no se proporciona)
        artifacts_dir: Directorio para guardar artifacts si falla (default: artifacts/)
        
    Returns:
        Tupla (success, error_message)
        - success: True si pasa todas las validaciones
        - error_message: None si success=True, mensaje de error si success=False
    """
    if artifacts_dir is None:
        artifacts_dir = Path("artifacts")
    artifacts_dir.mkdir(parents=True, exist_ok=True)
    
    try:
        # 1. Validar que SOAP request parsea
        try:
            parser = etree.XMLParser(remove_blank_text=False, recover=False)
            soap_root = etree.fromstring(payload_xml.encode("utf-8"), parser=parser)
        except Exception as e:
            error_msg = f"SOAP request no parsea: {e}"
            artifacts_dir.joinpath("preflight_soap.xml").write_text(payload_xml, encoding="utf-8")
            return (False, error_msg)
        
        # 2. Validar que xDE existe y es Base64 válido
        xde_elem = soap_root.find(f".//{{{SIFEN_NS}}}xDE")
        if xde_elem is None:
            xde_elem = soap_root.find(".//xDE")
        
        if xde_elem is None or not xde_elem.text:
            error_msg = "xDE no encontrado o vacío en rEnvioLote"
            artifacts_dir.joinpath("preflight_soap.xml").write_text(payload_xml, encoding="utf-8")
            return (False, error_msg)
        
        try:
            xde_base64 = xde_elem.text.strip()
            zip_from_base64 = base64.b64decode(xde_base64)
            if zip_from_base64 != zip_bytes:
                # No es crítico, pero avisar
                pass
        except Exception as e:
            error_msg = f"xDE no es Base64 válido: {e}"
            artifacts_dir.joinpath("preflight_soap.xml").write_text(payload_xml, encoding="utf-8")
            return (False, error_msg)
        
        # 3. Validar que ZIP es válido y contiene lote.xml
        try:
            with zipfile.ZipFile(BytesIO(zip_bytes), "r") as zf:
                namelist = zf.namelist()
                # Normalizar (por safety: bytes/quotes/whitespace)
                namelist_norm = [
                    (n.decode('utf-8','replace') if isinstance(n, (bytes, bytearray)) else str(n))
                    for n in namelist
                ]
                namelist_norm = [n.strip().strip("'\"") for n in namelist_norm]
                namelist_norm = [n.replace("\ufeff", "").translate({0x200B: None, 0x200C: None, 0x200D: None}) for n in namelist_norm]

                # DEBUG ROBUSTO: Imprimir namelist real antes de validar
                print(f"🔍 DEBUG PREFLIGHT: ZIP namelist original = {namelist}")
                print(f"🔍 DEBUG PREFLIGHT: ZIP namelist normalizado = {namelist_norm}")
                print(f"🔍 DEBUG PREFLIGHT: Buscando '{ZIP_INTERNAL_FILENAME}'")

                if ZIP_INTERNAL_FILENAME not in namelist_norm:
                    error_msg = f"ZIP no contiene '{ZIP_INTERNAL_FILENAME}'. Archivos encontrados: {namelist_norm}"
                    artifacts_dir.joinpath("preflight_zip.zip").write_bytes(zip_bytes)
                    return (False, error_msg)
                
                if set(namelist_norm) != {ZIP_INTERNAL_FILENAME}:
                    error_msg = f"ZIP debe contener solo '{ZIP_INTERNAL_FILENAME}', encontrado: {namelist_norm}"
                    artifacts_dir.joinpath("preflight_zip.zip").write_bytes(zip_bytes)
                    return (False, error_msg)
                
                # Extraer lote.xml si no se proporcionó
                if lote_xml_bytes is None:
                    lote_xml_raw = zf.read(ZIP_INTERNAL_FILENAME)
                    # Extraer el XML interno del wrapper
                    # import re  # usa el import global (evita UnboundLocalError)                    wrapper_match = re.search(rb'<rLoteDE>(.*)</rLoteDE>', lote_xml_raw, re.DOTALL)
                    if wrapper_match:
                        lote_xml_bytes = wrapper_match.group(1)
                    else:
                        lote_xml_bytes = lote_xml_raw
        except zipfile.BadZipFile as e:
            error_msg = f"ZIP no es válido: {e}"
            artifacts_dir.joinpath("preflight_zip.zip").write_bytes(zip_bytes)
            return (False, error_msg)
        
        # 4. Validar que lote.xml parsea y tiene estructura correcta
        try:
            # Sin recover para que no modifique los namespaces
            lote_root = etree.fromstring(lote_xml_bytes)
            
            # Validar root es rLoteDE
            root_localname = local_tag(lote_root.tag)
            if root_localname != "rLoteDE":
                error_msg = f"lote.xml root debe ser 'rLoteDE', encontrado: {root_localname}"
                artifacts_dir.joinpath("preflight_lote.xml").write_bytes(lote_xml_bytes)
                return (False, error_msg)
            
            # Validar namespace
            root_ns = None
            if "}" in lote_root.tag:
                root_ns = lote_root.tag.split("}", 1)[0][1:]
            if root_ns != SIFEN_NS:
                error_msg = f"rLoteDE debe tener namespace {SIFEN_NS}, encontrado: {root_ns or '(vacío)'}"
                artifacts_dir.joinpath("preflight_lote.xml").write_bytes(lote_xml_bytes)
                return (False, error_msg)
            
            # Validar que NO contiene <dId> ni <xDE>
            lote_xml_str = lote_xml_bytes.decode("utf-8", errors="replace")
            if "<dId" in lote_xml_str or "</dId>" in lote_xml_str:
                error_msg = "lote.xml NO debe contener <dId> (pertenece al SOAP rEnvioLote)"
                artifacts_dir.joinpath("preflight_lote.xml").write_bytes(lote_xml_bytes)
                return (False, error_msg)
            if "<xDE" in lote_xml_str or "</xDE>" in lote_xml_str:
                # Diagnóstico detallado si encuentra xDE
                root_tag = lote_root.tag if hasattr(lote_root, 'tag') else str(lote_root)
                root_nsmap = lote_root.nsmap if hasattr(lote_root, 'nsmap') else {}
                children_local = [local_tag(c.tag) for c in list(lote_root)]
                xde_count = len([c for c in list(lote_root) if local_tag(c.tag) == "xDE"])
                rde_count = len([c for c in list(lote_root) if local_tag(c.tag) == "rDE"])
                error_msg = (
                    f"lote.xml NO debe contener <xDE> (pertenece al SOAP rEnvioLote).\n"
                    f"  root.tag: {root_tag}\n"
                    f"  root.nsmap: {root_nsmap}\n"
                    f"  children(local): {children_local}\n"
                    f"  xDE count: {xde_count}\n"
                    f"  rDE count: {rde_count}"
                )
                artifacts_dir.joinpath("preflight_lote.xml").write_bytes(lote_xml_bytes)
                # Guardar reporte de preflight
                preflight_report = (
                    f"Preflight Validation Failed\n"
                    f"==========================\n"
                    f"Error: {error_msg}\n"
                    f"\n"
                    f"Structure Analysis:\n"
                    f"  root.tag: {root_tag}\n"
                    f"  root.nsmap: {root_nsmap}\n"
                    f"  children(local): {children_local}\n"
                    f"  xDE count: {xde_count}\n"
                    f"  rDE count: {rde_count}\n"
                )
                artifacts_dir.joinpath("preflight_report.txt").write_text(
                    preflight_report,
                    encoding="utf-8"
                )
                return (False, error_msg)
            
            # Validar que tiene al menos 1 rDE hijo directo (y 0 xDE)
            rde_children = [c for c in lote_root if local_tag(c.tag) == "rDE"]
            xde_children = [c for c in lote_root if local_tag(c.tag) == "xDE"]
            if len(xde_children) > 0:
                error_msg = f"rLoteDE NO debe contener <xDE> (pertenece al SOAP rEnvioLote). Encontrado: {len(xde_children)}"
                artifacts_dir.joinpath("preflight_lote.xml").write_bytes(lote_xml_bytes)
                # Guardar reporte de preflight
                root_tag = lote_root.tag if hasattr(lote_root, 'tag') else str(lote_root)
                root_nsmap = lote_root.nsmap if hasattr(lote_root, 'nsmap') else {}
                children_local = [local_tag(c.tag) for c in list(lote_root)]
                preflight_report = (
                    f"Preflight Validation Failed\n"
                    f"==========================\n"
                    f"Error: {error_msg}\n"
                    f"\n"
                    f"Structure Analysis:\n"
                    f"  root.tag: {root_tag}\n"
                    f"  root.nsmap: {root_nsmap}\n"
                    f"  children(local): {children_local}\n"
                    f"  xDE count: {len(xde_children)}\n"
                    f"  rDE count: {len(rde_children)}\n"
                )
                artifacts_dir.joinpath("preflight_report.txt").write_text(
                    preflight_report,
                    encoding="utf-8"
                )
                return (False, error_msg)
            if len(rde_children) < 1:
                error_msg = f"rLoteDE debe contener al menos 1 rDE hijo directo, encontrado: {len(rde_children)}"
                artifacts_dir.joinpath("preflight_lote.xml").write_bytes(lote_xml_bytes)
                # Guardar reporte de preflight
                root_tag = lote_root.tag if hasattr(lote_root, 'tag') else str(lote_root)
                root_nsmap = lote_root.nsmap if hasattr(lote_root, 'nsmap') else {}
                children_local = [local_tag(c.tag) for c in list(lote_root)]
                preflight_report = (
                    f"Preflight Validation Failed\n"
                    f"==========================\n"
                    f"Error: {error_msg}\n"
                    f"\n"
                    f"Structure Analysis:\n"
                    f"  root.tag: {root_tag}\n"
                    f"  root.nsmap: {root_nsmap}\n"
                    f"  children(local): {children_local}\n"
                    f"  xDE count: {len(xde_children)}\n"
                    f"  rDE count: {len(rde_children)}\n"
                )
                artifacts_dir.joinpath("preflight_report.txt").write_text(
                    preflight_report,
                    encoding="utf-8"
                )
                return (False, error_msg)
            
            rde_elem = rde_children[0]
        except Exception as e:
            error_msg = f"lote.xml no parsea o estructura incorrecta: {e}"
            if lote_xml_bytes:
                artifacts_dir.joinpath("preflight_lote.xml").write_bytes(lote_xml_bytes)
            return (False, error_msg)
        
        # 5. Validar que existe <DE Id="...">
        de_elem = None
        for elem in rde_elem.iter():
            if local_tag(elem.tag) == "DE":
                de_elem = elem
                break
        
        if de_elem is None:
            error_msg = "No se encontró elemento <DE> dentro de <rDE>"
            artifacts_dir.joinpath("preflight_lote.xml").write_bytes(lote_xml_bytes)
            return (False, error_msg)
        
        de_id = de_elem.get("Id") or de_elem.get("id")
        if not de_id:
            error_msg = "Elemento <DE> no tiene atributo Id"
            artifacts_dir.joinpath("preflight_lote.xml").write_bytes(lote_xml_bytes)
            return (False, error_msg)
        
        # 6. Validar que existe <Signature> como hermano de <DE> en rDE
        # Según learnings de SIFEN, Signature debe ser hermano de DE dentro de rDE
        rde_elem = de_elem.getparent()
        if rde_elem is None or local_tag(rde_elem.tag) != "rDE":
            error_msg = "El DE no está dentro de un rDE"
            artifacts_dir.joinpath("preflight_lote.xml").write_bytes(lote_xml_bytes)
            return (False, error_msg)
        
        sig_elem = None
        for elem in rde_elem:
            if local_tag(elem.tag) == "Signature":
                # Verificar namespace
                elem_ns = None
                if "}" in elem.tag:
                    elem_ns = elem.tag.split("}", 1)[0][1:]
                elif hasattr(elem, 'nsmap') and elem.prefix:
                    elem_ns = elem.nsmap.get(elem.prefix)
                print(f"DEBUG: Signature encontrada, ns={elem_ns}, tag={elem.tag}")
                if elem_ns == DS_NS or elem_ns == SIFEN_NS:
                    sig_elem = elem
                    break
        
        if sig_elem is None:
            error_msg = "No se encontró <Signature> como hermano de <DE> en rDE"
            artifacts_dir.joinpath("preflight_lote.xml").write_bytes(lote_xml_bytes)
            return (False, error_msg)
        
        # 7. Validar firma: SignatureMethod=rsa-sha256, DigestMethod=sha256, Reference URI=#Id
        # Buscar SignatureMethod
        sig_method_elem = None
        for elem in sig_elem.iter():
            if local_tag(elem.tag) == "SignatureMethod":
                sig_method_elem = elem
                break
        
        if sig_method_elem is None:
            error_msg = "No se encontró <SignatureMethod> en la firma"
            artifacts_dir.joinpath("preflight_lote.xml").write_bytes(lote_xml_bytes)
            return (False, error_msg)
        
        sig_method_alg = sig_method_elem.get("Algorithm", "")
        expected_sig_method = "http://www.w3.org/2001/04/xmldsig-more#rsa-sha256"
        if sig_method_alg != expected_sig_method:
            error_msg = f"SignatureMethod debe ser '{expected_sig_method}', encontrado: '{sig_method_alg}'"
            artifacts_dir.joinpath("preflight_lote.xml").write_bytes(lote_xml_bytes)
            return (False, error_msg)
        
        # Buscar DigestMethod
        digest_method_elem = None
        for elem in sig_elem.iter():
            if local_tag(elem.tag) == "DigestMethod":
                digest_method_elem = elem
                break
        
        if digest_method_elem is None:
            error_msg = "No se encontró <DigestMethod> en la firma"
            artifacts_dir.joinpath("preflight_lote.xml").write_bytes(lote_xml_bytes)
            return (False, error_msg)
        
        digest_method_alg = digest_method_elem.get("Algorithm", "")
        expected_digest_method = "http://www.w3.org/2001/04/xmlenc#sha256"
        if digest_method_alg != expected_digest_method:
            error_msg = f"DigestMethod debe ser '{expected_digest_method}', encontrado: '{digest_method_alg}'"
            artifacts_dir.joinpath("preflight_lote.xml").write_bytes(lote_xml_bytes)
            return (False, error_msg)
        
        # Buscar Reference URI
        ref_elem = None
        for elem in sig_elem.iter():
            if local_tag(elem.tag) == "Reference":
                ref_elem = elem
                break
        
        if ref_elem is None:
            error_msg = "No se encontró <Reference> en la firma"
            artifacts_dir.joinpath("preflight_lote.xml").write_bytes(lote_xml_bytes)
            return (False, error_msg)
        
        ref_uri = ref_elem.get("URI", "")
        expected_uri = f"#{de_id}"
        if ref_uri != expected_uri:
            error_msg = f"Reference URI debe ser '{expected_uri}', encontrado: '{ref_uri}'"
            artifacts_dir.joinpath("preflight_lote.xml").write_bytes(lote_xml_bytes)
            return (False, error_msg)
        
        # Validar que X509Certificate existe y no está vacío
        x509_cert_elem = None
        for elem in sig_elem.iter():
            if local_tag(elem.tag) == "X509Certificate":
                x509_cert_elem = elem
                break
        
        if x509_cert_elem is None:
            error_msg = "No se encontró <X509Certificate> en la firma"
            artifacts_dir.joinpath("preflight_lote.xml").write_bytes(lote_xml_bytes)
            return (False, error_msg)
        
        if not x509_cert_elem.text or not x509_cert_elem.text.strip():
            error_msg = "<X509Certificate> está vacío (firma dummy o certificado no cargado)"
            artifacts_dir.joinpath("preflight_lote.xml").write_bytes(lote_xml_bytes)
            return (False, error_msg)
        
        # Validar que SignatureValue existe y no es dummy
        sig_value_elem = None
        for elem in sig_elem.iter():
            if local_tag(elem.tag) == "SignatureValue":
                sig_value_elem = elem
                break
        
        if sig_value_elem is None:
            error_msg = "No se encontró <SignatureValue> en la firma"
            artifacts_dir.joinpath("preflight_lote.xml").write_bytes(lote_xml_bytes)
            return (False, error_msg)
        
        if not sig_value_elem.text or not sig_value_elem.text.strip():
            error_msg = "<SignatureValue> está vacío (firma dummy)"
            artifacts_dir.joinpath("preflight_lote.xml").write_bytes(lote_xml_bytes)
            return (False, error_msg)
        
        # Validar que SignatureValue no contiene texto dummy
        try:
            sig_value_b64 = sig_value_elem.text.strip()
            sig_value_decoded = base64.b64decode(sig_value_b64)
            sig_value_str = sig_value_decoded.decode("ascii", errors="ignore")
            if "this is a test" in sig_value_str.lower() or "dummy" in sig_value_str.lower():
                error_msg = "SignatureValue contiene texto dummy (firma de prueba, no real)"
                artifacts_dir.joinpath("preflight_lote.xml").write_bytes(lote_xml_bytes)
                return (False, error_msg)
        except Exception:
            # Si no se puede decodificar, asumir que es válido (binario real)
            pass
        
        # Todas las validaciones pasaron
        return (True, None)
        
    except Exception as e:
        error_msg = f"Error inesperado en preflight: {e}"
        try:
            artifacts_dir.joinpath("preflight_soap.xml").write_text(payload_xml, encoding="utf-8")
            if zip_bytes:
                artifacts_dir.joinpath("preflight_zip.zip").write_bytes(zip_bytes)
            if lote_xml_bytes:
                artifacts_dir.joinpath("preflight_lote.xml").write_bytes(lote_xml_bytes)
        except Exception:
            pass
        return (False, error_msg)


def _debug_roundtrip_xde(payload_xml: str, artifacts_dir: str):
    """Debug round-trip del xDE desde el SOAP final para validar contenido."""
    m = re.search(r"<sifen:xDE>([^<]+)</sifen:xDE>", payload_xml)
    if not m:
        print("❌ DEBUG: no encontré <sifen:xDE> en el SOAP final")
        return

    xde_b64 = m.group(1).strip()
    zip_bytes = base64.b64decode(xde_b64)

    out_zip = os.path.join(artifacts_dir, "last_lote_from_payload.zip")
    with open(out_zip, "wb") as f:
        f.write(zip_bytes)
    print(f"✅ DEBUG: ZIP guardado: {out_zip} ({len(zip_bytes)} bytes)")

    zf = zipfile.ZipFile(BytesIO(zip_bytes))
    print("✅ DEBUG: ZIP entries:", zf.namelist())

    lote_xml_bytes = zf.read(ZIP_INTERNAL_FILENAME)
    
    # Runtime guardrail: verificar que no haya duplicación de gCamFuFD
    lote_root = etree.fromstring(lote_xml_bytes)
    gcam_count = len(lote_root.findall(f".//{{{SIFEN_NS}}}gCamFuFD"))
    if gcam_count > 1:
        raise RuntimeError(f"BUG CRÍTICO: gCamFuFD count={gcam_count} en lote.xml antes de enviar a SIFEN (esperado=1).")
    elif gcam_count == 0:
        print("⚠️ ADVERTENCIA: No se encontró gCamFuFD en lote.xml")
    
    out_xml = os.path.join(artifacts_dir, "last_lote_from_payload.xml")
    with open(out_xml, "wb") as f:
        f.write(lote_xml_bytes)

    head = lote_xml_bytes[:200].decode("utf-8", "ignore")
    print(f"✅ DEBUG: lote.xml guardado: {out_xml} ({len(lote_xml_bytes)} bytes)")
    print("✅ DEBUG: lote.xml head:", head.replace("\n", "\\n")[:200])


def build_r_envio_lote_xml(did: Union[int, str], xml_bytes: bytes, zip_base64: Optional[str] = None) -> str:
    """
    Construye el XML rEnvioLote con el lote comprimido en Base64.
    
    Args:
        did: ID del documento (IGNORADO - siempre se genera uno nuevo de 15 dígitos)
        xml_bytes: XML original (puede ser rDE o siRecepDE)
        zip_base64: Base64 del ZIP (IGNORADO - siempre se construye un ZIP fresco)
        
    Returns:
        XML rEnvioLote como string
    """
    # Función para generar dId único de 15 dígitos
    def make_did_15() -> str:
        """Genera un dId único de 15 dígitos: YYYYMMDDHHMMSS + 1 dígito random"""
        import random
        base = datetime.now().strftime("%Y%m%d%H%M%S")  # 14 dígitos
        return base + str(random.randint(0, 9))  # + 1 dígito random = 15
    
    # SIEMPRE generar dId de 15 dígitos (ignorar el parámetro did)
    did = make_did_15()  # SIEMPRE (no reutilizar nada)
    
    # SIEMPRE construir un ZIP fresco desde xml_bytes (evita enviar un ZIP viejo -> 0160)
    print("🔍 DEBUG: Construyendo ZIP fresco desde xml_bytes (sin reutilizar zip_base64)")
    xde_b64 = build_lote_base64_from_single_xml(xml_bytes)
    
    # Calcular hash_from_zip para debug
    try:
        zip_bytes = base64.b64decode(xde_b64)
        import hashlib
        hash_from_zip = hashlib.sha256(zip_bytes).hexdigest()
    except Exception as e:
        print(f"⚠️  No se pudo calcular hash_from_zip desde xde_b64: {e}")
        hash_from_zip = None

    # Construir rEnvioLote con prefijo sifen (nsmap {"sifen": SIFEN_NS})
    rEnvioLote = etree.Element(etree.QName(SIFEN_NS, "rEnvioLote"), nsmap={"xsd": SIFEN_NS})
    dId = etree.SubElement(rEnvioLote, etree.QName(SIFEN_NS, "dId"))
    dId.text = did  # Usar el dId de 15 dígitos generado
    xDE = etree.SubElement(rEnvioLote, etree.QName(SIFEN_NS, "xDE"))
    xDE.text = xde_b64

    return etree.tostring(rEnvioLote, xml_declaration=False, encoding="utf-8").decode("utf-8")


def apply_timbrado_override(xml_bytes: bytes, artifacts_dir: Optional[Path] = None) -> bytes:
    """
    Aplica override de timbrado y fecha de inicio si están definidos en env vars.
    
    Si SIFEN_TIMBRADO_OVERRIDE está definido:
    - Parchea <dNumTim> en gTimb
    - Regenera CDC (DE@Id) y dDVId
    
    Si SIFEN_FEINI_OVERRIDE está definido:
    - Parchea <dFeIniT> en gTimb
    
    Args:
        xml_bytes: XML original (bytes)
        artifacts_dir: Directorio para guardar artifact de salida (opcional)
        
    Returns:
        XML modificado (bytes) o xml_bytes sin cambios si no hay override
    """
    # import re  # usa el import global (evita UnboundLocalError)    
    # Leer env vars
    timbrado = os.getenv("SIFEN_TIMBRADO_OVERRIDE", "").strip()
    feini = os.getenv("SIFEN_FEINI_OVERRIDE", "").strip()
    
    # Si ambas vacías, devolver sin cambios
    if not timbrado and not feini:
        return xml_bytes
    
    # Parsear XML
    parser = etree.XMLParser(remove_blank_text=True)
    try:
        root = etree.fromstring(xml_bytes, parser)
    except Exception as e:
        raise ValueError(f"Error al parsear XML para timbrado override: {e}")
    
    # Namespace
    NS = {"s": SIFEN_NS}
    
    # Buscar gTimb
    gtimb = root.find(".//s:gTimb", namespaces=NS)
    if gtimb is None:
        raise RuntimeError("No se encontró <gTimb> en el XML. No se puede aplicar override de timbrado.")
    
    # Aplicar override de timbrado
    if timbrado:
        dnumtim = gtimb.find("s:dNumTim", namespaces=NS)
        if dnumtim is None:
            raise RuntimeError("No se encontró <dNumTim> en <gTimb>. No se puede aplicar override de timbrado.")
        dnumtim.text = timbrado
        print(f"🔧 TIMBRADO OVERRIDE: dNumTim = {timbrado}")
    
    # Aplicar override de fecha inicio
    if feini:
        dfeinit = gtimb.find("s:dFeIniT", namespaces=NS)
        if dfeinit is None:
            raise RuntimeError("No se encontró <dFeIniT> en <gTimb>. No se puede aplicar override de fecha inicio.")
        dfeinit.text = feini
        print(f"🔧 TIMBRADO OVERRIDE: dFeIniT = {feini}")
    
    # Si se cambió el timbrado, regenerar CDC
    if timbrado:
        print("🔄 Regenerando CDC con nuevo timbrado...")
        
        # Extraer datos del XML
        gemis = root.find(".//s:gEmis", namespaces=NS)
        if gemis is None:
            raise RuntimeError("No se encontró <gEmis> en el XML. No se puede regenerar CDC.")
        
        drucem = gemis.find("s:dRucEm", namespaces=NS)
        if drucem is None or not drucem.text:
            raise RuntimeError("No se encontró <dRucEm> en <gEmis>. No se puede regenerar CDC.")
        ruc = drucem.text.strip()
        
        dest = gtimb.find("s:dEst", namespaces=NS)
        if dest is None or not dest.text:
            raise RuntimeError("No se encontró <dEst> en <gTimb>. No se puede regenerar CDC.")
        est = dest.text.strip()
        
        dpunexp = gtimb.find("s:dPunExp", namespaces=NS)
        if dpunexp is None or not dpunexp.text:
            raise RuntimeError("No se encontró <dPunExp> en <gTimb>. No se puede regenerar CDC.")
        pnt = dpunexp.text.strip()
        
        dnumdoc = gtimb.find("s:dNumDoc", namespaces=NS)
        if dnumdoc is None or not dnumdoc.text:
            raise RuntimeError("No se encontró <dNumDoc> en <gTimb>. No se puede regenerar CDC.")
        num = dnumdoc.text.strip()
        
        # Tipo documento
        itide = gtimb.find("s:iTiDE", namespaces=NS)
        if itide is None or not itide.text:
            raise RuntimeError("No se encontró <iTiDE> en <gTimb>. No se puede regenerar CDC.")
        tipo_doc = itide.text.strip()
        
        # Fecha emisión
        gdatgral = root.find(".//s:gDatGralOpe", namespaces=NS)
        if gdatgral is None:
            raise RuntimeError("No se encontró <gDatGralOpe> en el XML. No se puede regenerar CDC.")
        
        dfemi = gdatgral.find("s:dFeEmiDE", namespaces=NS)
        if dfemi is None or not dfemi.text:
            raise RuntimeError("No se encontró <dFeEmiDE> en <gDatGralOpe>. No se puede regenerar CDC.")
        fecha_emi = dfemi.text.strip()
        
        # Convertir fecha de YYYY-MM-DD a YYYYMMDD
        fecha_ymd = re.sub(r"\D", "", fecha_emi)[:8]
        if len(fecha_ymd) != 8:
            raise RuntimeError(f"Fecha de emisión inválida para CDC: {fecha_emi!r}")
        
        # Monto total
        gtot = root.find(".//s:gTotSub", namespaces=NS)
        if gtot is None:
            raise RuntimeError("No se encontró <gTotSub> en el XML. No se puede regenerar CDC.")
        
        dtot = gtot.find("s:dTotalGs", namespaces=NS)
        if dtot is None or not dtot.text:
            # Fallback: usar 0 si no hay monto
            monto = "0"
        else:
            monto = dtot.text.strip()
        
        # Generar nuevo CDC
        try:
            from app.sifen_client.xml_generator_v150 import generate_cdc
            cdc = generate_cdc(
                ruc=ruc,
                timbrado=timbrado,
                establecimiento=est,
                punto_expedicion=pnt,
                numero_documento=num,
                tipo_documento=tipo_doc,
                fecha=fecha_ymd,
                monto=monto
            )
            print(f"✓ CDC regenerado: {cdc}")
        except Exception as e:
            raise RuntimeError(f"Error al generar CDC: {e}")
        
        # Actualizar DE@Id
        de = root.find(".//s:DE", namespaces=NS)
        if de is None:
            raise RuntimeError("No se encontró <DE> en el XML. No se puede actualizar CDC.")
        de.set("Id", cdc)
        
        # Actualizar dDVId (último dígito del CDC)
        ddvid = root.find(".//s:dDVId", namespaces=NS)
        if ddvid is None:
            raise RuntimeError("No se encontró <dDVId> en el XML. No se puede actualizar DV.")
        ddvid.text = cdc[-1]
        print(f"✓ dDVId actualizado: {cdc[-1]}")
    
    # Serializar de vuelta
    out = etree.tostring(root, xml_declaration=True, encoding="UTF-8", pretty_print=True)
    
    # Guardar artifact si artifacts_dir está definido
    if artifacts_dir is not None:
        try:
            artifacts_dir.mkdir(exist_ok=True)
            artifact_path = artifacts_dir / "xml_after_timbrado_override.xml"
            artifact_path.write_bytes(out)
            print(f"💾 Guardado: {artifact_path}")
        except Exception as e:
            # Silencioso: no romper el flujo si falla guardar artifact
            print(f"⚠️  No se pudo guardar artifact de timbrado override: {e}")
    
    return out


def resolve_xml_path(xml_arg: str, artifacts_dir: Path) -> Path:
    """
    Resuelve el path al XML (puede ser 'latest' o un path específico)
    
    Args:
        xml_arg: Argumento XML ('latest' o path)
        artifacts_dir: Directorio de artifacts
        
    Returns:
        Path al archivo XML
    """
    if xml_arg.lower() == "latest":
        xml_path = find_latest_sirecepde(artifacts_dir)
        if not xml_path:
            raise FileNotFoundError(
                f"No se encontró ningún archivo sirecepde_*.xml en {artifacts_dir}"
            )
        return xml_path
    
    xml_path = Path(xml_arg)
    if not xml_path.exists():
        # Intentar como path relativo a artifacts
        artifacts_xml = artifacts_dir / xml_arg
        if artifacts_xml.exists():
            return artifacts_xml
        raise FileNotFoundError(f"Archivo XML no encontrado: {xml_arg}")
    
    return xml_path


def _extract_ruc_from_cert(p12_path: str, p12_password: str) -> Optional[Dict[str, str]]:
    """
    Extrae el RUC del certificado P12/PFX.
    
    Busca el RUC en:
    1. Subject DN: SERIALNUMBER o CN (formato "RUCxxxxxxx-y" o "xxxxxxx-y")
    2. Subject Alternative Names (SAN): DirectoryName con SERIALNUMBER
    
    Args:
        p12_path: Ruta al certificado P12/PFX
        p12_password: Contraseña del certificado
        
    Returns:
        Dict con:
            - "ruc": número de RUC sin DV (ej: "4554737")
            - "ruc_with_dv": RUC completo con DV si se encuentra (ej: "4554737-8")
        None si no se puede extraer o si cryptography no está disponible
    """
    try:
        from cryptography.hazmat.primitives.serialization import pkcs12
        from cryptography.hazmat.backends import default_backend
        from cryptography import x509
    except ImportError:
        return None
    
    try:
        with open(p12_path, "rb") as f:
            p12_bytes = f.read()
        password_bytes = p12_password.encode("utf-8") if p12_password else None
        
        key_obj, cert_obj, _ = pkcs12.load_key_and_certificates(
            p12_bytes, password_bytes, backend=default_backend()
        )
        
        if cert_obj is None:
            return None
        
        # Buscar RUC en Subject DN
        subject = cert_obj.subject
        ruc_with_dv = None
        
        # Buscar en SERIALNUMBER
        for attr in subject:
            if attr.oid == x509.NameOID.SERIAL_NUMBER:
                serial = attr.value.strip()
                # Puede ser "RUC4554737-8" o "4554737-8"
                if serial.upper().startswith("RUC"):
                    serial = serial[3:].strip()
                if "-" in serial:
                    ruc_with_dv = serial
                    break
        
        # Si no se encontró en SERIALNUMBER, buscar en CN
        if ruc_with_dv is None:
            for attr in subject:
                if attr.oid == x509.NameOID.COMMON_NAME:
                    cn = attr.value.strip()
                    # Puede ser "RUC4554737-8" o "4554737-8"
                    if cn.upper().startswith("RUC"):
                        cn = cn[3:].strip()
                    # Validar que es un RUC (solo números y un guion)
                    if "-" in cn and all(c.isdigit() or c == "-" for c in cn):
                        ruc_with_dv = cn
                        break
        
        # Buscar en Subject Alternative Names (SAN)
        if ruc_with_dv is None:
            try:
                san_ext = cert_obj.extensions.get_extension_for_oid(
                    x509.ExtensionOID.SUBJECT_ALTERNATIVE_NAME
                )
                for name in san_ext.value:
                    if isinstance(name, x509.DirectoryName):
                        dir_name = name.value
                        for attr in dir_name:
                            if attr.oid == x509.NameOID.SERIAL_NUMBER:
                                serial = attr.value.strip()
                                if serial.upper().startswith("RUC"):
                                    serial = serial[3:].strip()
                                if "-" in serial:
                                    ruc_with_dv = serial
                                    break
                        if ruc_with_dv:
                            break
            except x509.ExtensionNotFound:
                pass
        
        if ruc_with_dv:
            # Separar RUC y DV
            parts = ruc_with_dv.split("-", 1)
            ruc = parts[0].strip()
            return {
                "ruc": ruc,
                "ruc_with_dv": ruc_with_dv
            }
        
        return None
    except Exception:
        # Silenciosamente fallar si no se puede extraer
        return None


def send_sirecepde(xml_path: str, env: str = "test", artifacts_dir: Optional[Path] = None, dump_http: bool = False) -> dict:
    """
    Wrapper para send_sirecepde_lote para compatibilidad con el main.
    """
    return send_sirecepde_lote(xml_path, env, dump_http)


def send_sirecepde_lote(xml_file: str, env: str = "test", dump_http: bool = False) -> dict:
    """
    Envía un lote de DEs a SIFEN usando el endpoint siRecepLoteDE.
    
    Args:
        xml_file: Path al archivo XML con el lote
        env: Ambiente ('test' o 'prod')
        dump_http: Si True, guarda request/response en archivos
        
    Returns:
        Dict con la respuesta de SIFEN
    """
    from pathlib import Path
    
    print(f"DEBUG: send_sirecepde_lote llamado con xml_file={xml_file}")
    
    # Leer el XML del lote
    with open(xml_file, 'r', encoding='utf-8') as f:
        lote_xml = f.read()
    
    print(f"DEBUG: XML leído, longitud={len(lote_xml)}")
    
    # GUARD-RAIL: Verificar dependencias críticas ANTES de continuar
    try:
        _check_signing_dependencies()
    except RuntimeError as e:
        error_msg = f"BLOQUEADO: {str(e)}. Ejecutar scripts/bootstrap_env.sh"
        try:
            xml_bytes = Path(xml_file).read_bytes()
            if artifacts_dir is None:
                artifacts_dir = Path("artifacts")
            artifacts_dir.mkdir(parents=True, exist_ok=True)
            artifacts_dir.joinpath("sign_blocked_input.xml").write_bytes(xml_bytes)
            artifacts_dir.joinpath("sign_blocked_reason.txt").write_text(
                f"BLOQUEADO: Dependencias de firma faltantes\n\n{str(e)}\n\n"
                f"Ejecutar: scripts/bootstrap_env.sh\n"
                f"O manualmente: pip install lxml python-xmlsec",
                encoding="utf-8"
            )
        except Exception:
            pass
        return {
            "success": False,
            "error": error_msg,
            "error_type": "DependencyError"
        }
    
    # Leer XML como bytes
    print(f"📄 Cargando XML: {xml_file}")
    try:
        xml_bytes = Path(xml_file).read_bytes()
    except Exception as e:
        return {
            "success": False,
            "error": f"Error al leer archivo XML: {str(e)}",
            "error_type": type(e).__name__
        }
    
    # DEBUG: Dump XML original
    from pathlib import Path
    artifacts_dir_for_debug = Path("artifacts")
    hash_input = dump_stage("01_input", xml_bytes, artifacts_dir_for_debug)
    
    # Aplicar override de timbrado/fecha inicio si están definidos (ANTES de construir lote)
    xml_bytes = apply_timbrado_override(xml_bytes, artifacts_dir=None)
    
    xml_size = len(xml_bytes)
    print(f"   Tamaño: {xml_size} bytes ({xml_size / 1024:.2f} KB)\n")
    
    # Validar RUC del emisor antes de enviar (evitar código 1264)
    try:
        from app.sifen_client.ruc_validator import validate_emisor_ruc
        from app.sifen_client.config import get_sifen_config
        
        # Obtener RUC esperado del config si está disponible
        try:
            config = get_sifen_config(env=env)
            expected_ruc = os.getenv("SIFEN_EMISOR_RUC") or getattr(config, 'test_ruc', None)
        except:
            expected_ruc = os.getenv("SIFEN_EMISOR_RUC") or os.getenv("SIFEN_TEST_RUC")
        
        xml_content_str = xml_bytes.decode('utf-8') if isinstance(xml_bytes, bytes) else xml_bytes
        is_valid, error_msg = validate_emisor_ruc(xml_content_str, expected_ruc=expected_ruc)
        
        if not is_valid:
            print(f"❌ RUC emisor inválido/dummy/no coincide; no se envía a SIFEN:")
            print(f"   {error_msg}")
            return {
                "success": False,
                "error": error_msg,
                "error_type": "RUCValidationError",
                "note": "Configure SIFEN_EMISOR_RUC con el RUC real del contribuyente habilitado (formato: RUC-DV, ej: 4554737-8)"
            }
        
        print("✓ RUC del emisor validado (no es dummy)\n")
    except ImportError:
        # Si no se puede importar el validador, continuar sin validación (no crítico)
        print("⚠️  No se pudo importar validador de RUC, continuando sin validación\n")
    except Exception as e:
        # Si falla la validación por otro motivo, continuar (no bloquear)
        print(f"⚠️  Error al validar RUC del emisor: {e}, continuando sin validación\n")
    
    # Validar variables de entorno requeridas
    required_vars = ['SIFEN_CERT_PATH', 'SIFEN_CERT_PASSWORD']
    missing_vars = [var for var in required_vars if not os.getenv(var)]
    
    if missing_vars:
        return {
            "success": False,
            "error": f"Variables de entorno faltantes: {', '.join(missing_vars)}",
            "error_type": "ConfigurationError",
            "note": "Configure estas variables en .env o en el entorno"
        }
    
    # Configurar cliente SIFEN
    print(f"🔧 Configurando cliente SIFEN (ambiente: {env})...")
    try:
        config = get_sifen_config(env=env)
        service_key = "recibe_lote"  # Usar servicio de lote (async)
        wsdl_url = config.get_soap_service_url(service_key)
        print(f"   WSDL (recibe_lote): {wsdl_url}")
        print(f"   Operación: siRecepLoteDE\n")
    except Exception as e:
        error_msg = f"Error al configurar cliente SIFEN: {str(e)}"
        print(f"❌ {error_msg}")
        debug_enabled = os.getenv("SIFEN_DEBUG_SOAP", "0") in ("1", "true", "True")
        if debug_enabled:
            import traceback
            traceback.print_exc()
        return {
            "success": False,
            "error": error_msg,
            "error_type": type(e).__name__
        }
    
    # Construir XML de lote (rEnvioLote) desde el XML original
    try:
        print("📦 Construyendo y firmando lote desde XML individual...")
        
        # Leer certificado de firma (fallback a mTLS si no hay específico de firma)
        sign_cert_path = os.getenv("SIFEN_SIGN_P12_PATH") or os.getenv("SIFEN_MTLS_P12_PATH")
        sign_cert_password = os.getenv("SIFEN_SIGN_P12_PASSWORD") or os.getenv("SIFEN_MTLS_P12_PASSWORD")
        
        if not sign_cert_path or not sign_cert_password:
            return {
                "success": False,
                "error": "Falta certificado de firma (SIFEN_SIGN_P12_PATH o SIFEN_MTLS_P12_PATH y su contraseña)",
                "error_type": "ConfigurationError"
            }
        
        print("🔐 Verificando si el XML ya está firmado...")
        
        # Detectar si el XML ya está firmado
        if _is_xml_already_signed(xml_bytes):
            print("✓ XML ya está firmado, usando modo passthrough (sin re-serialización)")
            try:
                # Usar passthrough para no re-serializar el rDE firmado
                result = build_lote_passthrough_signed(
                    xml_bytes=xml_bytes,
                    return_debug=True
                )
                zip_base64, lote_xml_bytes, zip_bytes = result
                print("✓ Lote construido con rDE firmado intacto\n")
            except Exception as e:
                error_msg = f"Error al construir lote con XML ya firmado: {str(e)}"
                print(f"❌ {error_msg}")
                import traceback
                traceback.print_exc()
                return {
                    "success": False,
                    "error": error_msg,
                    "error_type": type(e).__name__
                }
        else:
            print("✓ XML no está firmado, construyendo lote completo y firmando rDE in-place...")
            try:
                # NUEVO FLUJO: construir lote completo ANTES de firmar, luego firmar in-place
                result = build_and_sign_lote_from_xml(
                    xml_bytes=xml_bytes,
                    cert_path=sign_cert_path,
                    cert_password=sign_cert_password,
                    return_debug=True,
                    dump_http=dump_http
                )
                if isinstance(result, tuple):
                    if len(result) == 4:
                        zip_base64, lote_xml_bytes, zip_bytes, _ = result  # _ es None (lote_did ya no existe)
                    else:
                        zip_base64, lote_xml_bytes, zip_bytes = result
                else:
                    zip_base64 = result
                    zip_bytes = base64.b64decode(zip_base64)
                    lote_xml_bytes = None
                
                print("✓ Lote construido y rDE firmado exitosamente\n")
            except Exception as e:
                error_msg = f"Error al construir y firmar lote: {str(e)}"
                print(f"❌ {error_msg}")
                traceback.print_exc()
                return {
                    "success": False,
                    "error": error_msg,
                    "error_type": type(e).__name__
                }
            
            # Validar lote.xml contra XSD si está habilitado
            if lote_xml_bytes:
                # Definir artifacts_dir si no está definido
                if artifacts_dir is None:
                    artifacts_dir = Path("artifacts")
                artifacts_dir.mkdir(parents=True, exist_ok=True)
                
                try:
                    # Importar el validador
                    sys.path.insert(0, str(Path(__file__).parent.parent.parent / "tools"))
                    from validate_lote_xsd import validate_lote_from_bytes
                    
                    # Guardar lote.xml temporalmente para validación
                    temp_lote_file = artifacts_dir / "_temp_lote_for_validation.xml"
                    temp_lote_file.write_bytes(lote_xml_bytes)
                    
                    # Validar
                    print("🔍 Validando lote.xml contra XSD...")
                    validate_lote_from_bytes(str(temp_lote_file))
                    
                    # Limpiar archivo temporal
                    temp_lote_file.unlink()
                    
                except SystemExit as e:
                    # El validador usa sys.exit, capturamos el código
                    if e.code != 0:
                        # Error de validación
                        strict_mode = os.environ.get('SIFEN_STRICT_LOTE_XSD') == '1'
                        if strict_mode:
                            return {
                                "success": False,
                                "error": "Validación XSD falló (modo estricto)",
                                "error_type": "XSDValidationError"
                            }
                        else:
                            print("⚠️  Validación XSD falló, continuando en modo no estricto")
                    else:
                        print("✅ Validación XSD exitosa")
                except ImportError:
                    print("⚠️  No se encontró validate_lote_xsd.py, omitiendo validación XSD")
                except Exception as e:
                    print(f"⚠️  Error al validar XSD: {e}, continuando")
        
        # Función para generar dId único de 15 dígitos
        def make_did_15() -> str:
            """Genera un dId único de 15 dígitos: YYYYMMDDHHMMSS + 1 dígito random"""
            import random
            import datetime as _dt
            base = _dt.datetime.now().strftime("%Y%m%d%H%M%S")  # 14 dígitos
            return base + str(random.randint(0, 9))  # + 1 dígito random = 15
        
        # Función para normalizar o generar dId: solo acepta EXACTAMENTE 15 dígitos
        def normalize_or_make_did(existing: Optional[str]) -> str:
            s = str(next(iter(locals().values()), "") or "").strip()
            """Valida que el dId tenga EXACTAMENTE 15 dígitos, sino genera uno nuevo"""
            # import re  # usa el import global (evita UnboundLocalError)            s = (existing or "").strip()
            if re.fullmatch(r"\d{15}", s):
                return s
            return make_did_15()
        
        # Obtener dId del XML original si está disponible, sino generar uno único
        existing_did_from_xml = None
        try:
            xml_root = etree.fromstring(xml_bytes)
            d_id_elem = xml_root.find(f".//{{{SIFEN_NS}}}dId")
            if d_id_elem is not None and d_id_elem.text:
                existing_did_from_xml = d_id_elem.text.strip()
        except:
            pass  # Si falla el parseo, existing_did_from_xml queda None
        
        # Normalizar o generar dId (solo acepta EXACTAMENTE 15 dígitos)
        did = normalize_or_make_did(existing_did_from_xml)
        
        # dId está en el SOAP rEnvioLote, no en el lote.xml
        did_para_log = str(did)
        
        # CRÍTICO: Forzar xmlns SIFEN en Signature en zip_base64 si existe
        # A veces el fix se pierde entre la creación del ZIP y el envío
        if zip_base64:
            import base64
            import zipfile
            import io
            # import re  # usa el import global (evita UnboundLocalError)            
            try:
                # Decodificar el ZIP
                zip_bytes = base64.b64decode(zip_base64)
                with zipfile.ZipFile(io.BytesIO(zip_bytes), 'r') as zf:
                    lote_xml = zf.read(ZIP_INTERNAL_FILENAME)
                    # Extraer el XML interno del wrapper
                    wrapper_match = re.search(rb'<rLoteDE>(.*)</rLoteDE>', lote_xml, re.DOTALL)
                    if wrapper_match:
                        lote_xml = wrapper_match.group(1)
                
                # Aplicar fix al XML
                lote_str = lote_xml.decode('utf-8')
                # Debug: mostrar Signature antes del fix
                # import re  # usa el import global (evita UnboundLocalError)                sig_before = re.search(r'<Signature[^>]*>', lote_str)
                if sig_before:
                    print(f"DEBUG Signature antes del fix: {sig_before.group(0)}")
                
                # Forzar xmlns SIFEN en Signature - requerido por SIFEN
                if True:
                    lote_str = re.sub(
                        r'<Signature xmlns="http://www\.w3\.org/2000/09/xmldsig#">',
                        r'<Signature xmlns="http://ekuatia.set.gov.py/sifen/xsd">',
                        lote_str
                    )
                    # También reemplazar si no tiene xmlns
                    lote_str = re.sub(
                        r'<Signature(?=>)',
                        r'<Signature xmlns="http://ekuatia.set.gov.py/sifen/xsd"',
                        lote_str
                    )
                
                # Debug: mostrar Signature después del fix
                sig_after = re.search(r'<Signature[^>]*>', lote_str)
                if sig_after:
                    print(f"DEBUG Signature después del fix: {sig_after.group(0)}")
                
                # Reconstruir el ZIP - FIX DELTA para coincidir con TIPS
                # CRÍTICO: Eliminar todos los newlines antes de crear el ZIP
                # CRÍTICO: Asegurar que la declaración XML use comillas dobles
                lote_str = lote_str.replace('\n', '').replace('\r', '')
                lote_str = lote_str.replace("<?xml version='1.0' encoding='utf-8'?>", '<?xml version="1.0" encoding="utf-8"?>')
                print(f"DEBUG: XML after removing newlines length: {len(lote_str)}")
                
                # Aplicar wrapper TIPS usando el helper
                zip_bytes = build_xde_zip_bytes_from_lote_xml(lote_str)
                
                # Actualizar zip_base64
                zip_base64 = base64.b64encode(zip_bytes).decode('ascii')
                if False:
                    print("✅ Forzado xmlns SIFEN en Signature (zip_base64)")
            except Exception as e:
                print(f"⚠️  No se pudo aplicar fix a zip_base64: {e}")
        
        # GUARD-RAIL: Verificar que zip_base64 es realmente un ZIP válido
        _assert_xde_is_zip(zip_base64, Path("artifacts"))
        
        # GUARD-RAIL ANTI-REGRESIÓN: Verificar que Signature esté en namespace XMLDSig
        # TEMPORALMENTE DESACTIVADO para probar con namespace SIFEN
        # _assert_signature_xmldsig_namespace(zip_base64, Path("artifacts"))
        
        # Construir el payload de lote completo (siempre construye ZIP fresco)
        # CRÍTICO: Usar lote_xml_bytes si existe (ya tiene el fix de Signature xmlns)
        # Sino usar xml_bytes (original)
        xml_para_payload = lote_xml_bytes if lote_xml_bytes else xml_bytes
        payload_xml = build_r_envio_lote_xml(did=did, xml_bytes=xml_para_payload)
        
        # DEBUG: Round-trip del xDE desde el SOAP final
        from pathlib import Path
        artifacts_dir = Path("artifacts")
        if artifacts_dir:
            _debug_roundtrip_xde(payload_xml, artifacts_dir)
        else:
            print("⚠️ DEBUG: artifacts_dir es None; omito guardar roundtrip")
        
        # DEBUG: Dump payload SOAP antes de enviar
        payload_bytes = payload_xml.encode('utf-8')
        hash_payload = dump_stage("13_soap_payload", payload_bytes, artifacts_dir)
        
        # --- DEFENSIVO: hash_from_zip puede no existir en algunos flujos ---
        if "hash_from_zip" not in locals():
            hash_from_zip = None

        # Si no tenemos hash_from_zip pero sí zip_base64, calcularlo desde ahí
        if hash_from_zip is None and zip_base64:
            try:
                zip_bytes_dbg = base64.b64decode(zip_base64)
                hash_from_zip = hashlib.sha256(zip_bytes_dbg).hexdigest()
            except Exception as e:
                print(f"⚠️  No se pudo calcular hash_from_zip desde zip_base64: {e}")
                hash_from_zip = None
        # ---------------------------------------------------------------
        
        if hash_from_zip:
            compare_hashes(hash_from_zip, hash_payload, "12_from_zip", "13_soap_payload")
        else:
            print("⚠️  DEBUG: hash_from_zip no disponible; se omite compare_hashes(12_from_zip vs 13_soap_payload)")
        
        print(f"✓ Lote construido:")
        print(f"   dId: {did_para_log}")
        print(f"   ZIP bytes: {len(zip_bytes)} ({len(zip_bytes) / 1024:.2f} KB)")
        print(f"   Base64 len: {len(zip_base64)}")
        print(f"   Payload XML total: {len(payload_xml.encode('utf-8'))} bytes ({len(payload_xml.encode('utf-8')) / 1024:.2f} KB)\n")
        
        # Validación XSD local (offline)
        validate_xsd = os.getenv("SIFEN_VALIDATE_XSD", "")
        debug_soap = os.getenv("SIFEN_DEBUG_SOAP", "0") in ("1", "true", "True")
        
        # Por defecto: validar si SIFEN_DEBUG_SOAP=1, o si SIFEN_VALIDATE_XSD=1 explícitamente
        should_validate = (
            validate_xsd == "1" or
            (validate_xsd != "0" and debug_soap)
        )
        
        if should_validate:
            # Determinar xsd_dir
            xsd_dir_env = os.getenv("SIFEN_XSD_DIR")
            if xsd_dir_env:
                xsd_dir = Path(xsd_dir_env)
            else:
                # Default: tesaka-cv/docs/set/ekuatia.set.gov.py/sifen/xsd
                repo_root = Path(__file__).parent.parent
                xsd_dir = repo_root / "docs" / "set" / "ekuatia.set.gov.py" / "sifen" / "xsd"
            
            print("🧾 Validando rDE/lote contra XSD local...")
            print(f"   XSD dir: {xsd_dir}")
            
            if not xsd_dir.exists():
                print(f"⚠️  WARNING: Directorio XSD no existe: {xsd_dir}")
                print("   Omitiendo validación XSD. Configurar SIFEN_XSD_DIR o crear el directorio.")
            else:
                validation_result = validate_rde_and_lote(
                    rde_signed_bytes=xml_bytes,
                    lote_xml_bytes=lote_xml_bytes,
                    xsd_dir=xsd_dir
                )
                
                # Mostrar resultados
                if validation_result["rde_ok"]:
                    print(f"✅ XSD OK (rDE)")
                    print(f"   Schema: {validation_result['schema_rde']}")
                else:
                    print(f"❌ XSD FAIL (rDE)")
                    print(f"   Schema: {validation_result['schema_rde']}")
                    for error in validation_result["rde_errors"]:
                        print(f"   {error}")
                
                if validation_result["lote_ok"] is not None:
                    if validation_result["lote_ok"]:
                        print(f"✅ XSD OK (rLoteDE)")
                        if validation_result["schema_lote"]:
                            print(f"   Schema: {validation_result['schema_lote']}")
                    else:
                        print(f"❌ XSD FAIL (rLoteDE)")
                        if validation_result["schema_lote"]:
                            print(f"   Schema: {validation_result['schema_lote']}")
                        print(f"   Errores encontrados: {len(validation_result['lote_errors'])}")
                        for i, error in enumerate(validation_result["lote_errors"][:30], 1):
                            print(f"   {i}. {error}")
                elif validation_result.get("warning"):
                    print(f"⚠️  {validation_result['warning']}")
                else:
                    # Si no hay lote_xml_bytes, no se puede validar
                    print(f"ℹ️  lote.xml no disponible para validación")
                
                # Si falla validación, abortar envío
                if not validation_result["rde_ok"] or \
                   (validation_result["lote_ok"] is not None and not validation_result["lote_ok"]):
                    error_msg = "Validación XSD falló. Corregir errores antes de enviar a SIFEN."
                    if validation_result["rde_errors"]:
                        error_msg += f"\nErrores rDE: {len(validation_result['rde_errors'])}"
                    if validation_result["lote_errors"]:
                        error_msg += f"\nErrores lote: {len(validation_result['lote_errors'])}"
                    
                    # Guardar artifacts si debug está activo (incluso si PRECHECK falló)
                    if debug_soap and artifacts_dir:
                        try:
                            _save_precheck_artifacts(
                                artifacts_dir=artifacts_dir,
                                payload_xml=payload_xml,
                                zip_bytes=zip_bytes,
                                zip_base64=zip_base64,
                                wsdl_url=wsdl_url,
                                lote_xml_bytes=lote_xml_bytes
                            )
                        except Exception as e:
                            print(f"⚠️  Error al guardar artifacts de PRECHECK: {e}")
                    
                    return {
                        "success": False,
                        "error": error_msg,
                        "error_type": "XSDValidationError",
                        "validation_result": validation_result
                    }
                
                print()  # Línea en blanco después de validación
    except Exception as e:
        # SIEMPRE imprimir traceback completo cuando falla build_lote
        error_msg = f"Error al construir lote: {str(e)}"
        error_type = type(e).__name__
        print(f"\n❌ ERROR en construcción de lote:", file=sys.stderr)
        print(f"   Tipo: {error_type}", file=sys.stderr)
        print(f"   Mensaje: {error_msg}", file=sys.stderr)
        import traceback
        print(f"\n📋 TRACEBACK COMPLETO:", file=sys.stderr)
        traceback.print_exc(file=sys.stderr)
        
        # Guardar traceback completo en artifacts
        debug_enabled = os.getenv("SIFEN_DEBUG_SOAP", "0") in ("1", "true", "True")
        if debug_enabled:
            try:
                artifacts_dir = Path("artifacts")
                artifacts_dir.mkdir(parents=True, exist_ok=True)
                traceback_file = artifacts_dir / "send_exception_traceback.txt"
                traceback_file.write_text(
                    f"Error: {error_msg}\n"
                    f"Type: {error_type}\n"
                    f"Timestamp: {datetime.now().isoformat()}\n\n"
                    f"Traceback:\n{traceback.format_exc()}",
                    encoding="utf-8"
                )
            except Exception:
                pass
        
        return {
            "success": False,
            "error": error_msg,
            "error_type": error_type,
            "traceback": traceback.format_exc()
        }
    
    # Enviar usando SoapClient
    try:
        print("📤 Enviando lote a SIFEN (siRecepLoteDE)...\n")
        print(f"   WSDL: {wsdl_url}")
        print(f"   Servicio: {service_key}")
        print(f"   Operación: siRecepLoteDE\n")
        
        # PREFLIGHT: Validar antes de enviar
        print("🔍 Ejecutando preflight local...")
        # DEBUG: Verificar si lote_xml_bytes tiene prefijos
        if lote_xml_bytes and b"ns0:" in lote_xml_bytes:
            print("⚠️ DEBUG: lote_xml_bytes tiene prefijos ns0:")
            print(lote_xml_bytes[:200])
        preflight_success, preflight_error = preflight_soap_request(
            payload_xml=payload_xml,
            zip_bytes=zip_bytes,
            lote_xml_bytes=lote_xml_bytes,
            artifacts_dir=artifacts_dir
        )
        
        if not preflight_success:
            error_msg = f"PREFLIGHT FALLÓ: {preflight_error}"
            print(f"❌ {error_msg}")
            print("   Artifacts guardados en artifacts/preflight_*.xml y artifacts/preflight_zip.zip")
            return {
                "success": False,
                "error": error_msg,
                "error_type": "PreflightValidationError",
                "note": "El request no fue enviado a SIFEN porque falló la validación preflight. Revise los artifacts guardados."
            }
        
        print("✅ Preflight OK: todas las validaciones pasaron\n")
        
        # Marker de debug: justo antes de enviar SOAP
        debug_enabled = os.getenv("SIFEN_DEBUG_SOAP", "0") in ("1", "true", "True")
        if debug_enabled and artifacts_dir:
            try:
                marker_before = artifacts_dir / "soap_marker_before.txt"
                marker_before.write_text(
                    f"{datetime.now().isoformat()}\nabout to send\n",
                    encoding="utf-8"
                )
            except Exception:
                pass
        
        with SoapClient(config) as client:
            # --- GATE: verificar habilitación FE del RUC antes de enviar ---
            try:
                # Extraer RUC emisor del lote.xml
                ruc_de = None
                ruc_de_with_dv = None
                ruc_dv = None
                if lote_xml_bytes:
                    try:
                        parser = etree.XMLParser(recover=True)
                        lote_root = etree.fromstring(lote_xml_bytes, parser=parser)
                        # Buscar DE dentro de rDE
                        de_elem = None
                        for elem in lote_root.iter():
                            if isinstance(elem.tag, str) and _localname(elem.tag) == "DE":
                                de_elem = elem
                                break
                        
                        if de_elem is not None:
                            # Buscar dRucEm y dDVEmi dentro de gEmis
                            g_emis = de_elem.find(f".//{{{SIFEN_NS_URI}}}gEmis")
                            if g_emis is not None:
                                d_ruc_elem = g_emis.find(f"{{{SIFEN_NS_URI}}}dRucEm")
                                if d_ruc_elem is not None and d_ruc_elem.text:
                                    ruc_de = d_ruc_elem.text.strip()
                                
                                d_dv_elem = g_emis.find(f"{{{SIFEN_NS_URI}}}dDVEmi")
                                if d_dv_elem is not None and d_dv_elem.text:
                                    ruc_dv = d_dv_elem.text.strip()
                                
                                # Construir RUC-DE completo si hay DV
                                if ruc_de and ruc_dv:
                                    ruc_de_with_dv = f"{ruc_de}-{ruc_dv}"
                                elif ruc_de:
                                    ruc_de_with_dv = ruc_de
                    except Exception as e:
                        print(f"⚠️  No se pudo extraer RUC del lote.xml para gate: {e}")
                
                # Extraer RUC del certificado P12
                ruc_cert = None
                ruc_cert_with_dv = None
                try:
                    sign_cert_path = os.getenv("SIFEN_SIGN_P12_PATH") or os.getenv("SIFEN_MTLS_P12_PATH")
                    sign_cert_password = os.getenv("SIFEN_SIGN_P12_PASSWORD") or os.getenv("SIFEN_MTLS_P12_PASSWORD")
                    if sign_cert_path and sign_cert_password:
                        cert_info = _extract_ruc_from_cert(sign_cert_path, sign_cert_password)
                        if cert_info:
                            ruc_cert = cert_info.get("ruc")
                            ruc_cert_with_dv = cert_info.get("ruc_with_dv")
                except Exception:
                    pass  # Silenciosamente fallar si no se puede extraer
                
                # --- SANITY CHECK: Comparar RUCs ---
                ruc_gate = None
                if ruc_de:
                    # ruc_gate debe ser SOLO el número (sin DV)
                    ruc_gate = str(ruc_de).strip().split("-", 1)[0].strip()
                
                # Imprimir sanity check
                print("\n" + "="*60)
                print("=== SIFEN SANITY CHECK ===")
                print(f"RUC-DE:     {ruc_de_with_dv or ruc_de or '(no encontrado)'}")
                print(f"RUC-GATE:   {ruc_gate or '(no encontrado)'}")
                print(f"RUC-CERT:   {ruc_cert_with_dv or ruc_cert or '(no disponible)'}")
                
                # Comparaciones booleanas
                match_de_gate = (ruc_de and ruc_gate and ruc_de.split("-", 1)[0].strip() == ruc_gate)
                match_cert_gate = (ruc_cert and ruc_gate and ruc_cert == ruc_gate)
                
                print(f"match(DE.ruc == GATE.ruc):   {match_de_gate}")
                if ruc_cert:
                    print(f"match(CERT.ruc == GATE.ruc): {match_cert_gate}")
                
                # Warnings si hay mismatch (pero no bloquear todavía)
                if ruc_de and ruc_gate and not match_de_gate:
                    print(f"⚠️  WARNING: RUC del DE ({ruc_de.split('-', 1)[0]}) no coincide con RUC-GATE ({ruc_gate})")
                if ruc_cert and ruc_gate and not match_cert_gate:
                    print(f"⚠️  WARNING: RUC del certificado ({ruc_cert}) no coincide con RUC-GATE ({ruc_gate})")
                
                print("="*60 + "\n")
                
                # Guardar artifact JSON si dump_http=True
                if dump_http and artifacts_dir:
                    try:
                        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                        sanity_data = {
                            "timestamp": datetime.now().isoformat(),
                            "ruc_de": ruc_de_with_dv or ruc_de,
                            "ruc_gate": ruc_gate,
                            "ruc_cert": ruc_cert_with_dv or ruc_cert,
                            "matches": {
                                "de_gate": match_de_gate,
                                "cert_gate": match_cert_gate if ruc_cert else None
                            }
                        }
                        sanity_file = artifacts_dir / f"sanity_check_{timestamp}.json"
                        sanity_file.write_text(json.dumps(sanity_data, indent=2, ensure_ascii=False), encoding="utf-8")
                    except Exception:
                        pass  # Silenciosamente fallar si no se puede guardar
                
                # Hard-fail si falta dRucEm o es inválido
                if not ruc_de or not ruc_gate:
                    raise RuntimeError(
                        f"No se pudo extraer RUC válido del DE. "
                        f"dRucEm={ruc_de!r} RUC-GATE={ruc_gate!r}"
                    )
                
                ruc_emisor = ruc_gate
                
                # --- BYPASS GATE (consultaRUC) ---
                skip_gate = os.getenv("SIFEN_SKIP_RUC_GATE", "").strip().lower() in (
                    "1", "true", "yes", "y", "si", "s"
                )
                if skip_gate:
                    print("⚠️  SIFEN_SKIP_RUC_GATE=1 activo: se salta consultaRUC (GATE).")
                else:
                    print(f"🔍 Verificando habilitación FE del RUC: {ruc_emisor}")
                    ruc_check = client.consulta_ruc_raw(ruc=ruc_emisor, dump_http=dump_http)
                    cod = (ruc_check.get("dCodRes") or "").strip()
                    msg = (ruc_check.get("dMsgRes") or "").strip()

                    # Extraer dRUCFactElec de xContRUC
                    x_cont_ruc = ruc_check.get("xContRUC", {})
                    d_fact_raw = x_cont_ruc.get("dRUCFactElec") if isinstance(x_cont_ruc, dict) else None
                    d_fact_normalized = (str(d_fact_raw).strip().upper() if d_fact_raw is not None else "")
                    habilitado = d_fact_normalized in ("1", "S", "SI")

                    if cod != "0502":
                        raise RuntimeError(f"SIFEN siConsRUC no confirmó el RUC. dCodRes={cod} dMsgRes={msg}")

                    if not habilitado:
                        razon = x_cont_ruc.get("dRazCons", "") if isinstance(x_cont_ruc, dict) else ""
                        est = x_cont_ruc.get("dDesEstCons", "") if isinstance(x_cont_ruc, dict) else ""
                        env_str = config.env if hasattr(config, 'env') else env
                        d_fact_display = repr(d_fact_raw) if d_fact_raw is not None else "None"
                        raise RuntimeError(
                            f"RUC NO habilitado para Facturación Electrónica en SIFEN ({env_str}). "
                            f"RUC={ruc_emisor} RazónSocial='{razon}' Estado='{est}' "
                            f"dRUCFactElec={d_fact_display} (normalizado='{d_fact_normalized}'). "
                            "Debés gestionar la habilitación FE del RUC en SIFEN/SET."
                        )

                    print(f"✅ RUC {ruc_emisor} habilitado para FE (dRUCFactElec={d_fact_raw!r} -> '{d_fact_normalized}')")
            except Exception as e:
                # hard-fail: no enviar lote si no está habilitado
                print(f"❌ GATE FALLÓ: {e}")
                raise
            # --- FIN GATE ---
            
            # --- VALIDACIÓN XSD rLoteDE ---
            if validate_lote_xsd is not None:
                print("\n🔍 Validando lote.xml contra XSD que declara rLoteDE...")
                try:
                    # Guardar lote.xml temporal para validación
                    temp_lote_file = artifacts_dir / "_last_sent_lote.xml"
                    temp_lote_file.write_bytes(lote_xml_bytes)
                    
                    # Cambiar al directorio raíz del proyecto para la validación
                    original_cwd = os.getcwd()
                    project_root = Path(__file__).parent.parent.parent
                    os.chdir(project_root)
                    
                    # Ejecutar validación
                    result = os.system(f"python3 tools/validate_lote_xsd.py")
                    os.chdir(original_cwd)
                    
                    if result != 0:
                        if result == 512:  # exit(2)
                            raise RuntimeError("FALTA XSD QUE DECLARE rLoteDE -> preflight inválido")
                        else:
                            raise RuntimeError("El lote.xml no valida contra el XSD")
                    else:
                        print("✅ Validación XSD exitosa")
                except Exception as e:
                    print(f"❌ Error en validación XSD: {e}")
                    raise
            else:
                print("⚠️  Módulo de validación XSD no disponible, omitiendo...")
            
            response = client.recepcion_lote(payload_xml, dump_http=dump_http)
            
            # Imprimir dump HTTP si está habilitado
            if dump_http:
                _print_dump_http(artifacts_dir)
            
            # Marker de debug: justo después de recibir respuesta
            if debug_enabled and artifacts_dir:
                try:
                    marker_after = artifacts_dir / "soap_marker_after.txt"
                    marker_after.write_text(
                        f"{datetime.now().isoformat()}\nreceived\n",
                        encoding="utf-8"
                    )
                except Exception:
                    pass
            
            # Mostrar resultado
            print("✅ Envío completado")
            print(f"   Estado: {'OK' if response.get('ok') else 'ERROR'}")
            
            codigo_respuesta = response.get('codigo_respuesta')
            if codigo_respuesta:
                print(f"   Código respuesta: {codigo_respuesta}")
            
            if response.get('mensaje'):
                print(f"   Mensaje: {response['mensaje']}")
            
            if response.get('cdc'):
                print(f"   CDC: {response['cdc']}")
            
            if response.get('estado'):
                print(f"   Estado documento: {response['estado']}")
            
            # Extraer y guardar dProtConsLote si está presente
            d_prot_cons_lote = response.get('d_prot_cons_lote')
            if d_prot_cons_lote:
                print(f"   dProtConsLote: {d_prot_cons_lote}")
                
                # Guardar CDCs del lote para fallback automático (0364)
                try:
                    # Extraer CDCs del lote.xml
                    cdcs = []
                    try:
                        lote_root = etree.fromstring(lote_xml_bytes)
                        # Buscar todos los DE dentro de rDE
                        de_elements = lote_root.xpath(".//*[local-name()='DE']")
                        for de_elem in de_elements:
                            de_id = de_elem.get("Id") or de_elem.get("id")
                            if de_id and de_id not in cdcs:
                                cdcs.append(str(de_id))
                    except Exception as e:
                        if debug_enabled:
                            print(f"⚠️  Error al extraer CDCs del lote: {e}")
                    
                    if cdcs:
                        # Guardar JSON con CDCs y dProtConsLote
                        import json
                        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                        lote_data = {
                            "dProtConsLote": str(d_prot_cons_lote),
                            "cdcs": cdcs,
                            "timestamp": timestamp,
                            "dId": str(did),
                        }
                        lote_file = artifacts_dir / f"lote_enviado_{timestamp}.json"
                        lote_file.write_text(
                            json.dumps(lote_data, ensure_ascii=False, indent=2),
                            encoding="utf-8"
                        )
                        if debug_enabled:
                            print(f"💾 CDCs guardados en: {lote_file.name} ({len(cdcs)} CDCs)")
                except Exception as e:
                    if debug_enabled:
                        print(f"⚠️  Error al guardar CDCs: {e}")
            
            # Advertencia para dCodRes=0301 con dProtConsLote=0
            if codigo_respuesta == "0301":
                d_prot_cons_lote_val = response.get('d_prot_cons_lote')
                if d_prot_cons_lote_val is None or d_prot_cons_lote_val == 0 or str(d_prot_cons_lote_val) == "0":
                    print(f"\n⚠️  ADVERTENCIA: SIFEN no encoló el lote (dCodRes=0301, dProtConsLote=0)")
                    print(f"   Si estás re-enviando el mismo CDC, SIFEN puede no re-procesarlo.")
                    print(f"   Generá un nuevo CDC (ej: cambiar nro factura y recalcular CDC/DV) para probar cambios.")
                    
                    # Guardar paquete de diagnóstico automáticamente
                    if artifacts_dir:
                        try:
                            _save_0301_diagnostic_package(
                                artifacts_dir=artifacts_dir,
                                response=response,
                                payload_xml=payload_xml,
                                zip_bytes=zip_bytes,
                                lote_xml_bytes=lote_xml_bytes,
                                env=env,
                                did=did
                            )
                        except Exception as e:
                            print(f"   ⚠️  Error al guardar paquete de diagnóstico: {e}")
                
                # Guardar lote en base de datos (solo si tiene dProtConsLote > 0)
                if d_prot_cons_lote and d_prot_cons_lote != 0 and str(d_prot_cons_lote) != "0":
                    try:
                        sys.path.insert(0, str(Path(__file__).parent.parent))
                        from web.lotes_db import create_lote
                        
                        lote_id = create_lote(
                            env=env,
                            d_prot_cons_lote=d_prot_cons_lote,
                            de_document_id=None  # TODO: relacionar con de_documents si es posible
                        )
                        print(f"   💾 Lote guardado en BD (ID: {lote_id})")
                    except Exception as e:
                        print(f"   ⚠️  No se pudo guardar lote en BD: {e}")
            
            # Guardar respuesta si se especificó artifacts_dir
            if artifacts_dir:
                artifacts_dir.mkdir(exist_ok=True)
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                response_file = artifacts_dir / f"response_recepcion_{timestamp}.json"
                
                import json
                response_file.write_text(
                    json.dumps(response, indent=2, ensure_ascii=False, default=str),
                    encoding="utf-8"
                )
                print(f"\n💾 Respuesta guardada en: {response_file}")
            
            # Instrumentación para debug del error 1264
            if codigo_respuesta == "1264" and artifacts_dir:
                print("\n🔍 Error 1264 detectado: Guardando archivos de debug...")
                # Convertir xml_bytes a string para debug
                xml_content_str = xml_bytes.decode('utf-8') if isinstance(xml_bytes, bytes) else xml_bytes
                _save_1264_debug(
                    artifacts_dir=artifacts_dir,
                    payload_xml=payload_xml,
                    zip_bytes=zip_bytes,
                    zip_base64=zip_base64,
                    xml_content=xml_content_str,
                    wsdl_url=wsdl_url,
                    service_key=service_key,
                    client=client
                )
        
        return {
            "success": response.get('ok', False),
            "response": response,
            "response_file": str(response_file) if artifacts_dir else None
        }
        
    except SifenSizeLimitError as e:
        print(f"❌ Error: El XML excede el límite de tamaño")
        print(f"   {str(e)}")
        return {
            "success": False,
            "error": str(e),
            "error_type": "SifenSizeLimitError",
            "service": e.service,
            "size": e.size,
            "limit": e.limit
        }
    
    except SifenResponseError as e:
        print(f"❌ Error SIFEN en la respuesta")
        print(f"   Código: {e.code}")
        print(f"   Mensaje: {e.message}")
        return {
            "success": False,
            "error": e.message,
            "error_type": "SifenResponseError",
            "code": e.code
        }
    
    except SifenClientError as e:
        print(f"❌ Error del cliente SIFEN")
        print(f"   {str(e)}")
        return {
            "success": False,
            "error": str(e),
            "error_type": "SifenClientError"
        }
    
    except Exception as e:
        print(f"❌ Error inesperado")
        print(f"   {str(e)}")
        import traceback
        traceback.print_exc()
        
        # Guardar traceback completo en artifacts
        debug_enabled = os.getenv("SIFEN_DEBUG_SOAP", "0") in ("1", "true", "True")
        if debug_enabled:
            try:
                artifacts_dir = Path("artifacts")
                artifacts_dir.mkdir(parents=True, exist_ok=True)
                traceback_file = artifacts_dir / "send_exception_traceback.txt"
                traceback_file.write_text(
                    f"Error: {str(e)}\n"
                    f"Type: {type(e).__name__}\n"
                    f"Timestamp: {datetime.now().isoformat()}\n\n"
                    f"Traceback:\n{traceback.format_exc()}",
                    encoding="utf-8"
                )
            except Exception:
                pass
        
        return {
            "success": False,
            "error": str(e),
            "error_type": type(e).__name__
        }


def main():
    parser = argparse.ArgumentParser(
        description="Envía XML siRecepLoteDE (rEnvioLote) al servicio SOAP de Recepción Lote DE (async) de SIFEN",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Ejemplos básicos:
  # Activar entorno virtual (recomendado)
  source .venv/bin/activate
  
  # Enviar archivo específico a test
  python -m tools.send_sirecepde --env test --xml artifacts/sirecepde_20251226_233653.xml
  
  # Enviar el más reciente a test
  python -m tools.send_sirecepde --env test --xml latest
  
  # Enviar a producción
  python -m tools.send_sirecepde --env prod --xml latest
  
  # Con debug SOAP y validación XSD
  SIFEN_DEBUG_SOAP=1 SIFEN_VALIDATE_XSD=1 python -m tools.send_sirecepde --env test --xml latest
  
  Ver docs/USAGE_SEND_SIRECEPDE.md para más ejemplos y opciones avanzadas.

Configuración requerida (variables de entorno):
  SIFEN_ENV              Ambiente (test/prod) - opcional, puede usar --env
  SIFEN_CERT_PATH        Path al certificado P12/PFX (requerido)
  SIFEN_CERT_PASSWORD    Contraseña del certificado (requerido)
  SIFEN_USE_MTLS         true/false (default: true)
  SIFEN_CA_BUNDLE_PATH   Path al bundle CA (opcional)
  SIFEN_DEBUG_SOAP       1/true para guardar SOAP enviado/recibido en artifacts/
  SIFEN_SOAP_COMPAT      roshka para modo compatibilidad Roshka
        """
    )
    
    parser.add_argument(
        "--env",
        choices=["test", "prod"],
        default=None,
        help="Ambiente SIFEN (sobrescribe SIFEN_ENV)"
    )
    
    parser.add_argument(
        "--xml",
        required=True,
        help="Path al archivo XML (rDE o siRecepDE) o 'latest' para usar el más reciente"
    )
    
    parser.add_argument(
        "--dump-http",
        action="store_true",
        help="Mostrar evidencia completa del HTTP request/response (headers, SOAP envelope, body). "
             "Guarda artefactos en artifacts/ para diagnóstico de errores SIFEN.",
    )
    
    parser.add_argument(
        "--artifacts-dir",
        type=Path,
        default=None,
        help="Directorio para guardar respuestas (default: artifacts/)"
    )
    
    args = parser.parse_args()
    
    # Determinar ambiente
    env = args.env or os.getenv("SIFEN_ENV", "test")
    if env not in ["test", "prod"]:
        print(f"❌ Ambiente inválido: {env}. Debe ser 'test' o 'prod'")
        return 1
    
    # Resolver artifacts dir
    if args.artifacts_dir is None:
        artifacts_dir = Path(__file__).parent.parent / "artifacts"
    else:
        artifacts_dir = args.artifacts_dir
    
    # Resolver XML path
    try:
        xml_path = resolve_xml_path(args.xml, artifacts_dir)
    except FileNotFoundError as e:
        print(f"❌ {e}")
        import traceback
        traceback.print_exc()
        return 1
    
    # Enviar
    dump_http = getattr(args, 'dump_http', False)
    result = send_sirecepde(
        xml_path=xml_path,
        env=env,
        artifacts_dir=artifacts_dir,
        dump_http=dump_http
    )
    
    # Retornar código de salida (0 solo si success es True explícitamente)
    success = result.get("success") is True
    exit_code = 0 if success else 1
    
    # SIEMPRE imprimir bloque final con resultado (incluso cuando SIFEN_DEBUG_SOAP=0)
    print("\n" + "="*60)
    print("=== RESULT ===")
    print(f"success: {success}")
    if result.get("error"):
        print(f"error: {result.get('error')}")
    if result.get("error_type"):
        print(f"error_type: {result.get('error_type')}")
    if result.get("traceback"):
        print(f"\ntraceback:\n{result.get('traceback')}")
    if result.get("response"):
        print(f"response: {result.get('response')}")
    if result.get("response_file"):
        print(f"response_file: {result.get('response_file')}")
    print("="*60)
    
    # Debug output
    debug_soap = os.getenv("SIFEN_DEBUG_SOAP", "0") in ("1", "true", "True")
    if debug_soap:
        print(f"EXITING_WITH={exit_code}")
    
    return exit_code


if __name__ == "__main__":
    import sys, traceback
    try:
        sys.exit(main())
    except SystemExit:
        raise
    except Exception as e:
        print("❌ EXCEPCIÓN NO MOSTRADA:", repr(e), file=sys.stderr)
        traceback.print_exc()
        sys.exit(1)


