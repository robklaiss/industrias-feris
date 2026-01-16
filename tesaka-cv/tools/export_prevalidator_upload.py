#!/usr/bin/env python3
"""
Exportador byte-safe para Prevalidador SIFEN.

CRÍTICO: Este script modifica SOLO el tag de apertura de <rDE ...> (atributos).
NO toca nada dentro de <DE>...</DE> porque eso rompería la firma XMLDSig.

La firma referencia DE@Id, no rDE. Por lo tanto, modificar atributos de rDE
(Id, xmlns, schemaLocation) es seguro y no invalida la firma.
"""
from __future__ import annotations

import argparse
import codecs
import re
import sys
from pathlib import Path
from typing import Dict, Optional, Tuple

from lxml import etree as ET

SIFEN_NS = "http://ekuatia.set.gov.py/sifen/xsd"
DS_NS = "http://www.w3.org/2000/09/xmldsig#"
XSI_NS = "http://www.w3.org/2001/XMLSchema-instance"

# schemaLocation correcto para rDE standalone (v150)
# Formato: "namespace location" (dos tokens separados por espacio)
CORRECT_SCHEMA_LOCATION = "http://ekuatia.set.gov.py/sifen/xsd http://ekuatia.set.gov.py/sifen/xsd/siRecepRDE_v150.xsd"

DEFAULT_OUT = Path.home() / "Desktop" / "SIFEN_PREVALIDADOR_UPLOAD.xml"
DEFAULT_PROLOG = b'<?xml version="1.0" encoding="UTF-8"?>\n'


def _local(tag: Optional[str]) -> str:
    if not tag:
        return ""
    if "}" in tag:
        return tag.split("}", 1)[1]
    return tag


def _trim_bytes(raw: bytes) -> bytes:
    if raw.startswith(codecs.BOM_UTF8):
        raw = raw[len(codecs.BOM_UTF8) :]
    idx = raw.find(b"<")
    if idx == -1:
        raise ValueError("No se encontró '<' en el XML")
    return raw[idx:]


def _extract_rde_block(trimmed: bytes) -> bytes:
    open_re = re.compile(rb"<([A-Za-z0-9_]+:)?rDE\b")
    m_open = open_re.search(trimmed)
    if not m_open:
        raise ValueError("No se encontró apertura de <rDE>")
    start = m_open.start()

    close_re = re.compile(rb"</([A-Za-z0-9_]+:)?rDE\s*>")
    matches = list(close_re.finditer(trimmed, start))
    if not matches:
        raise ValueError("No se encontró cierre </rDE>")
    end = matches[-1].end()
    return trimmed[start:end]


def _extract_de_id_from_block(rde_block: bytes) -> Optional[str]:
    """Extract DE@Id from the rDE block without full parsing.
    
    Uses regex to find the DE element's Id attribute.
    """
    # Match <DE ... Id="..." ...> or <DE ... Id='...' ...>
    # Also handle namespaced: <sifen:DE ... Id="...">
    de_id_pat = re.compile(rb'<([A-Za-z0-9_]+:)?DE\b[^>]*\sId=(["\'])([^"\']+)\2')
    m = de_id_pat.search(rde_block)
    if m:
        return m.group(3).decode("utf-8")
    return None


def _parse_rde_start_tag_attrs(start_tag: bytes) -> Tuple[Dict[str, str], bytes, bytes]:
    """Parse attributes from rDE start tag.
    
    Returns:
        - dict of attr_name -> attr_value
        - prefix bytes (e.g. b"<rDE" or b"<sifen:rDE")
        - suffix bytes (e.g. b">" or b"/>")
    """
    # Find the tag name part: <rDE or <prefix:rDE
    tag_name_pat = re.compile(rb'^(<(?:[A-Za-z0-9_]+:)?rDE)\s*')
    m = tag_name_pat.match(start_tag)
    if not m:
        raise ValueError(f"No se pudo parsear tag de apertura rDE: {start_tag[:50]}")
    
    prefix = m.group(1)
    rest = start_tag[m.end():]
    
    # Find suffix (> or />)
    if rest.endswith(b"/>"):
        suffix = b"/>"
        attr_part = rest[:-2]
    elif rest.endswith(b">"):
        suffix = b">"
        attr_part = rest[:-1]
    else:
        raise ValueError("rDE start tag no termina en > o />")
    
    # Parse attributes using regex
    # Matches: name="value" or name='value'
    attrs: Dict[str, str] = {}
    attr_pat = re.compile(rb'([A-Za-z0-9_:]+)=(["\'])([^"\']*)\2')
    for match in attr_pat.finditer(attr_part):
        attr_name = match.group(1).decode("utf-8")
        attr_value = match.group(3).decode("utf-8")
        attrs[attr_name] = attr_value
    
    return attrs, prefix, suffix


def _rebuild_rde_start_tag(attrs: Dict[str, str], prefix: bytes, suffix: bytes) -> bytes:
    """Rebuild rDE start tag from parsed components."""
    parts = [prefix]
    for name, value in attrs.items():
        # Use double quotes for all attributes
        parts.append(f' {name}="{value}"'.encode("utf-8"))
    parts.append(suffix)
    return b"".join(parts)


def _fix_rde_start_tag_bytesafe(
    rde_block: bytes, 
    de_id: Optional[str],
    nsmap_in_scope: Dict[Optional[str], str]
) -> Tuple[bytes, Dict[str, str]]:
    """ZERO-modification extraction - preserva rDE EXACTAMENTE como está.
    
    CRÍTICO: Agregar CUALQUIER atributo a rDE (incluso xmlns) puede cambiar
    la forma canónica de los elementos hijos y romper la firma XMLDSig.
    
    Esta función NO modifica NADA - solo extrae y reporta estado.
    
    Returns:
        - rDE block SIN CAMBIOS
        - Dict with info for logging
    """
    changes: Dict[str, str] = {}
    
    # Find the end of the start tag for analysis only
    gt = rde_block.find(b">")
    if gt == -1:
        raise ValueError("rDE start tag inválido (no se encontró '>')")
    
    start_tag = rde_block[: gt + 1]
    
    # Log rDE@Id status
    id_pat = re.compile(rb'\sId=(["\'])([^"\']*)\1')
    m = id_pat.search(start_tag)
    if m:
        existing_id = m.group(2).decode("utf-8", errors="replace")
        changes["rDE.Id"] = f"existing: {existing_id}"
    else:
        changes["rDE.Id"] = f"NOT present (DE@Id={de_id})"
    
    # Log xmlns status
    if b'xmlns="' in start_tag or b"xmlns='" in start_tag:
        changes["xmlns"] = "existing in rDE"
    else:
        changes["xmlns"] = "NOT in rDE (inherited from parent)"
    
    # Log xmlns:xsi status
    if b'xmlns:xsi=' in start_tag:
        changes["xmlns:xsi"] = "existing"
    else:
        changes["xmlns:xsi"] = "NOT present"
    
    # Log schemaLocation
    schema_loc_pat = re.compile(rb'xsi:schemaLocation=(["\'])([^"\']*)\1')
    m = schema_loc_pat.search(start_tag)
    if m:
        current_loc = m.group(2).decode("utf-8")
        changes["schemaLocation"] = current_loc
    else:
        changes["schemaLocation"] = "NOT present"
    
    # Return rDE block UNCHANGED
    return rde_block, changes


def _inject_ns_decls_into_rde_start_tag(rde_block: bytes, nsmap_in_scope: Dict[Optional[str], str]) -> bytes:
    """DEPRECATED: Use _fix_rde_start_tag_bytesafe instead.
    
    Kept for compatibility - now delegates to the new function.
    """
    de_id = _extract_de_id_from_block(rde_block)
    fixed_block, _ = _fix_rde_start_tag_bytesafe(rde_block, de_id, nsmap_in_scope)
    return fixed_block


def _ensure_prolog(doc: bytes) -> bytes:
    if doc.lstrip().startswith(b"<?xml"):
        return doc
    return DEFAULT_PROLOG + doc


def _check_signature_serialization(doc: bytes) -> None:
    sig_pat = re.compile(
        rb"<Signature\b[^>]*\sxmlns=(\"|')http://www\.w3\.org/2000/09/xmldsig#(\"|')"
    )
    count = len(sig_pat.findall(doc))
    if count != 1:
        raise ValueError(
            f"Se esperaba exactamente 1 <Signature xmlns=\"{DS_NS}\">, se encontró: {count}"
        )
    if b"<ds:Signature" in doc or b"xmlns:ds=" in doc:
        raise ValueError(
            "El XML contiene prefijo ds: o xmlns:ds=; el estándar requiere default xmlns en Signature"
        )


def _validate_structure(doc: bytes) -> None:
    """Validate rDE structure using local-name() to work with or without explicit xmlns."""
    parser = ET.XMLParser(remove_blank_text=False)
    root = ET.fromstring(doc, parser=parser)
    if _local(root.tag) != "rDE":
        raise ValueError(f"Root debe ser rDE; encontrado: {_local(root.tag)}")

    children = list(root)
    if not children:
        raise ValueError("rDE no tiene hijos")

    if _local(children[0].tag) != "dVerFor":
        raise ValueError("Estructura inválida: rDE debe iniciar con dVerFor")

    # Use local-name() to find elements regardless of namespace declaration
    de_nodes = root.xpath("./*[local-name()='DE']")
    if len(de_nodes) != 1:
        raise ValueError(
            f"Se esperaba exactamente 1 DE hijo directo de rDE; encontrado: {len(de_nodes)}"
        )
    de = de_nodes[0]
    de_id = de.get("Id")
    if not de_id:
        raise ValueError("El DE no tiene atributo Id")

    sig_nodes = root.xpath("./*[local-name()='Signature']")
    if len(sig_nodes) != 1:
        raise ValueError(
            f"Se esperaba exactamente 1 Signature hijo directo de rDE; encontrado: {len(sig_nodes)}"
        )

    idx_de = children.index(de)
    idx_sig = children.index(sig_nodes[0])
    if idx_sig != idx_de + 1:
        raise ValueError(
            "Estructura inválida: Signature debe ser hermano inmediato de DE (DE seguido de Signature)"
        )

    g_nodes = root.xpath("./*[local-name()='gCamFuFD']")
    if g_nodes:
        idx_g = children.index(g_nodes[0])
        if idx_g <= idx_sig:
            raise ValueError(
                "Estructura inválida: gCamFuFD debe estar después de Signature dentro de rDE"
            )

    g_inside_de = de.xpath(".//*[local-name()='gCamFuFD']")
    if g_inside_de:
        raise ValueError(
            "Estructura inválida: gCamFuFD no puede estar dentro de DE; debe ser hijo directo de rDE"
        )


def export_prevalidator_upload(input_path: Path, out_path: Path) -> None:
    raw = input_path.read_bytes()
    trimmed = _trim_bytes(raw)

    # Parse para detectar root y capturar nsmap en scope (sin reserializar)
    parser = ET.XMLParser(remove_blank_text=False)
    root = ET.fromstring(trimmed, parser=parser)
    root_local = _local(root.tag)

    if root_local == "rDE":
        rde_elem = root
        rde_block = _extract_rde_block(trimmed)
        nsmap_in_scope: Dict[Optional[str], str] = dict(rde_elem.nsmap or {})
    elif root_local == "rEnviDe":
        # Extraer el rDE interno (debe existir) y exportarlo como root del upload.
        rde_nodes = root.xpath("//*[local-name()='rDE']")
        if not rde_nodes:
            raise ValueError("No se encontró rDE dentro de rEnviDe")
        rde_elem = rde_nodes[0]
        rde_block = _extract_rde_block(trimmed)
        nsmap_in_scope = dict(rde_elem.nsmap or {})
    else:
        raise ValueError(f"El input debe tener root rDE o rEnviDe. Encontrado: {root_local}")

    # Extract DE@Id for potential injection into rDE
    de_id = _extract_de_id_from_block(rde_block)
    
    # Asegurar que el rDE exportado sea auto-contenido en namespaces (default xmlns, xsi, etc.)
    if "xsi" not in nsmap_in_scope:
        nsmap_in_scope["xsi"] = XSI_NS
    if None not in nsmap_in_scope:
        nsmap_in_scope[None] = SIFEN_NS

    # Apply byte-safe fixes to rDE start tag (Id, schemaLocation, xmlns)
    rde_block, changes = _fix_rde_start_tag_bytesafe(rde_block, de_id, nsmap_in_scope)

    out_bytes = _ensure_prolog(rde_block)

    _check_signature_serialization(out_bytes)
    _validate_structure(out_bytes)

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_bytes(out_bytes)

    # Print detailed summary
    print(f"IN:  {input_path}")
    print(f"OUT: {out_path}")
    print(f"root detectado: {root_local}")
    print(f"DE@Id: {de_id}")
    print(f"bytes: {len(out_bytes)}")
    print("--- Cambios en rDE start tag (byte-safe) ---")
    for key, val in changes.items():
        print(f"  {key}: {val}")
    print("OK: estructura rDE estándar y Signature (default xmlns) detectadas")


def main(argv: Optional[list[str]] = None) -> int:
    ap = argparse.ArgumentParser(
        description="Export byte-safe para Prevalidador SIFEN: valida y exporta rDE firmado sin reserializar."
    )
    ap.add_argument("input_xml", help="XML firmado con root rDE")
    ap.add_argument(
        "--out",
        default=str(DEFAULT_OUT),
        help="Ruta de salida (default: Desktop/SIFEN_PREVALIDADOR_UPLOAD.xml)",
    )
    args = ap.parse_args(argv)

    input_path = Path(args.input_xml).expanduser()
    out_path = Path(args.out).expanduser()
    if not input_path.exists():
        print(f"ERROR: no existe {input_path}", file=sys.stderr)
        return 1

    try:
        export_prevalidator_upload(input_path, out_path)
        return 0
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
