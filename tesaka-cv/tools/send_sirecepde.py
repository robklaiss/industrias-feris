#!/usr/bin/env python3


def _handle_0301_autofollow(*args, **kwargs):
    """Stub: evita NameError cuando dCodRes=0301. Implementación real puede hacer retry/backoff."""
    return None

def _save_0301_diagnostic_package(*args, **kwargs):
    """Stub: evita NameError si el empaquetado de diagnóstico no está implementado."""
    return None

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
# Import datetime con alias para evitar shadowing
import datetime as dt
from io import BytesIO
import base64
import zipfile
import json
import glob
from functools import lru_cache
from dataclasses import dataclass
import hashlib
import importlib.util

# Agregar el directorio padre al path para imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from dotenv import load_dotenv

from app.sifen_client.cdc_builder import build_cdc_from_de_xml
from app.sifen_client.lote_checker import check_lote_status
from app.sifen_client.xsd_validator import validate_rde_and_lote
from app.sifen_client.soap_client import SoapClient
from app.sifen_client.exceptions import SifenSizeLimitError, SifenClientError

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


@lru_cache(maxsize=1024)
def local_tag(tag: str) -> str:
    """
    Wrapper con cache para obtener el nombre local de un tag XML.
    Mantener compatibilidad con helpers legacy que usaban local_tag().
    """
    return _localname(tag)


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


def _resolve_envio_lote_root() -> str:
    """Obtiene el nombre del root para rEnvioLote según ENV (default: rEnvioLote)."""
    override = os.getenv("SIFEN_ENVIOLOTE_ROOT", "").strip()
    if override not in ("rEnvioLote", "rEnvioLoteDe"):
        return "rEnvioLote"
    return override


@dataclass
class LoteStructureResult:
    valid: bool
    mode: str
    root_localname: str
    root_namespace: Optional[str]
    direct_rde_count: int
    direct_rde_sifen_count: int
    xde_count: int
    xde_sifen_count: int
    nested_rde_total: int
    xde_wrapper_count: int
    first_rde: Optional[etree._Element] = None
    message: Optional[str] = None


def _analyze_lote_structure(lote_root: etree._Element) -> LoteStructureResult:
    """Inspecciona la estructura del rLoteDE y valida rDE/xDE según las reglas soportadas."""

    root_localname = local_tag(lote_root.tag)
    root_ns = _namespace_uri(lote_root.tag)

    direct_rde_children = [c for c in list(lote_root) if isinstance(c.tag, str) and local_tag(c.tag) == "rDE"]
    direct_rde_sifen = [c for c in direct_rde_children if _namespace_uri(c.tag) == SIFEN_NS]

    xde_children = [c for c in list(lote_root) if isinstance(c.tag, str) and local_tag(c.tag) == "xDE"]
    xde_children_sifen = [c for c in xde_children if _namespace_uri(c.tag) == SIFEN_NS]

    result = LoteStructureResult(
        valid=False,
        mode="invalid",
        root_localname=root_localname,
        root_namespace=root_ns,
        direct_rde_count=len(direct_rde_children),
        direct_rde_sifen_count=len(direct_rde_sifen),
        xde_count=len(xde_children),
        xde_sifen_count=len(xde_children_sifen),
        nested_rde_total=0,
        xde_wrapper_count=len(xde_children_sifen),
    )

    if root_localname != "rLoteDE":
        result.message = f"root localname debe ser 'rLoteDE', encontrado: {root_localname}"
        return result

    if root_ns != SIFEN_NS:
        result.message = f"rLoteDE debe tener namespace {SIFEN_NS}, encontrado: {root_ns or '(vacío)'}"
        return result

    if direct_rde_sifen:
        result.valid = True
        result.mode = "direct_rde"
        result.nested_rde_total = len(direct_rde_sifen)
        result.first_rde = direct_rde_sifen[0]
        return result

    if direct_rde_children and not direct_rde_sifen:
        result.message = "Los <rDE> directos encontrados no usan el namespace SIFEN requerido"
        return result

    if not xde_children:
        result.message = "lote.xml debe contener al menos un <rDE> (o <xDE> con 1 <rDE>)"
        return result

    if not xde_children_sifen:
        result.message = "Los elementos <xDE> deben estar en el namespace SIFEN"
        return result

    nested_total = 0
    for idx, xde_child in enumerate(xde_children_sifen, start=1):
        nested_rde = [c for c in list(xde_child) if isinstance(c.tag, str) and local_tag(c.tag) == "rDE"]
        if len(nested_rde) != 1:
            result.message = f"Cada <xDE> debe contener exactamente un <rDE> (xDE #{idx} tiene {len(nested_rde)})"
            return result
        if _namespace_uri(nested_rde[0].tag) != SIFEN_NS:
            result.message = f"El <rDE> dentro de <xDE> #{idx} debe usar el namespace SIFEN"
            return result
        nested_total += 1
        if result.first_rde is None:
            result.first_rde = nested_rde[0]

    if nested_total == 0:
        result.message = "lote.xml debe contener al menos un <rDE> (o <xDE> con 1 <rDE>)"
        return result

    result.valid = True
    result.mode = "xde_wrapped"
    result.nested_rde_total = nested_total
    return result


def _wrap_direct_rde_with_xde(lote_root: etree._Element) -> etree._Element:
    """Envuelve cada rDE directo en un xDE preservando el orden. Devuelve el árbol normalizado."""
    structure = _analyze_lote_structure(lote_root)
    if not structure.valid:
        message = structure.message or "lote.xml no es válido (no se pudo analizar estructura rDE/xDE)."
        raise RuntimeError(message)
    if structure.mode != "direct_rde":
        return lote_root

    for child in list(lote_root):
        if not (isinstance(child.tag, str) and local_tag(child.tag) == "rDE"):
            continue
        if _namespace_uri(child.tag) != SIFEN_NS:
            raise RuntimeError("rDE directo debe pertenecer al namespace SIFEN antes de normalizar xDE.")
        parent = child.getparent()
        if parent is None:
            raise RuntimeError("rDE directo no tiene parent al normalizar xDE (árbol inconsistente).")
        idx = parent.index(child)
        parent.remove(child)
        xde_wrapper = etree.Element(etree.QName(SIFEN_NS, "xDE"))
        xde_wrapper.append(child)
        parent.insert(idx, xde_wrapper)
    return lote_root


def _assert_r_envio_namespace(payload_xml: str) -> Dict[str, Optional[str]]:
    """Verifica que rEnvioLote, dId y xDE estén en el namespace SIFEN."""
    parser = etree.XMLParser(remove_blank_text=False)
    try:
        root = etree.fromstring(payload_xml.encode("utf-8"), parser=parser)
    except Exception as exc:
        raise RuntimeError(f"payload rEnvioLote no es XML válido: {exc}") from exc

    info = {
        "root_local": local_tag(root.tag),
        "root_ns": _namespace_uri(root.tag),
        "dId_ns": None,
        "xDE_ns": None,
    }

    d_id_elem = root.find(f".//{{{SIFEN_NS}}}dId")
    if d_id_elem is None:
        # Intentar encontrarlo sin namespace para proveer diagnóstico detallado
        raw = root.find(".//dId")
        raw_ns = _namespace_uri(raw.tag) if raw is not None else None
        raise RuntimeError(
            f"rEnvioLote no contiene <dId> en namespace SIFEN (encontrado ns={raw_ns or 'VACÍO'})"
        )
    info["dId_ns"] = _namespace_uri(d_id_elem.tag)

    xde_elem = root.find(f".//{{{SIFEN_NS}}}xDE")
    if xde_elem is None:
        raw = root.find(".//xDE")
        raw_ns = _namespace_uri(raw.tag) if raw is not None else None
        raise RuntimeError(
            f"rEnvioLote no contiene <xDE> en namespace SIFEN (encontrado ns={raw_ns or 'VACÍO'})"
        )
    info["xDE_ns"] = _namespace_uri(xde_elem.tag)

    if info["root_ns"] != SIFEN_NS:
        raise RuntimeError(
            f"Root rEnvioLote tiene namespace incorrecto: {info['root_ns'] or 'VACÍO'} (esperado {SIFEN_NS})"
        )
    if info["dId_ns"] != SIFEN_NS:
        raise RuntimeError(
            f"<dId> tiene namespace incorrecto: {info['dId_ns'] or 'VACÍO'} (esperado {SIFEN_NS})"
        )
    if info["xDE_ns"] != SIFEN_NS:
        raise RuntimeError(
            f"<xDE> tiene namespace incorrecto: {info['xDE_ns'] or 'VACÍO'} (esperado {SIFEN_NS})"
        )

    return info


def _extract_dnumdoc_from_file(xml_path: Path) -> Optional[str]:
    try:
        data = xml_path.read_bytes()
        parser = etree.XMLParser(remove_blank_text=False)
        root = etree.fromstring(data, parser=parser)
    except Exception:
        return None
    node = root.find(f".//{{{SIFEN_NS}}}dNumDoc")
    if node is None:
        node = root.find(".//dNumDoc")
    if node is None or not node.text:
        return None
    digits = "".join(ch for ch in node.text if ch.isdigit())
    if not digits:
        return None
    return digits[-7:]


def _increment_numdoc(base: str, offset: int) -> str:
    try:
        width = len(base)
        value = int(base) + offset
        return str(value).zfill(width)
    except Exception:
        return str(offset + 1).zfill(7)

def _inspect_zip_lote(zip_bytes: bytes, artifacts_dir: Optional[Path]) -> Dict[str, Any]:
    """
    Inspección no destructiva del ZIP/xDE final.
    Retorna dict con root, ns, counts y guarda inspect_last_zip.json.
    """
    import json as _json

    result: Dict[str, Any] = {
        "zip_namelist": [],
        "chosen_xml": None,
        "lote_root": None,
        "lote_ns": None,
        "lote_nsmap": None,
        "rde_count": None,
        "xde_count": None,
    }
    try:
        with zipfile.ZipFile(BytesIO(zip_bytes), "r") as zf:
            names = zf.namelist()
            result["zip_namelist"] = names
            xml_name = "lote.xml" if "lote.xml" in names else None
            if xml_name is None:
                xml_candidates = [n for n in names if n.lower().endswith(".xml")]
                if xml_candidates:
                    xml_name = xml_candidates[0]
            if xml_name is None:
                raise RuntimeError(f"ZIP no contiene archivos XML (namelist={names})")
            result["chosen_xml"] = xml_name
            lote_xml_bytes = zf.read(xml_name)
    except Exception as exc:
        result["error"] = f"No se pudo abrir ZIP: {exc}"
        return result

    try:
        parser = etree.XMLParser(remove_blank_text=False, recover=False)
        lote_root = etree.fromstring(lote_xml_bytes, parser=parser)
        result["lote_root"] = local_tag(lote_root.tag)
        result["lote_ns"] = _namespace_uri(lote_root.tag)
        result["lote_nsmap"] = lote_root.nsmap if hasattr(lote_root, "nsmap") else {}
        result["rde_count"] = len(lote_root.xpath(".//*[local-name()='rDE']"))
        result["xde_count"] = len(lote_root.xpath(".//*[local-name()='xDE']"))
    except Exception as exc:
        result["error"] = f"No se pudo parsear lote.xml: {exc}"

    target_dir = artifacts_dir or Path("artifacts")
    try:
        target_dir.mkdir(parents=True, exist_ok=True)
        target_path = target_dir / "inspect_last_zip.json"
        target_path.write_text(_json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")
    except Exception:
        pass

    return result


def _extract_de_info_from_lote(lote_xml_bytes: bytes) -> Dict[str, Any]:
    info: Dict[str, Any] = {
        "rde_ids": [],
        "rde_count": 0,
        "xde_count": 0,
        "ruc_emisor": None,
        "ruc_emisor_dv": None,
        "iti_de": None,
        "has_dCarQR": False,
    }
    try:
        parser = etree.XMLParser(remove_blank_text=False, recover=False)
        root = etree.fromstring(lote_xml_bytes, parser=parser)
        rde_elems = root.xpath(".//*[local-name()='rDE']")
        info["rde_count"] = len(rde_elems)
        info["xde_count"] = len(root.xpath(".//*[local-name()='xDE']"))

        for rde_el in rde_elems:
            de_el = None
            for elem in rde_el:
                if isinstance(elem.tag, str) and local_tag(elem.tag) == "DE":
                    de_el = elem
                    break
            if de_el is None:
                continue
            de_id = de_el.get("Id") or de_el.get("id")
            if de_id:
                info["rde_ids"].append(de_id)

            iti = de_el.find(f".//{{{SIFEN_NS}}}iTiDE")
            if iti is None:
                iti_candidates = de_el.xpath(".//*[local-name()='iTiDE']")
                if iti_candidates:
                    iti = iti_candidates[0]
            if iti is not None and iti.text:
                info["iti_de"] = iti.text.strip()

            dcarqr = de_el.find(f".//{{{SIFEN_NS}}}dCarQR")
            if dcarqr is None:
                dcarqr_candidates = de_el.xpath(".//*[local-name()='dCarQR']")
                if dcarqr_candidates:
                    dcarqr = dcarqr_candidates[0]
            if dcarqr is not None and dcarqr.text and dcarqr.text.strip():
                info["has_dCarQR"] = True

            gemis = de_el.find(f".//{{{SIFEN_NS}}}gEmis")
            if gemis is None:
                gemis_candidates = de_el.xpath(".//*[local-name()='gEmis']")
                gemis = gemis_candidates[0] if gemis_candidates else None
            if gemis is not None:
                ruc = gemis.find(f".//{{{SIFEN_NS}}}dRucEm") or gemis.find(".//dRucEm")
                dv = gemis.find(f".//{{{SIFEN_NS}}}dDVEmi") or gemis.find(".//dDVEmi")
                if ruc is not None and ruc.text:
                    info["ruc_emisor"] = ruc.text.strip()
                if dv is not None and dv.text:
                    info["ruc_emisor_dv"] = dv.text.strip()
    except Exception:
        pass
    return info


def _write_block_report(
    *,
    artifacts_dir: Optional[Path],
    lote_xml_bytes: bytes,
    zip_bytes: bytes,
    did: str,
    ruc_cert: Optional[str],
) -> None:
    """Guarda un reporte de bloqueo previo al envío."""
    info = _extract_de_info_from_lote(lote_xml_bytes)
    sha_zip = hashlib.sha256(zip_bytes).hexdigest()
    report = {
        "did": did,
        "zip_sha256": sha_zip,
        "zip_len": len(zip_bytes),
        "rde_count": info.get("rde_count"),
        "xde_count": info.get("xde_count"),
        "de_ids": info.get("rde_ids"),
        "ruc_de": info.get("ruc_emisor"),
        "ruc_de_dv": info.get("ruc_emisor_dv"),
        "ruc_cert": ruc_cert,
        "iTiDE": info.get("iti_de"),
        "has_dCarQR": info.get("has_dCarQR"),
        "timestamp": dt.datetime.now().isoformat(),
    }
    target_dir = artifacts_dir or Path("artifacts")
    try:
        target_dir.mkdir(parents=True, exist_ok=True)
        target = target_dir / f"block_report_{dt.datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        target.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
        print(
            "🛡️  Block Report:"
            f" RUC_DE={report['ruc_de'] or 'N/A'}"
            f" RUC_CERT={report['ruc_cert'] or 'N/A'}"
            f" iTiDE={report['iTiDE'] or 'N/A'}"
            f" rDE={report['rde_count']}"
            f" xDE={report['xde_count']}"
            f" SHA256={sha_zip}"
            f" dId={did}"
            f" dCarQR={'sí' if report['has_dCarQR'] else 'no'}"
        )
    except Exception as exc:
        print(f"⚠️  No se pudo escribir block report: {exc}")


def _scan_duplicate_history(cdc: str, artifacts_dir: Optional[Path]) -> list[str]:
    matches: list[str] = []
    if not cdc:
        return matches
    dirs = _candidate_artifact_dirs(artifacts_dir)
    for base in dirs:
        try:
            for json_path in base.glob("response_recepcion_*.json"):
                try:
                    txt = json_path.read_text(encoding="utf-8")
                    if cdc in txt:
                        matches.append(str(json_path))
                except Exception:
                    continue
            for xml_path in base.glob("soap_last_request*.xml"):
                try:
                    txt = xml_path.read_text(encoding="utf-8", errors="ignore")
                    if cdc in txt:
                        matches.append(str(xml_path))
                except Exception:
                    continue
        except Exception:
            continue
    return matches


class SifenResponseError(Exception):
    """Fallback local exception to evitar NameError si no está importada."""
    pass


def _print_dump_http(artifacts_dir: Optional[Path]) -> None:
    """
    Imprime paths útiles de dump HTTP sin lanzar excepciones si faltan archivos.
    """
    try:
        base_dir = Path(artifacts_dir) if artifacts_dir else Path("artifacts")
        base_dir.mkdir(parents=True, exist_ok=True)

        def _print_artifact(label: str, relative_name: str) -> None:
            file_path = base_dir / relative_name
            if file_path.exists():
                print(f"   {label}: {file_path}")
            else:
                print(f"   {label}: (no existe)")

        print("📄 HTTP dump artifacts:")
        _print_artifact("soap_last_request_SENT", "soap_last_request_SENT.xml")
        _print_artifact("soap_last_response_RECV", "soap_last_response_RECV.xml")

        diag_files = sorted(base_dir.glob("diagnostic_*soap_request_redacted*.xml"))
        if diag_files:
            for idx, diag in enumerate(diag_files, start=1):
                print(f"   diagnostic redacted #{idx}: {diag}")
        else:
            print("   diagnostic redacted: (no existe)")
    except Exception as e:
        print(f"⚠️  No se pudo imprimir dump-http: {e}")


def _load_wsdl_wrapper_guess(wsdl_path: Path) -> Optional[str]:
    """
    Lee artifacts/wsdl_wrapper_guess.json si existe o ejecuta guess_wsdl_wrapper inline.
    """
    guess_json = Path("artifacts/wsdl_wrapper_guess.json")
    if guess_json.exists():
        try:
            data = json.loads(guess_json.read_text(encoding="utf-8"))
            wrapper = data.get("wrapper_guess")
            if wrapper:
                return wrapper
        except Exception:
            pass

    # Intentar carga directa de tools.guess_wsdl_wrapper
    try:
        spec = importlib.util.spec_from_file_location(
            "guess_wsdl_wrapper", str(Path(__file__).parent / "guess_wsdl_wrapper.py")
        )
        if spec and spec.loader:
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)  # type: ignore
            if hasattr(module, "guess_wrapper_from_wsdl"):
                wsdl_file = wsdl_path if wsdl_path.exists() else Path("artifacts/recibe-lote.wsdl.xml")
                result = module.guess_wrapper_from_wsdl(wsdl_file)  # type: ignore
                return getattr(result, "wrapper", None)
    except Exception:
        return None
    return None


def _apply_auto_wrapper_guess(env: str, artifacts_dir: Optional[Path], auto_flag: bool) -> Optional[str]:
    """
    Si auto_flag está activo y no hay override explícito, usa guess del WSDL para ajustar SIFEN_ENVIOLOTE_ROOT.
    Solo aplica en env test o cuando se pidió explícitamente.
    """
    if not auto_flag:
        return None
    if os.getenv("SIFEN_ENVIOLOTE_ROOT"):
        return None
    if env != "test":
        # Solo aplicar auto en test para evitar sorpresas en prod
        return None

    wsdl_path = Path("artifacts/recibe-lote.wsdl.xml")
    wrapper = _load_wsdl_wrapper_guess(wsdl_path)
    chosen = wrapper if wrapper in ("rEnvioLote", "rEnvioLoteDe") else None
    if chosen:
        os.environ["SIFEN_ENVIOLOTE_ROOT"] = chosen
        try:
            target_dir = artifacts_dir or Path("artifacts")
            target_dir.mkdir(parents=True, exist_ok=True)
            (target_dir / "last_wrapper_choice.json").write_text(
                json.dumps(
                    {
                        "chosen": chosen,
                        "source": "auto-wsdl-guess",
                        "wsdl_path": str(wsdl_path),
                        "timestamp": dt.datetime.now().isoformat(),
                    },
                    indent=2,
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
        except Exception:
            pass
        print(f"⚙️  Wrapper elegido por WSDL guess: {chosen}")
    else:
        print("⚠️  No se pudo determinar wrapper por WSDL guess (usando defaults).")
    return chosen


def _print_envelope_shape(wrapper: str, artifacts_dir: Optional[Path]) -> None:
    """Imprime y guarda un Body de ejemplo con el wrapper elegido."""
    nsmap = {None: SIFEN_NS, "soap": "http://www.w3.org/2003/05/soap-envelope"}
    body_root = etree.Element(etree.QName("http://www.w3.org/2003/05/soap-envelope", "Body"), nsmap=nsmap)
    payload = etree.SubElement(body_root, etree.QName(SIFEN_NS, wrapper))
    etree.SubElement(payload, etree.QName(SIFEN_NS, "dId")).text = "123456789012345"
    etree.SubElement(payload, etree.QName(SIFEN_NS, "xDE")).text = "__BASE64_REDACTED__"
    preview = etree.tostring(body_root, pretty_print=True, encoding="unicode")
    print("\n=== SOAP Body preview ===")
    print(preview)
    try:
        target_dir = artifacts_dir or Path("artifacts")
        target_dir.mkdir(parents=True, exist_ok=True)
        (target_dir / "envelope_shape_preview.xml").write_text(preview, encoding="utf-8")
        print(f"💾 Guardado envelope_shape_preview.xml en {target_dir}")
    except Exception:
        pass


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
        nsmap={None: SIFEN_NS_URI, "ds": DSIG_NS_URI, "xsi": XSI_NS_URI},
    )

    # Copiar atributos (si existieran)
    for k, v in rde_el.attrib.items():
        new_rde.set(k, v)

    # Mover hijos
    for ch in list(rde_el):
        parent = ch.getparent()
        if parent is not None and parent is rde_el:
            rde_el.remove(ch)
            new_rde.append(ch)

    return new_rde


def _ensure_signature_on_rde(xml_bytes: bytes, artifacts_dir: Optional[Path], debug_enabled: bool) -> bytes:
    """
    Garantiza que <ds:Signature> sea hijo directo de <rDE> (orden: dVerFor, DE, Signature, gCamFuFD).
    Si la firma está dentro de <DE> (o en otro lugar), la reubica inmediatamente después de <DE>.
    También asegura que dVerFor esté presente como primer hijo.
    """
    try:
        parser = etree.XMLParser(remove_blank_text=False)
        root = etree.fromstring(xml_bytes, parser)
    except Exception as e:
        raise ValueError(f"Error al parsear XML firmado para reposicionar Signature: {e}")

    def _serialize(current_root: etree._Element) -> bytes:
        has_decl = xml_bytes.lstrip().startswith(b"<?xml")
        return etree.tostring(
            current_root,
            encoding="utf-8",
            xml_declaration=has_decl,
            pretty_print=False,
        )

    rde_elem = root if local_tag(root.tag) == "rDE" else None
    if rde_elem is None:
        results = root.xpath("//*[local-name()='rDE']")
        rde_elem = results[0] if results else None

    if rde_elem is None:
        return xml_bytes

    # Asegurar que dVerFor esté presente como primer hijo
    dverfor_elem = rde_elem.find(".//dVerFor")
    if dverfor_elem is None:
        dverfor_elem = rde_elem.find(f".//{{{SIFEN_NS}}}dVerFor")
    
    if dverfor_elem is None:
        # Insertar dVerFor como primer hijo
        dverfor_new = etree.SubElement(rde_elem, f"{{{SIFEN_NS}}}dVerFor")
        dverfor_new.text = "150"
        # Moverlo al principio
        rde_elem.insert(0, dverfor_new)
        if debug_enabled:
            print("🔧 dVerFor agregado como primer hijo en _ensure_signature_on_rde")

    sig_nodes: List[etree._Element] = []
    for elem in rde_elem.xpath(".//*[local-name()='Signature']"):
        if _namespace_uri(elem.tag) == DSIG_NS_URI:
            sig_nodes.append(elem)

    if not sig_nodes:
        return xml_bytes

    sig_elem = sig_nodes[0]
    # Eliminar firmas duplicadas adicionales
    for extra in sig_nodes[1:]:
        parent = extra.getparent()
        if parent is not None:
            parent.remove(extra)

    sig_parent = sig_elem.getparent()
    if sig_parent is not None and sig_parent is not rde_elem:
        if sig_elem in list(sig_parent):
            sig_parent.remove(sig_elem)
        else:
            actual_parent = sig_elem.getparent()
            if actual_parent is not None and sig_elem in list(actual_parent):
                actual_parent.remove(sig_elem)
    elif sig_parent is None:
        return xml_bytes  # no hay parent válido

    children = list(rde_elem)
    insert_index = len(children)
    for idx, child in enumerate(children):
        if local_tag(child.tag) == "DE":
            insert_index = idx + 1
            break

    rde_elem.insert(insert_index, sig_elem)

    result_bytes = _serialize(root)

    children_snapshot = [local_tag(child.tag) for child in list(rde_elem)]
    print(f"🔍 rDE children: [{', '.join(children_snapshot)}]")

    if artifacts_dir:
        try:
            artifacts_dir.mkdir(parents=True, exist_ok=True)
            artifacts_dir.joinpath("signed_after_sig_reloc.xml").write_bytes(result_bytes)
            if debug_enabled:
                print(f"💾 Guardado: {artifacts_dir / 'signed_after_sig_reloc.xml'}")
        except Exception:
            pass

    return result_bytes


@dataclass
class LotePayloadSelection:
    lote_bytes: bytes
    zip_bytes: bytes
    zip_base64: str
    source: str
    lote_path: Optional[Path]
    zip_path: Optional[Path]


def _candidate_artifact_dirs(preferred: Optional[Path]) -> list[Path]:
    """
    Retorna lista de directorios candidatos de artifacts (sin duplicados).
    """
    dirs: list[Path] = []
    if preferred:
        dirs.append(Path(preferred))
    dirs.append(Path("artifacts"))
    dirs.append(Path(__file__).parent.parent / "artifacts")

    unique: list[Path] = []
    seen: set[str] = set()
    for base in dirs:
        resolved = base if base.is_absolute() else (Path.cwd() / base)
        key = str(resolved.resolve())
        if key not in seen:
            seen.add(key)
            unique.append(resolved)
    return unique


def _find_artifact_file(filename: str, preferred_dir: Optional[Path]) -> Optional[Path]:
    """
    Busca filename en los directorios de artifacts conocidos.
    """
    for base in _candidate_artifact_dirs(preferred_dir):
        candidate = base / filename
        if candidate.exists():
            return candidate
    return None


def _zip_lote_xml_bytes(lote_xml_bytes: bytes) -> bytes:
    """Crea lote.zip en memoria a partir de lote.xml.

    Regla SIFEN (TEST/PROD): dentro del ZIP debe existir un único archivo 'lote.xml'
    cuyo root sea rLoteDE y contenga rDE como hijos directos.
    Si viene con wrapper xDE (rLoteDE/xDE/rDE), se hace unwrap antes de zipear.
    """
    from io import BytesIO
    import zipfile
    from lxml import etree

    NS = "http://ekuatia.set.gov.py/sifen/xsd"

    # Parse
    root = etree.fromstring(lote_xml_bytes)

    # Si el root es rLoteDE y trae xDE como hijo, mover los hijos de xDE al root y eliminar xDE.
    if root.tag == f"{{{NS}}}rLoteDE":
        xdes = root.findall(f"./{{{NS}}}xDE")
        if xdes:
            moved = 0
            for xde in xdes:
                for child in list(xde):
                    xde.remove(child)
                    root.insert(root.index(xde), child)
                    moved += 1
                root.remove(xde)

            # re-serializar
            lote_xml_bytes = etree.tostring(
                root, xml_declaration=True, encoding="UTF-8", pretty_print=False
            )

    out = BytesIO()
    with zipfile.ZipFile(out, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("lote.xml", lote_xml_bytes)
    return out.getvalue()

    out = BytesIO()
    with zipfile.ZipFile(out, 'w', compression=zipfile.ZIP_DEFLATED) as zf:
        zf.writestr('lote.xml', lote_xml_bytes)
    return out.getvalue()

def _extract_de_metadata(lote_xml_bytes: bytes) -> Dict[str, Optional[str]]:
    """Extrae campos básicos del DE dentro de lote.xml."""
    fields = {
        "de_id": None,
        "dNumTim": None,
        "dEst": None,
        "dPunExp": None,
        "dNumDoc": None,
        "dFeEmiDE": None,
        "dRucEm": None,
    }
    try:
        parser = etree.XMLParser(remove_blank_text=True)
        root = etree.fromstring(lote_xml_bytes, parser=parser)
        # Buscar primer rDE (soporta xDE wrapper)
        rde_elem = root.find(f".//{{{SIFEN_NS}}}rDE")
        if rde_elem is None:
            nodes = root.xpath(".//*[local-name()='rDE']")
            rde_elem = nodes[0] if nodes else None
        if rde_elem is None:
            return fields

        de_elem = rde_elem.find(f".//{{{SIFEN_NS}}}DE")
        if de_elem is None:
            nodes = rde_elem.xpath(".//*[local-name()='DE']")
            de_elem = nodes[0] if nodes else None
        if de_elem is None:
            return fields

        fields["de_id"] = de_elem.get("Id") or de_elem.get("id")

        def find_text(xpath_expr: str) -> Optional[str]:
            node = de_elem.find(xpath_expr)
            if node is not None and node.text:
                return node.text.strip()
            return None

        fields["dNumTim"] = find_text(f".//{{{SIFEN_NS}}}dNumTim")
        fields["dEst"] = find_text(f".//{{{SIFEN_NS}}}dEst")
        fields["dPunExp"] = find_text(f".//{{{SIFEN_NS}}}dPunExp")
        fields["dNumDoc"] = find_text(f".//{{{SIFEN_NS}}}dNumDoc")
        fields["dFeEmiDE"] = find_text(f".//{{{SIFEN_NS}}}dFeEmiDE")

        g_emis = de_elem.find(f".//{{{SIFEN_NS}}}gEmis")
        if g_emis is not None:
            d_ruc = g_emis.find(f"{{{SIFEN_NS}}}dRucEm")
            if d_ruc is not None and d_ruc.text:
                fields["dRucEm"] = d_ruc.text.strip()
    except Exception:
        pass
    return fields


def _select_lote_payload(
    lote_xml_bytes: Optional[bytes],
    zip_bytes: Optional[bytes],
    zip_base64: Optional[str],
    artifacts_dir: Optional[Path],
    lote_source: str
) -> LotePayloadSelection:
    """
    Determina qué lote usar para el envío. Si lote_source == 'last_lote',
    intenta cargar artifacts/last_lote.xml + last_xde.zip como fuente.
    """
    source = (lote_source or "last_lote").strip().lower()
    if source not in {"last_lote", "memory"}:
        source = "last_lote"

    last_lote_path = _find_artifact_file("last_lote.xml", artifacts_dir)
    last_zip_path = _find_artifact_file("last_xde.zip", artifacts_dir)

    if source == "last_lote" and last_lote_path:
        lote_bytes = last_lote_path.read_bytes()
        zip_bytes_final: Optional[bytes] = None
        if last_zip_path:
            zip_bytes_final = last_zip_path.read_bytes()
            try:
                with zipfile.ZipFile(BytesIO(zip_bytes_final), "r") as zf:
                    if "lote.xml" in zf.namelist():
                        extracted = zf.read("lote.xml")
                        if extracted != lote_bytes:
                            print("⚠️  WARNING: last_xde.zip no coincide con last_lote.xml, regenerando ZIP.")
                            zip_bytes_final = None
            except Exception:
                zip_bytes_final = None
        if zip_bytes_final is None:
            zip_bytes_final = _zip_lote_xml_bytes(lote_bytes)
        zip_b64 = base64.b64encode(zip_bytes_final).decode("ascii")
        print(f"📂 Usando lote desde {last_lote_path}")
        return LotePayloadSelection(
            lote_bytes=lote_bytes,
            zip_bytes=zip_bytes_final,
            zip_base64=zip_b64,
            source=f"file:{last_lote_path}",
            lote_path=last_lote_path,
            zip_path=last_zip_path,
        )

    if source == "last_lote":
        print("⚠️  WARNING: artifacts/last_lote.xml no encontrado. Usando lote en memoria.")

    # Fallback: usar bytes en memoria (tal como retornó el builder)
    if lote_xml_bytes is None or zip_bytes is None or zip_base64 is None:
        raise RuntimeError("No hay lote en memoria para enviar.")
    return LotePayloadSelection(
        lote_bytes=lote_xml_bytes,
        zip_bytes=zip_bytes,
        zip_base64=zip_base64,
        source="memory",
        lote_path=None,
        zip_path=None,
    )


def _compare_with_last_lote_or_fail(
    selection: LotePayloadSelection,
    artifacts_dir: Optional[Path]
) -> None:
    """
    Compara el DE.Id del lote a enviar contra artifacts/last_lote.xml si existe.
    Aborta con diagnóstico si difiere.
    """
    # Si no existe artifacts/last_lote.xml, nada que comparar
    last_lote_path = _find_artifact_file("last_lote.xml", artifacts_dir)
    if not last_lote_path or not last_lote_path.exists():
        return

    try:
        existing_bytes = last_lote_path.read_bytes()
        if existing_bytes == selection.lote_bytes:
            return

        current_meta = _extract_de_metadata(selection.lote_bytes)
        existing_meta = _extract_de_metadata(existing_bytes)

        if current_meta.get("de_id") and existing_meta.get("de_id") and current_meta["de_id"] != existing_meta["de_id"]:
            diag_dir = _candidate_artifact_dirs(artifacts_dir)[0]
            diag_dir.mkdir(parents=True, exist_ok=True)
            diag_path = diag_dir / "diag_mismatch_last_lote_vs_sent.txt"
            diag_path.write_text(
                "Mismatch entre lote a enviar y artifacts/last_lote.xml\n"
                f"Fuente envío: {selection.source}\n"
                f"DE.Id envío: {current_meta.get('de_id')}\n"
                f"DE.Id last_lote: {existing_meta.get('de_id')}\n"
                f"Lote path usado: {selection.lote_path or '(memoria)'}\n"
                f"last_lote path: {last_lote_path}\n",
                encoding="utf-8"
            )
            import os
            if os.getenv("SIFEN_SKIP_LAST_LOTE_MISMATCH") == "1":
                print("⚠️  WARNING: SKIP last_lote mismatch gate (ENV:SIFEN_SKIP_LAST_LOTE_MISMATCH=1)")
                return
            raise RuntimeError(
                "Lote a enviar no coincide con artifacts/last_lote.xml. "
                f"Ver detalles en {diag_path}"
            )
    except RuntimeError:
        raise
    except Exception as exc:
        print(f"⚠️  WARNING: No se pudo comparar con last_lote.xml: {exc}")


def normalize_rde_before_sign(xml_bytes: bytes) -> bytes:
    """
    Normaliza el XML rDE antes de firmar:
    - Cambia dDesPaisRec -> dDesPaisRe (si existe)
    - Mueve gCamFuFD fuera del DE para que sea hijo directo del rDE (después de Signature)
    """
    parser = etree.XMLParser(remove_blank_text=False)
    root = etree.fromstring(xml_bytes, parser)

    # Tomar rDE (raíz o anidado)
    rde = root if local_tag(root.tag) == "rDE" else next((e for e in root.iter() if local_tag(e.tag) == "rDE"), None)
    if rde is None:
        return xml_bytes

    # 1) dDesPaisRec -> dDesPaisRe (renombrar en todo el árbol)
    for dd_rec in rde.xpath(".//*[local-name()='dDesPaisRec']"):
        dd_rec.tag = etree.QName(SIFEN_NS_URI, "dDesPaisRe")

    # 2) asegurar gCamFuFD como hijo directo de rDE
    de_elem = next((child for child in rde if local_tag(child.tag) == "DE"), None)
    gcam_elem = None
    if de_elem is not None:
        for child in list(de_elem):
            if local_tag(child.tag) == "gCamFuFD":
                gcam_elem = child
                de_elem.remove(child)
                break
    if gcam_elem is None:
        # Tal vez ya estaba en rDE; usar el existente
        gcam_elem = next((child for child in rde if local_tag(child.tag) == "gCamFuFD"), None)

    if gcam_elem is not None:
        if gcam_elem.getparent() is not rde:
            parent = gcam_elem.getparent()
            if parent is not None and gcam_elem in list(parent):
                parent.remove(gcam_elem)
        if gcam_elem in list(rde):
            rde.remove(gcam_elem)

        # Insertar gCamFuFD después de Signature si existe, si no al final
        children = list(rde)
        insert_idx = len(children)
        for idx, child in enumerate(children):
            if local_tag(child.tag) == "Signature":
                insert_idx = idx + 1
        rde.insert(insert_idx, gcam_elem)

    # 3) Garantizar Signature como hijo directo de rDE (y orden correcto)
    rde_bytes = etree.tostring(root, encoding="utf-8", xml_declaration=True)
    normalized_bytes = _ensure_signature_on_rde(rde_bytes, None, False)
    return normalized_bytes


def normalize_despaisrec_tags(xml_bytes: bytes) -> bytes:
    """
    Reemplaza cualquier tag dDesPaisRec (con o sin namespace/prefijo) por dDesPaisRe.
    Se aplica al XML completo (no solo rDE) para evitar rechazos en XSD.
    """
    try:
        parser = etree.XMLParser(remove_blank_text=False)
        root = etree.fromstring(xml_bytes, parser)
    except Exception:
        return xml_bytes

    changed = False
    for elem in root.iter():
        if isinstance(elem.tag, str) and local_tag(elem.tag) == "dDesPaisRec":
            ns_uri = _namespace_uri(elem.tag) or SIFEN_NS_URI
            elem.tag = etree.QName(ns_uri, "dDesPaisRe")
            changed = True

    if not changed:
        return xml_bytes

    has_decl = xml_bytes.lstrip().startswith(b"<?xml")
    return etree.tostring(
        root,
        encoding="utf-8",
        xml_declaration=has_decl,
        pretty_print=False,
    )


def reorder_signature_before_gcamfufd(xml_bytes: bytes) -> bytes:
    """
    Reordena los hijos de <rDE> para que Signature venga antes de gCamFuFD.
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

    # Si Signature está después de gCamFuFD, moverlo antes
    # Remover Signature y reinsertarlo justo antes de gCamFuFD
    # Verificar que sig realmente es hijo de rde antes de remover
    if sig in list(rde):
        rde.remove(sig)
    else:
        sig_parent = sig.getparent()
        if sig_parent is None:
            raise RuntimeError("Signature no tiene parent (bug de árbol XML)")
        sig_parent.remove(sig)
    # Recalcular índice de gCamFuFD después de remover sig
    children_after = list(rde)
    gcam_idx_after = children_after.index(gcam)
    rde.insert(gcam_idx_after, sig)

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
    nsmap = {None: SIFEN_NS, "xsi": XSI_NS, "ds": DS_NS}
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
    - Si no tiene ds:Signature como hijo directo, lo firma
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
        
        # Firmar usando el XML completo que contiene el DE
        try:
            from app.sifen_client.xmlsec_signer import sign_de_with_p12
            signed_xml_bytes = sign_de_with_p12(xml_bytes, cert_path, cert_password)
            print("✓ DE firmado exitosamente")
        except Exception as e:
            error_msg = f"Error al firmar DE: {e}"
            print(f"❌ {error_msg}", file=sys.stderr)
            traceback.print_exc(file=sys.stderr)
            raise RuntimeError(error_msg)
        
        # Guardar XML firmado (debug)
        if debug_enabled and artifacts_dir:
            artifacts_dir.mkdir(exist_ok=True)
            (artifacts_dir / "xml_signed.xml").write_bytes(signed_xml_bytes)
            print(f"💾 Guardado: {artifacts_dir / 'xml_signed.xml'}")
        
        # Validar estructura del XML firmado
        signed_tree = etree.fromstring(signed_xml_bytes)
        signed_rde = signed_tree.xpath("//*[local-name()='rDE']")
        if not signed_rde:
            raise RuntimeError("No se encontró rDE en XML firmado")
        
        signed_rde = signed_rde[0]
        rde_children = [local_tag(c.tag) for c in list(signed_rde)]
        print(f"🔍 rDE children: {rde_children}")
        
        # Verificar que Signature sea hija de rDE (no de DE)
        sig_in_rde = signed_rde.xpath("./ds:Signature", namespaces={"ds": DSIG_NS_URI})
        if not sig_in_rde:
            sig_in_rde = [c for c in list(signed_rde) if local_tag(c.tag) == "Signature"]
        
        if sig_in_rde:
            print("✓ Signature es hija directa de rDE (estructura correcta)")
        else:
            print("⚠️ ADVERTENCIA: Signature no es hija directa de rDE")
        
        # Retornar XML firmado directamente
        return signed_xml_bytes
        
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
    import re
    
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
    if has_xsi_attr and not has_xsi_ns:
        nsmap["xsi"] = XSI_NS
    
    new_rde = etree.Element(f"{{{SIFEN_NS}}}rDE", nsmap=nsmap)
    
    # Copiar todos los atributos (excepto xmlns que ya está en nsmap)
    for key, value in rde.attrib.items():
        if not key.startswith('xmlns'):
            new_rde.set(key, value)
    
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


def build_lote_base64_from_single_xml(xml_bytes: bytes, return_debug: bool = False) -> Union[str, Tuple[str, bytes, bytes], Tuple[str, bytes, bytes, str]]:
    """
    DEPRECATED: Esta función asume que el XML ya está firmado.
    
    RECOMENDADO: Usar build_and_sign_lote_from_xml() que normaliza, firma y valida.
    
    Crea un ZIP con el rDE firmado envuelto en rLoteDE/xDE.
    
    El ZIP contiene un único archivo "lote.xml" con:
    - Root: <rLoteDE xmlns="http://ekuatia.set.gov.py/sifen/xsd">
    - Contenido: un <xDE> (namespace SIFEN) cuyo hijo directo es el <rDE> firmado.
    
    IMPORTANTE: 
    - NO incluye <dId> (pertenece al SOAP rEnvioLote).
    - Cada rDE queda envuelto dentro de un xDE para cumplir con el XSD de lote.
    - Selecciona SIEMPRE el rDE que tiene <ds:Signature> como hijo directo.
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
        RuntimeError: Si lote.xml contiene <dId> o si faltan xDE/rDE esperados
    """
    import copy
    # etree ya está importado arriba, no redefinir
    
    # Namespace de firma digital
    DSIG_NS = "http://www.w3.org/2000/09/xmldsig#"
    
    # Función para verificar si un rDE tiene Signature como hijo directo
    def is_signed_rde(el) -> bool:
        """Verifica si el rDE tiene <ds:Signature> como hijo directo."""
        return any(
            child.tag == f"{{{DSIG_NS}}}Signature"
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
                    "Se encontró rDE pero NO contiene <ds:Signature> como hijo directo. "
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
                    "Se encontró rDE pero NO contiene <ds:Signature> como hijo directo. "
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
    
    # IMPORTANTE: Insertar dVerFor como primer hijo de rDE (requerido por SIFEN)
    # Solo si no existe ya
    if b'<dVerFor>' not in rde_patched:
        # Buscar el cierre del tag de apertura del rDE y agregar dVerFor después
        rde_open_tag_end = rde_patched.find(b">")
        if rde_open_tag_end != -1:
            # Insertar dVerFor después del tag de apertura de rDE con namespace SIFEN
            # Usar el mismo namespace que el rDE (default namespace)
            dverfor_element = b'<dVerFor>150</dVerFor>'
            rde_before = rde_patched
            rde_patched = (
                rde_patched[:rde_open_tag_end + 1] + 
                dverfor_element + 
                rde_patched[rde_open_tag_end + 1:]
            )
            # Verificar que se insertó
            if dverfor_element in rde_patched:
                print(f"✅ DIAGNÓSTICO [build_lote_base64] dVerFor insertado como primer hijo de rDE")
            else:
                print(f"❌ ERROR [build_lote_base64] dVerFor NO fue insertado")
                print(f"   Buscando en: {rde_patched[:200]}...")
        else:
            print(f"❌ ERROR [build_lote_base64] No se encontró el tag de cierre de rDE")
    else:
        print(f"✅ DIAGNÓSTICO [build_lote_base64] dVerFor ya existe en rDE")
    
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
    
    # Construir lote.xml con estructura: <rLoteDE xmlns="..."><xDE><rDE>...</rDE></xDE></rLoteDE>
    # SIN dId (pertenece al SOAP rEnvioLote). Cada rDE queda envuelto por un xDE.
    # dId dinámico para usar en el SOAP (NO dentro de lote.xml)
    lote_did = str(int(time.time() * 1000))
    
    # Construir lote.xml: rLoteDE con namespace SIFEN, conteniendo rDE firmado
    lote_xml_bytes = (
        b'<?xml version="1.0" encoding="utf-8"?>'
        b'<rLoteDE xmlns="' + SIFEN_NS.encode("utf-8") + b'">'
        b'<xDE>' +
        rde_patched +
        b'</xDE>'
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
    
    # Hard-guard: verificar que rLoteDE tenga la estructura correcta: <rLoteDE xmlns="..."><xDE><rDE>...</rDE></xDE></rLoteDE>
    # PROHIBIDO: <dId> dentro de lote.xml (pertenece al SOAP, NO al lote.xml)
    rlote_tag_start = lote_xml_bytes.find(b"<rLoteDE")
    if rlote_tag_start >= 0:
        rlote_tag_end = lote_xml_bytes.find(b">", rlote_tag_start)
        if rlote_tag_end > rlote_tag_start:
            rlote_tag = lote_xml_bytes[rlote_tag_start:rlote_tag_end]
            # Verificar que tenga xmlns SIFEN
            if b'xmlns="' + SIFEN_NS.encode("utf-8") + b'"' not in rlote_tag:
                raise RuntimeError(f"BUG: rLoteDE no tiene xmlns SIFEN correcto. Tag: {rlote_tag}")
    
    # Verificar que NO tenga <dId> (pertenece al SOAP, NO al lote.xml)
    if b"<dId" in lote_xml_bytes or b"</dId>" in lote_xml_bytes:
        raise RuntimeError("BUG: lote.xml contiene <dId> (pertenece al SOAP, NO al lote.xml)")
    
    if b"<xDE" not in lote_xml_bytes:
        raise RuntimeError("BUG: lote.xml debe contener al menos un elemento <xDE>")
    
    # Verificar que tenga <rDE> (con o sin prefijo)
    if b"<rDE" not in lote_xml_bytes:
        raise RuntimeError("BUG: lote.xml no contiene <rDE>")
    
    # Verificar que sea well-formed y que la cantidad de xDE coincida con rDE
    try:
        lote_tree = etree.fromstring(lote_xml_bytes)
    except Exception as e:
        raise RuntimeError(f"BUG: lote.xml no es well-formed: {e}")
    
    # Contabilizar rDE y xDE
    rde_count = len(lote_tree.xpath(".//*[local-name()='rDE']"))
    xde_count = len(lote_tree.xpath(".//*[local-name()='xDE']"))
    if rde_count == 0:
        raise RuntimeError("BUG: lote.xml no contiene elementos <rDE>")
    if xde_count != rde_count:
        raise RuntimeError(
            f"BUG: lote.xml debe contener la misma cantidad de <xDE> y <rDE>. "
            f"xDE={xde_count}, rDE={rde_count}"
        )
    
    # Guardar para inspección (antes de crear ZIP)
    if debug_enabled:
        Path("/tmp/lote_xml_payload.xml").write_bytes(lote_xml_bytes)
    
    # ZIP con lote.xml
    try:
        mem = BytesIO()
        with zipfile.ZipFile(mem, mode="w", compression=zipfile.ZIP_DEFLATED) as zf:
            zf.writestr("lote.xml", lote_xml_bytes)
        zip_bytes = mem.getvalue()
        print(f"🔍 DIAGNÓSTICO [build_lote_base64] ZIP creado: {len(zip_bytes)} bytes")
        
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
                
                if "lote.xml" in zip_files:
                    lote_content = zf.read("lote.xml")
                    lote_root = etree.fromstring(lote_content)
                    
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
    
    IMPORTANTE: lote.xml (dentro del ZIP) NO debe contener <dId> (pertenece al SOAP rEnvioLote).
    IMPORTANTE: lote.xml SÍ debe contener <xDE> como hijo directo, con un <rDE> firmado dentro.
    
    Flujo:
    1. Verificar dependencias críticas (lxml/xmlsec)
    2. Parsear XML de entrada y extraer rDE/DE
    3. Construir árbol lote final: <rLoteDE>...<xDE><rDE>...</rDE></xDE>...</rLoteDE> (SIN dId)
    4. Remover cualquier Signature previa del rDE
    5. Firmar el DE dentro del contexto del lote final (no fuera y luego mover)
    6. Validar post-firma (algoritmos SHA256, URI correcto)
    7. Agregar rDE firmado dentro de un xDE hijo de rLoteDE
    8. Serializar lote completo UNA SOLA VEZ (pretty_print=False)
    9. Comprimir en ZIP y codificar en Base64
    10. Validar que el ZIP contiene xDE->rDE y NO contiene <dId>
    11. Sanity check: verificar que existe al menos 1 xDE y xDE count == rDE count
    12. Guardar artifacts/last_xde.zip siempre
    
    Esto garantiza que la firma se calcula en el MISMO namespace context que viajará dentro del lote.
    
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
    # 0. GUARD-RAIL: Verificar dependencias críticas ANTES de continuar
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
    import re
    
    debug_enabled = os.getenv("SIFEN_DEBUG_SOAP", "0") in ("1", "true", "True")
    
    # 1. Parsear XML de entrada
    try:
        parser = etree.XMLParser(remove_blank_text=False, recover=False)
        xml_root = etree.fromstring(xml_bytes, parser=parser)
    except Exception as e:
        raise ValueError(f"Error al parsear XML de entrada: {e}")
    
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
    
    # 3. Normalizar CDC/dDVId antes de cualquier firma para evitar 0301 por CDC repetido
    # Guardar ID original antes de normalizar
    de_candidates_before = rde_el.xpath(".//*[local-name()='DE']")
    if de_candidates_before:
        de_before = de_candidates_before[0]
        original_id = de_before.get("Id") or de_before.get("id")
    else:
        original_id = None
    
    try:
        normalize_cdc_in_rde(
            rde_el,
            log_prefix="🧾 CDC normalization (pre-firma)",
            log_if_unchanged=os.getenv("SIFEN_DEBUG_SOAP", "0") in ("1", "true", "True"),
        )
        
        # Verificar que el ID no haya cambiado después de normalizar
        if original_id:
            de_candidates_after = rde_el.xpath(".//*[local-name()='DE']")
            if de_candidates_after:
                de_after = de_candidates_after[0]
                new_id = de_after.get("Id") or de_after.get("id")
                if original_id != new_id:
                    print(f"\n⚠️  ALERTA: El ID del DE cambió durante normalización:")
                    print(f"   ID original: {original_id}")
                    print(f"   ID nuevo:    {new_id}")
                    print(f"   Esto puede causar error 0160 'XML Mal Formado'")
                    print(f"   Se usará el ID original para mantener consistencia\n")
                    # Restaurar el ID original
                    de_after.set("Id", original_id)
                    # También restaurar dDVId si cambió
                    ddvid_elem = de_after.find(".//{*}dDVId")
                    if ddvid_elem is not None:
                        # Calcular DV para el ID original
                        from app.sifen_client.xml_generator_v150 import calculate_digit_verifier
                        dv = calculate_digit_verifier(original_id[:-1])
                        ddvid_elem.text = str(dv)
                        
    except Exception as e:
        raise RuntimeError(f"No se pudo normalizar CDC antes de firmar: {e}") from e

    # 4. Construir lote.xml completo como árbol lxml ANTES de firmar
    # IMPORTANTE: lote.xml NO debe contener <dId> (pertenece al SOAP rEnvioLote).
    # IMPORTANTE: Cada rDE debe quedar encapsulado en un xDE hijo de rLoteDE.
    # Clonar rDE para no modificar el original
    rde_to_sign = copy.deepcopy(rde_el)
    
    # DEBUG: Verificar que dVerFor está presente en rDE_to_sign
    dver_for = rde_to_sign.find(".//dVerFor")
    if dver_for is not None:
        print(f"✅ DEBUG: dVerFor presente en rDE_to_sign antes de firmar: {dver_for.text}")
    else:
        print(f"❌ DEBUG: dVerFor NO encontrado en rDE_to_sign antes de firmar")
    
    # Construir lote.xml usando la función corregida con namespace SIFEN
    # El lote.xml debe contener xDE -> rDE (sin base64, preservando la firma)
    # IMPORTANTE: rLoteDE NO debe tener xsi:schemaLocation (causa 0160)
    # Solo rDE debe tenerlo. Comparado con lote exitoso del 20251230.
    lote_root = etree.Element(etree.QName(SIFEN_NS, "rLoteDE"), nsmap={None: SIFEN_NS})
    
    # NOTA: El rDE firmado se agregará dentro de un xDE DESPUÉS de firmar (línea ~2620)
    # Por ahora solo preparamos el lote_root vacío
    
    # 5. Remover cualquier Signature previa del rDE antes de firmar
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
    
    # Serializar el rDE temporal para firmar (con namespaces preservados)
    rde_to_sign_bytes = etree.tostring(
        rde_temp_root,
        encoding="utf-8",
        xml_declaration=True,
        pretty_print=False,
        with_tail=False
    )
    
    # 7. Firmar el rDE (sign_de_with_p12 espera rDE como root)
    from app.sifen_client.xmlsec_signer import sign_de_with_p12
    try:
        rde_signed_bytes = sign_de_with_p12(rde_to_sign_bytes, cert_path, cert_password)
        if not isinstance(rde_signed_bytes, (bytes, bytearray)) or not rde_signed_bytes:
            raise RuntimeError("sign_de_with_p12 devolvió None/vacío. Revisar XMLSecError/logs de firma.")
        
        # DEBUG: Verificar que dVerFor está presente después de firmar
        if b'<dVerFor>' in rde_signed_bytes:
            print(f"✅ DEBUG: dVerFor presente después de sign_de_with_p12")
        else:
            print(f"❌ DEBUG: dVerFor NO encontrado después de sign_de_with_p12")
            
        # Mover Signature dentro del DE si está fuera (como hermano del DE dentro del rDE)
        debug_enabled = os.getenv("SIFEN_DEBUG_SOAP", "0") in ("1", "true", "True")
        artifacts_dir = Path("artifacts")
        rde_signed_bytes = _ensure_signature_on_rde(rde_signed_bytes, artifacts_dir, debug_enabled)
        if not isinstance(rde_signed_bytes, (bytes, bytearray)) or not rde_signed_bytes:
            raise RuntimeError("_ensure_signature_on_rde devolvió None/vacío. Revisar artifacts de debug.")
            
        # DEBUG: Verificar que dVerFor está presente después de _ensure_signature_on_rde
        if b'<dVerFor>' in rde_signed_bytes:
            print(f"✅ DEBUG: dVerFor presente después de _ensure_signature_on_rde")
        else:
            print(f"❌ DEBUG: dVerFor NO encontrado después de _ensure_signature_on_rde")
            # Si no está, agregarlo aquí como último recurso
            print(f"🔧 AGREGANDO dVerFor como último recurso...")
            rde_signed_bytes = rde_signed_bytes.replace(b'<rDE', b'<rDE><dVerFor>150</dVerFor>')
    except Exception as e:
        # Si no se puede firmar, NO continuar - guardar artifacts y fallar
        error_msg = f"No se pudo firmar con xmlsec: {e}"
        artifacts_dir = Path("artifacts")
        artifacts_dir.mkdir(parents=True, exist_ok=True)
        try:
            # Guardar el XML PRE-firma del rde_el actual (ya pasado por ensure_rde_sifen)
            artifacts_dir.joinpath("sign_error_input.xml").write_bytes(rde_to_sign_bytes)
            # Guardar detalles con información de debug del root
            root_tag = rde_temp_root.tag if hasattr(rde_temp_root, 'tag') else str(rde_temp_root)
            root_nsmap = rde_temp_root.nsmap if hasattr(rde_temp_root, 'nsmap') else {}
            artifacts_dir.joinpath("sign_error_details.txt").write_text(
                f"Error al firmar:\n{error_msg}\n\n"
                f"Debug info:\n"
                f"  root.tag: {root_tag}\n"
                f"  root.nsmap: {root_nsmap}\n\n"
                f"Traceback:\n{type(e).__name__}: {str(e)}",
                encoding="utf-8"
            )
        except Exception:
            pass
        raise RuntimeError(error_msg) from e
    
    # 8. Verificación crítica: ID del DE vs Reference URI
    try:
        rde_signed_root = etree.fromstring(rde_signed_bytes)
        de_elem = rde_signed_root.xpath(".//*[local-name()='DE']")[0]
        de_id = de_elem.get("Id") or de_elem.get("id")
        
        # Buscar Signature y Reference URI
        signature_elem = rde_signed_root.xpath(".//*[local-name()='Signature']")
        if signature_elem:
            reference_elem = signature_elem[0].xpath(".//*[local-name()='Reference']")
            if reference_elem:
                reference_uri = reference_elem[0].get("URI", "")
                if reference_uri.startswith("#"):
                    reference_uri = reference_uri[1:]
                
                if de_id != reference_uri:
                    error_msg = f"INCONSISTENCIA CRÍTICA: ID del DE ({de_id}) != Reference URI ({reference_uri})"
                    print(f"\n❌ {error_msg}")
                    print("   Esto causará error 0160 'XML Mal Formado' en SIFEN")
                    print("   El XML fue abortado antes de enviar\n")
                    
                    # Guardar artifacts para diagnóstico
                    artifacts_dir = Path("artifacts")
                    artifacts_dir.mkdir(parents=True, exist_ok=True)
                    try:
                        artifacts_dir.joinpath("diag_id_mismatch_input.xml").write_bytes(rde_signed_bytes)
                        artifacts_dir.joinpath("diag_id_mismatch.txt").write_text(
                            f"{error_msg}\n\n"
                            f"DE@Id: {de_id}\n"
                            f"Reference@URI: #{reference_uri}\n\n"
                            f"El XML fue abortado para evitar envío con error 0160",
                            encoding="utf-8"
                        )
                    except Exception:
                        pass
                    
                    raise RuntimeError(error_msg)
                else:
                    print(f"✅ Verificación ID/URI: DE@Id={de_id} == Reference@URI=#{reference_uri}")
                    
                    # Guardar check exitoso
                    if artifacts_dir:
                        try:
                            artifacts_dir.joinpath("id_check.txt").write_text(
                                f"OK\nDE@Id: {de_id}\nReference@URI: #{reference_uri}",
                                encoding="utf-8"
                            )
                        except Exception:
                            pass
    except Exception as e:
        if "INCONSISTENCIA CRÍTICA" in str(e):
            raise
        print(f"⚠️  No se pudo verificar consistencia ID/URI: {e}")
    
    # 8. Validación post-firma (antes de continuar al ZIP)
    try:
        parser_strict = etree.XMLParser(remove_blank_text=False, recover=False)
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
        
        # Buscar Signature como hijo directo de rDE (namespace-aware)
        DS_NS_URI = "http://www.w3.org/2000/09/xmldsig#"
        sig_elem = None
        for child in list(rde_signed_root):
            if local_tag(child.tag) == "Signature" and _namespace_uri(child.tag) == DS_NS_URI:
                sig_elem = child
                break

        if sig_elem is None:
            # Fallback: buscar en profundidad para diagnóstico
            for elem in rde_signed_root.iter():
                if local_tag(elem.tag) == "Signature" and _namespace_uri(elem.tag) == DS_NS_URI:
                    sig_elem = elem
                    break

        if sig_elem is None:
            raise RuntimeError("Post-firma: No se encontró <ds:Signature> como hijo directo de <rDE>")
        
        # Validar SignatureMethod
        sig_method_elem = None
        for elem in sig_elem.iter():
            if local_tag(elem.tag) == "SignatureMethod":
                sig_method_elem = elem
                break
        
        if sig_method_elem is None:
            raise RuntimeError("Post-firma: No se encontró <SignatureMethod> en la firma")
        
        sig_method_alg = sig_method_elem.get("Algorithm", "")
        expected_sig_method = "http://www.w3.org/2001/04/xmldsig-more#rsa-sha256"
        if sig_method_alg != expected_sig_method:
            raise RuntimeError(
                f"Post-firma: SignatureMethod debe ser '{expected_sig_method}', "
                f"encontrado: '{sig_method_alg}'"
            )
        
        # Validar DigestMethod
        digest_method_elem = None
        for elem in sig_elem.iter():
            if local_tag(elem.tag) == "DigestMethod":
                digest_method_elem = elem
                break
        
        if digest_method_elem is None:
            raise RuntimeError("Post-firma: No se encontró <DigestMethod> en la firma")
        
        digest_method_alg = digest_method_elem.get("Algorithm", "")
        expected_digest_method = "http://www.w3.org/2001/04/xmlenc#sha256"
        if digest_method_alg != expected_digest_method:
            raise RuntimeError(
                f"Post-firma: DigestMethod debe ser '{expected_digest_method}', "
                f"encontrado: '{digest_method_alg}'"
            )
        
        # Validar Reference URI
        ref_elem = None
        for elem in sig_elem.iter():
            if local_tag(elem.tag) == "Reference":
                ref_elem = elem
                break
        
        if ref_elem is None:
            raise RuntimeError("Post-firma: No se encontró <Reference> en la firma")
        
        ref_uri = ref_elem.get("URI", "")
        expected_uri = f"#{de_id}"
        if ref_uri != expected_uri:
            raise RuntimeError(
                f"Post-firma: Reference URI debe ser '{expected_uri}', encontrado: '{ref_uri}'"
            )
        
        # Validar X509Certificate
        x509_cert_elem = None
        for elem in sig_elem.iter():
            if local_tag(elem.tag) == "X509Certificate":
                x509_cert_elem = elem
                break
        
        if x509_cert_elem is None:
            raise RuntimeError("Post-firma: No se encontró <X509Certificate> en la firma")
        
        if not x509_cert_elem.text or not x509_cert_elem.text.strip():
            raise RuntimeError("Post-firma: <X509Certificate> está vacío (firma dummy o certificado no cargado)")
        
        # Validar SignatureValue
        sig_value_elem = None
        for elem in sig_elem.iter():
            if local_tag(elem.tag) == "SignatureValue":
                sig_value_elem = elem
                break
        
        if sig_value_elem is None:
            raise RuntimeError("Post-firma: No se encontró <SignatureValue> en la firma")
        
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
    
    # 10. Construir lote.xml con xDE -> rDE
    # Cada rDE dentro del lote debe estar envuelto por un xDE (con namespace SIFEN)
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
    
    # IMPORTANTE: Limpiar rDE antes de agregarlo al lote
    # El lote debe tener rDE con: dVerFor, DE, Signature, gCamFuFD
    # dVerFor NO debe estar en rDE (causa 0160)
    # gCamFuFD debe ser hijo directo de rDE (NO dentro del DE)
    de_elem = None
    gcam_elem = None
    for child in list(rde_signed):
        child_local = local_tag(child.tag)
        if child_local == "dVerFor":
            rde_signed.remove(child)
        elif child_local == "DE":
            de_elem = child
        # gCamFuFD se mantiene como hijo directo de rDE (no se mueve dentro de DE)
    
    # NO mover gCamFuFD dentro del DE - mantener como hijo directo de rDE
    
    # Agregar el rDE firmado DIRECTAMENTE al lote (SIN xDE wrapper)
    # SIFEN ProtProcesLoteDE_v150: <rLoteDE><rDE>...</rDE></rLoteDE>
    lote_root.append(rde_signed)
    
    # El lote ahora tiene rDE firmado directamente dentro de rLoteDE
    lote_final = lote_root
    
    # 10. Serializar lote final UNA SOLA VEZ (pretty_print=False para no invalidar firma)
    lote_xml_bytes = etree.tostring(
        lote_final,
        encoding="utf-8",
        xml_declaration=True,
        pretty_print=False,
        with_tail=False
    )
    
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
            if xde_count == rde_count and rde_count >= 1:
                print(f"   ✅ OK: lote.xml contiene xDE -> rDE (conteo 1:1).")
            else:
                print(f"   ⚠️  WARNING: Conteo xDE/rDE inconsistente (xDE={xde_count}, rDE={rde_count})")
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
    # IMPORTANTE: lote.xml NO debe contener <dId> (pertenece al SOAP rEnvioLote)
    # IMPORTANTE: lote.xml debe contener rDE directamente (sin xDE wrapper)
    # Estructura correcta: <rLoteDE><rDE>...</rDE></rLoteDE>
    if b"<dId" in lote_xml_bytes or b"</dId>" in lote_xml_bytes:
        raise RuntimeError("BUG: lote.xml NO debe contener <dId>...</dId> (pertenece al SOAP rEnvioLote)")
    if b'<rLoteDE' not in lote_xml_bytes:
        raise RuntimeError("BUG: lote.xml no contiene <rLoteDE>")
    if b"<rDE" not in lote_xml_bytes or b"</rDE>" not in lote_xml_bytes:
        raise RuntimeError("BUG: lote.xml debe contener al menos un <rDE>")
    
    # Verificar que sea well-formed y que rDE esté presente
    try:
        lote_tree_guard = etree.fromstring(lote_xml_bytes)
    except Exception as e:
        raise RuntimeError(f"BUG: lote.xml no es well-formed: {e}")
    
    # rDE debe estar como hijo directo de rLoteDE (sin xDE wrapper)
    rde_children_guard = lote_tree_guard.xpath("./*[local-name()='rDE']")
    if not rde_children_guard:
        raise RuntimeError("BUG: rLoteDE debe contener rDE como hijos directos")
    
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
    
    # 14. Comprimir en ZIP
    try:
        mem = BytesIO()
        with zipfile.ZipFile(mem, mode="w", compression=zipfile.ZIP_DEFLATED) as zf:
            zf.writestr("lote.xml", lote_xml_bytes)
        zip_bytes = mem.getvalue()
    except Exception as e:
        raise RuntimeError(f"Error al crear ZIP: {e}")
    
    # 15. Validar el ZIP después de crearlo: verificar estructura completa
    try:
        with zipfile.ZipFile(BytesIO(zip_bytes), "r") as zf:
            namelist = zf.namelist()
            if "lote.xml" not in namelist:
                raise RuntimeError("ZIP no contiene 'lote.xml'")
            
            # Validar que contiene SOLO lote.xml
            if len(namelist) != 1:
                raise RuntimeError(f"ZIP debe contener solo 'lote.xml', encontrado: {namelist}")
            
            lote_xml_from_zip = zf.read("lote.xml")
            
            # Parsear para validar estructura (SIN recover)
            parser_strict = etree.XMLParser(remove_blank_text=False, recover=False)
            lote_root_from_zip = etree.fromstring(lote_xml_from_zip, parser=parser_strict)
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
            
            # Validar que tiene al menos 1 rDE hijo directo (sin xDE wrapper)
            # Estructura correcta: <rLoteDE><rDE>...</rDE></rLoteDE>
            rde_children = [c for c in lote_root_from_zip if local_tag(c.tag) == "rDE"]
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
            
            # Validar firma como hijo directo de rDE
            DS_NS_URI = "http://www.w3.org/2000/09/xmldsig#"
            sig_elem = None
            for child in list(rde_elem):
                if local_tag(child.tag) == "Signature" and _namespace_uri(child.tag) == DS_NS_URI:
                    sig_elem = child
                    break
            
            if sig_elem is None:
                raise RuntimeError("VALIDACIÓN FALLIDA: No se encontró <ds:Signature> como hijo directo de <rDE>")
            
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
                print(f"   - xDE hijos directos: {len(xde_children)} (>=1)")
                print(f"   - rDE encontrados dentro de xDE: {len(rde_children)}")
                print(f"   - xDE/rDE matching: {'✅' if len(xde_children) == len(rde_children) else '❌'}")
                print(f"   - NO contiene <dId>: ✅")
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
    
    # 16. Sanity check: verificar que el lote contiene xDE -> rDE antes de enviar
    try:
        lote_root_check = etree.fromstring(lote_xml_bytes, parser=parser)
        structure = _analyze_lote_structure(lote_root_check)
        if not structure.valid:
            raise RuntimeError(
                structure.message
                or "Lote inválido: debe existir al menos un <rDE> directo o envuelto por <xDE>."
            )
        
        if debug_enabled:
            if structure.mode == "direct_rde":
                print(
                    f"✅ Sanity check: rLoteDE contiene {structure.direct_rde_sifen_count} rDE directos "
                    f"en namespace SIFEN (sin xDE)."
                )
            else:
                print(
                    f"✅ Sanity check: lote contiene {structure.xde_sifen_count} xDE y "
                    f"{structure.nested_rde_total} rDE dentro de ellos (1:1)."
                )
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
                xde_ok = xde_count == rde_count and rde_count >= 1
                sanity_report = (
                    f"Lote XML Sanity Report\n"
                    f"======================\n"
                    f"root localname: {root_localname}\n"
                    f"root nsmap: {root_nsmap}\n"
                    f"children(local): {children_local}\n"
                    f"rDE count: {rde_count}\n"
                    f"xDE count: {xde_count}\n"
                    f"\n"
                    f"Status: {'✅ OK' if xde_ok else '❌ ERROR'}\n"
                    f"  - xDE/rDE 1:1: {'✅' if xde_ok else '❌'}\n"
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
        print(f"   - Contiene xDE -> rDE: ✅")
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
    6. Existe <ds:Signature> como hijo directo de <rDE>
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
                de_files = [f for f in namelist if f.startswith("de_") and f.endswith(".xml")]
                has_lote = "lote.xml" in namelist
                if (not has_lote) and (not de_files):
                    error_msg = f"ZIP no contiene de_*.xml ni lote.xml. Archivos encontrados: {namelist}"
                    artifacts_dir.joinpath("preflight_zip.zip").write_bytes(zip_bytes)
                    return (False, error_msg)
                
                if len(namelist) != 1:
                    error_msg = f"ZIP debe contener solo 'lote.xml', encontrado: {namelist}"
                    artifacts_dir.joinpath("preflight_zip.zip").write_bytes(zip_bytes)
                    return (False, error_msg)
                
                # Extraer lote.xml si no se proporcionó
                if lote_xml_bytes is None:
                    lote_xml_bytes = zf.read("lote.xml")
        except zipfile.BadZipFile as e:
            error_msg = f"ZIP no es válido: {e}"
            artifacts_dir.joinpath("preflight_zip.zip").write_bytes(zip_bytes)
            return (False, error_msg)
        
        # 4. Validar que lote.xml parsea y tiene estructura correcta
        try:
            parser = etree.XMLParser(remove_blank_text=False, recover=False)
            lote_root = etree.fromstring(lote_xml_bytes, parser=parser)
            
            # Validar que NO contiene <dId>
            lote_xml_str = lote_xml_bytes.decode("utf-8", errors="replace")
            if "<dId" in lote_xml_str or "</dId>" in lote_xml_str:
                error_msg = "lote.xml NO debe contener <dId> (pertenece al SOAP rEnvioLote)"
                artifacts_dir.joinpath("preflight_lote.xml").write_bytes(lote_xml_bytes)
                return (False, error_msg)

            structure = _analyze_lote_structure(lote_root)
            if not structure.valid or structure.first_rde is None:
                error_msg = structure.message or "lote.xml debe contener al menos un <rDE> (o <xDE> con 1 <rDE>)."
                artifacts_dir.joinpath("preflight_lote.xml").write_bytes(lote_xml_bytes)
                preflight_report = (
                    f"Preflight Validation Failed\n"
                    f"==========================\n"
                    f"Error: {error_msg}\n"
                    f"\n"
                    f"Structure Analysis:\n"
                    f"  root.tag: {lote_root.tag}\n"
                    f"  root.nsmap: {lote_root.nsmap if hasattr(lote_root, 'nsmap') else {}}\n"
                    f"  mode: {structure.mode}\n"
                    f"  direct_rDE(total/SIFEN): {structure.direct_rde_count}/{structure.direct_rde_sifen_count}\n"
                    f"  xDE(total/SIFEN): {structure.xde_count}/{structure.xde_sifen_count}\n"
                    f"  nested_rDE_total: {structure.nested_rde_total}\n"
                )
                artifacts_dir.joinpath("preflight_report.txt").write_text(
                    preflight_report,
                    encoding="utf-8"
                )
                return (False, error_msg)

            rde_elem = structure.first_rde
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
        
        DS_NS_URI = "http://www.w3.org/2000/09/xmldsig#"
        sig_elem = None
        for child in list(rde_elem):
            if local_tag(child.tag) == "Signature" and _namespace_uri(child.tag) == DS_NS_URI:
                sig_elem = child
                break

        if sig_elem is None:
            for elem in de_elem.iter():
                if local_tag(elem.tag) == "Signature" and _namespace_uri(elem.tag) == DS_NS_URI:
                    sig_elem = elem
                    break
        
        if sig_elem is None:
            error_msg = "PREFLIGHT FALLÓ: No se encontró <ds:Signature> dentro de <rDE> (ni dentro de <DE>)"
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


def build_r_envio_lote_xml(did: Union[int, str], xml_bytes: bytes, zip_base64: Optional[str] = None) -> str:
    """
    Construye el XML rEnvioLote con el lote comprimido en Base64.
    
    Args:
        did: ID del documento (IGNORADO - siempre se genera uno nuevo de 15 dígitos)
        xml_bytes: XML original (puede ser rDE o siRecepDE)
        zip_base64: Base64 del ZIP (opcional, se calcula si no se proporciona)
        
    Returns:
        XML rEnvioLote como string
    """
    # Función para generar dId único de 15 dígitos
    def make_did_15() -> str:
        """Genera un dId único de 15 dígitos: YYYYMMDDHHMMSS + 1 dígito random"""
        import random
        base = dt.datetime.now().strftime("%Y%m%d%H%M%S")  # 14 dígitos
        return base + str(random.randint(0, 9))  # + 1 dígito random = 15
    
    # SIEMPRE generar dId de 15 dígitos (ignorar el parámetro did)
    did = make_did_15()  # SIEMPRE (no reutilizar nada)
    
    # Si ya tenemos zip_base64 del proceso de firma, usarlo
    # Solo llamar a build_lote_base64_from_single_xml si no tenemos ZIP
    xde_b64 = None  # Inicializar variable
    print(f"🔍 DEBUG: zip_base64 al inicio = {'None' if zip_base64 is None else 'presente'}")
    if zip_base64 is None:
        print("🔍 DEBUG: zip_base64 es None, verificando xml_bytes...")
        # Verificar si xml_bytes ya contiene un rDE firmado con dVerFor
        # para evitar reconstruir y perder dVerFor
        parser_check = etree.XMLParser(remove_blank_text=False)
        try:
            temp_root = etree.fromstring(xml_bytes, parser_check)
            rde_check = temp_root if local_tag(temp_root.tag) == "rDE" else temp_root.find(".//rDE")
            if rde_check is not None:
                print("🔍 DEBUG: rDE encontrado en xml_bytes")
                # Buscar dVerFor con y sin namespace
                dver_check = rde_check.find(".//dVerFor")
                if dver_check is None:
                    dver_check = rde_check.find(f".//{{{SIFEN_NS}}}dVerFor")
                if dver_check is not None:
                    print("✅ DEBUG: rDE ya firmado contiene dVerFor, construyendo lote sin reprocesar")
                    # Construir lote directamente sin modificar el rDE firmado
                    lote_xml_bytes = (
                        b'<?xml version="1.0" encoding="utf-8"?>'
                        b'<rLoteDE xmlns="' + SIFEN_NS.encode("utf-8") + b'">'
                        b'<xDE>' +
                        etree.tostring(rde_check, encoding="utf-8", xml_declaration=False, with_tail=False) +
                        b'</xDE>'
                        b'</rLoteDE>'
                    )
                    # Crear ZIP
                    zip_bytes = _zip_lote_xml_bytes(lote_xml_bytes)
                    zip_base64 = base64.b64encode(zip_bytes).decode("ascii")
                    
                    # Guardar lote con dVerFor para futuros usos
                    artifacts_dir = Path("artifacts")
                    artifacts_dir.mkdir(parents=True, exist_ok=True)
                    try:
                        artifacts_dir.joinpath("last_lote.xml").write_bytes(lote_xml_bytes)
                        artifacts_dir.joinpath("last_xde.zip").write_bytes(zip_bytes)
                        print("💾 Guardado lote con dVerFor en artifacts/last_lote.xml")
                    except Exception as e:
                        print(f"⚠️  No se pudo guardar artifacts: {e}")
                else:
                    print("⚠️  DEBUG: rDE firmado no contiene dVerFor, usando build_lote_base64_from_single_xml")
                    xde_b64 = build_lote_base64_from_single_xml(xml_bytes)
            else:
                print("⚠️  DEBUG: No se encontró rDE en xml_bytes, usando build_lote_base64_from_single_xml")
                xde_b64 = build_lote_base64_from_single_xml(xml_bytes)
        except Exception as e:
            print(f"⚠️  ERROR al verificar rDE firmado: {e}, usando build_lote_base64_from_single_xml")
            xde_b64 = build_lote_base64_from_single_xml(xml_bytes)
        
        if zip_base64 is None:
            zip_base64 = xde_b64
    else:
        print("✅ DEBUG: Usando ZIP existente (ya firmado con dVerFor)")
        xde_b64 = zip_base64
        
        # Verificar si el ZIP tiene dVerFor y agregarlo si falta
        import zipfile
        import io
        import xml.etree.ElementTree as ET
        try:
            zip_data = base64.b64decode(zip_base64)
            with zipfile.ZipFile(io.BytesIO(zip_data), 'r') as zf:
                with zf.open('lote.xml') as f:
                    lote_xml = f.read().decode('utf-8')
                    
            # Parsear y verificar dVerFor
            root = ET.fromstring(lote_xml)
            NS = {'s': 'http://ekuatia.set.gov.py/sifen/xsd'}
            rde = root.find('.//s:rDE', NS)
            
            if rde is not None:
                dver = rde.find('.//s:dVerFor', NS)
                if dver is None:
                    print("🔧 ZIP existente no tiene dVerFor, agregándolo...")
                    # Agregar dVerFor como primer hijo
                    dver_new = ET.SubElement(rde, f"{{{SIFEN_NS}}}dVerFor")
                    dver_new.text = "150"
                    # Mover al principio
                    rde.insert(0, dver_new)
                    
                    # Re-serializar lote
                    lote_xml_fixed = ET.tostring(root, encoding='utf-8', xml_declaration=True)
                    
                    # Crear nuevo ZIP
                    zip_bytes_fixed = _zip_lote_xml_bytes(lote_xml_fixed)
                    zip_base64 = base64.b64encode(zip_bytes_fixed).decode('ascii')
                    xde_b64 = zip_base64
                    
                    # Guardar el ZIP corregido
                    artifacts_dir = Path("artifacts")
                    artifacts_dir.mkdir(parents=True, exist_ok=True)
                    try:
                        artifacts_dir.joinpath("last_lote.xml").write_bytes(lote_xml_fixed)
                        artifacts_dir.joinpath("last_xde.zip").write_bytes(zip_bytes_fixed)
                        print("💾 ZIP corregido guardado con dVerFor")
                    except Exception as e:
                        print(f"⚠️  No se pudo guardar artifacts: {e}")
                else:
                    print("✅ ZIP existente ya tiene dVerFor")
        except Exception as e:
            print(f"⚠️  Error al verificar ZIP existente: {e}")

    envio_root_name = _resolve_envio_lote_root()
    # Construir rEnvioLote con namespace por defecto
    rEnvioLote = etree.Element(etree.QName(SIFEN_NS, envio_root_name), nsmap={None: SIFEN_NS})
    dId = etree.SubElement(rEnvioLote, etree.QName(SIFEN_NS, "dId"))
    dId.text = did  # Usar el dId de 15 dígitos generado
    xDE = etree.SubElement(rEnvioLote, etree.QName(SIFEN_NS, "xDE"))
    xDE.text = xde_b64

    return etree.tostring(rEnvioLote, xml_declaration=True, encoding="utf-8").decode("utf-8")


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
    import re
    
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
        try:
            normalize_cdc_in_rde(
                root,
                log_prefix="🔄 Regenerando CDC con nuevo timbrado",
                log_if_unchanged=True,
            )
        except Exception as e:
            raise RuntimeError(f"Error al generar CDC tras override de timbrado: {e}") from e
    
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


def _ensure_cdc_consistency(
    root: etree._Element,
    *,
    override_numdoc: Optional[str] = None,
    log_prefix: str = "🧾 CDC normalization",
    log_if_unchanged: bool = False,
) -> Dict[str, Any]:
    """
    Normaliza dNumDoc, recalcula CDC (DE@Id) y dDVId reconstruyendo desde el XML real.
    """
    NS = {"s": SIFEN_NS}

    def _required_text(node: etree._Element, xpath: str, label: str) -> Tuple[etree._Element, str]:
        target = node.find(xpath, namespaces=NS)
        if target is None or target.text is None or not target.text.strip():
            raise RuntimeError(f"No se encontró <{label}> al recalcular CDC")
        return target, target.text.strip()

    gtimb = root.find(".//s:gTimb", namespaces=NS)
    if gtimb is None:
        raise RuntimeError("No se encontró <gTimb> necesario para recalcular CDC")

    dnumdoc_el, current_numdoc = _required_text(gtimb, "s:dNumDoc", "dNumDoc")

    if override_numdoc is not None:
        override_digits = "".join(c for c in str(override_numdoc) if c.isdigit())
        if not override_digits:
            raise ValueError("--bump-doc debe contener dígitos")
        target_numdoc = override_digits.zfill(7)[-7:]
    else:
        digits = "".join(c for c in current_numdoc if c.isdigit())
        if not digits:
            raise RuntimeError("dNumDoc no contiene dígitos para recalcular CDC")
        target_numdoc = digits.zfill(7)[-7:]
    old_numdoc = current_numdoc
    dnumdoc_el.text = target_numdoc

    gemis = root.find(".//s:gEmis", namespaces=NS)
    if gemis is None:
        raise RuntimeError("No se encontró <gEmis> para recalcular CDC")

    _, ruc_text = _required_text(gemis, "s:dRucEm", "dRucEm")
    dv_emi_el = gemis.find("s:dDVEmi", namespaces=NS)
    dv_emi = dv_emi_el.text.strip() if dv_emi_el is not None and dv_emi_el.text else ""
    ruc_for_cdc = f"{ruc_text}-{dv_emi}" if dv_emi else ruc_text

    _, timbrado = _required_text(gtimb, "s:dNumTim", "dNumTim")
    _, establecimiento = _required_text(gtimb, "s:dEst", "dEst")
    _, punto = _required_text(gtimb, "s:dPunExp", "dPunExp")
    _, tipo_doc = _required_text(gtimb, "s:iTiDE", "iTiDE")

    gdatgral = root.find(".//s:gDatGralOpe", namespaces=NS)
    if gdatgral is None:
        raise RuntimeError("No se encontró <gDatGralOpe> para recalcular CDC")
    _, fecha_emi = _required_text(gdatgral, "s:dFeEmiDE", "dFeEmiDE")
    fecha_ymd = re.sub(r"\D", "", fecha_emi)[:8]
    if len(fecha_ymd) != 8:
        raise RuntimeError(f"Fecha de emisión inválida para CDC: {fecha_emi!r}")

    de_elem = root.find(".//s:DE", namespaces=NS)
    if de_elem is None:
        # Fallback: buscar sin namespace
        for candidate in root.iter():
            if isinstance(candidate.tag, str) and _localname(candidate.tag) == "DE":
                de_elem = candidate
                break
    if de_elem is None:
        raise RuntimeError("No se encontró <DE> para actualizar CDC")

    try:
        new_cdc, new_dv = build_cdc_from_de_xml(root)
    except Exception as exc:
        raise RuntimeError(f"No se pudo reconstruir CDC desde el XML: {exc}") from exc

    old_cdc = de_elem.get("Id") or de_elem.get("id") or ""
    de_elem.set("Id", new_cdc)

    ddvid_elem = de_elem.find("s:dDVId", namespaces=NS)
    if ddvid_elem is None:
        ddvid_elem = de_elem.find(".//s:dDVId", namespaces=NS)
    if ddvid_elem is None:
        raise RuntimeError("No se encontró <dDVId> en el DE")
    ddvid_elem.text = new_dv

    changed = (old_cdc != new_cdc) or (old_numdoc != target_numdoc)
    if changed:
        print(f"\n{log_prefix}")
        if old_numdoc != target_numdoc:
            print(f"   dNumDoc {old_numdoc} -> {target_numdoc}")
        if old_cdc and old_cdc != new_cdc:
            print(f"   ⚠️  CDC recalculado automáticamente: {old_cdc} -> {new_cdc}")
        elif not old_cdc:
            print(f"   CDC establecido: {new_cdc}")
    elif log_if_unchanged:
        print(f"\n{log_prefix}")
        print(f"   dNumDoc sin cambios ({target_numdoc})")
        print(f"   CDC sin cambios ({new_cdc})")

    return {
        "changed": changed,
        "old_cdc": old_cdc,
        "new_cdc": new_cdc,
        "old_numdoc": old_numdoc,
        "new_numdoc": target_numdoc,
    }


def normalize_cdc_in_rde(
    rde_el: etree._Element,
    *,
    log_prefix: str = "🧾 CDC normalization",
    log_if_unchanged: bool = False,
    override_numdoc: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Expone la normalización de CDC para reutilizar en firma y pruebas.
    """
    if not isinstance(rde_el, etree._Element):
        raise TypeError("normalize_cdc_in_rde requiere un elemento lxml")
    return _ensure_cdc_consistency(
        rde_el,
        override_numdoc=override_numdoc,
        log_prefix=log_prefix,
        log_if_unchanged=log_if_unchanged,
    )


def apply_bump_doc(
    xml_bytes: bytes,
    bump_doc_value: str,
    env: str,
    artifacts_dir: Optional[Path] = None,
) -> bytes:
    """
    Ajusta dNumDoc y regenera el CDC/dDVId para pruebas en TEST.
    """
    if env != "test":
        raise ValueError("--bump-doc solo está permitido cuando --env=test")

    raw_value = (bump_doc_value or "").strip()
    if not raw_value:
        raise ValueError("Valor --bump-doc vacío")
    if not raw_value.isdigit():
        raise ValueError("--bump-doc debe ser numérico (ej: 2 ó 123)")

    parser = etree.XMLParser(remove_blank_text=False, recover=False)
    try:
        root = etree.fromstring(xml_bytes, parser=parser)
    except Exception as exc:
        raise ValueError(f"XML inválido para bump-doc: {exc}") from exc

    normalize_cdc_in_rde(
        root,
        log_prefix="🧪 TEST bump-doc activo",
        log_if_unchanged=True,
        override_numdoc=raw_value,
    )

    serialized = etree.tostring(
        root,
        xml_declaration=True,
        encoding="UTF-8",
        pretty_print=True,
    )

    target_dir = artifacts_dir or Path("artifacts")
    try:
        target_dir.mkdir(parents=True, exist_ok=True)
        target_file = target_dir / "last_rde_bumped.xml"
        target_file.write_bytes(serialized)
    except Exception as exc:
        print(f"⚠️  No se pudo guardar last_rde_bumped.xml: {exc}")

    return serialized


def find_latest_sirecepde(artifacts_dir: Path, pattern: str = "sirecepde_*.xml") -> Optional[Path]:
    """
    Busca el archivo sirecepde_*.xml más reciente en artifacts/ para --xml latest.
    """
    if not artifacts_dir.exists():
        return None

    files = sorted(
        artifacts_dir.glob(pattern),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )
    return files[0] if files else None


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


def _detect_input_is_lote_file(xml_path: Path) -> bool:
    try:
        parser = etree.XMLParser(remove_blank_text=False)
        root = etree.fromstring(xml_path.read_bytes(), parser=parser)
        return local_tag(root.tag) == "rLoteDE"
    except Exception:
        return False


def _prepare_stress_base_numdoc(xml_path: Path, override: Optional[str]) -> str:
    if override:
        digits = "".join(ch for ch in str(override) if ch.isdigit())
        if not digits:
            raise ValueError("--bump-doc para stress debe contener dígitos")
        return digits.zfill(7)[-7:]
    detected = _extract_dnumdoc_from_file(xml_path)
    if detected:
        return detected
    return "0000001"


def _print_cli_result(result: dict) -> None:
    success_flag = result.get("success") is True
    print("\n" + "=" * 60)
    print("=== RESULT ===")
    print(f"success: {success_flag}")
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
    stress_summary = result.get("stress_summary")
    if stress_summary:
        print("\nstress_summary:")
        summary_text = stress_summary.get("summary")
        if summary_text:
            print(f"  {summary_text}")
        print(
            f"  total_runs={stress_summary.get('total_runs')}, "
            f"success_runs={stress_summary.get('success_runs')}, "
            f"dCodRes0301={stress_summary.get('code_0301')}, "
            f"dProtConsLote>0={stress_summary.get('prot_nonzero')}, "
            f"http_errors={stress_summary.get('http_errors')}"
        )
    print("=" * 60)


def _run_stress_mode(
    *,
    runs: int,
    xml_path: Path,
    env: str,
    artifacts_dir: Path,
    dump_http: bool,
    lote_source: Optional[str],
    strict_xsd: bool,
    xsd_dir: Optional[str],
    skip_ruc_gate: bool,
    skip_ruc_gate_reason: Optional[str],
    base_bump_doc: Optional[str],
) -> dict:
    if runs <= 0:
        return {"success": False, "error": "--stress debe ser >= 1"}
    if _detect_input_is_lote_file(xml_path):
        return {
            "success": False,
            "error": "--stress no soporta XML ya firmado como rLoteDE. Proporcione el rDE individual.",
        }
    try:
        base_numdoc = _prepare_stress_base_numdoc(xml_path, base_bump_doc)
    except Exception as exc:
        return {"success": False, "error": str(exc)}

    print(f"\n🧪 Stress mode: {runs} envíos secuenciales (base dNumDoc={base_numdoc})")
    metrics = {
        "total_runs": runs,
        "success_runs": 0,
        "code_0301": 0,
        "prot_nonzero": 0,
        "http_errors": 0,
        "run_details": [],
    }

    last_result: Optional[dict] = None
    backoff_seconds = 1

    for idx in range(runs):
        bump_value = _increment_numdoc(base_numdoc, idx)
        print(f"\n===== Stress run {idx + 1}/{runs} (dNumDoc={bump_value}) =====")
        result = send_sirecepde(
            xml_path=xml_path,
            env=env,
            artifacts_dir=artifacts_dir,
            dump_http=dump_http,
            bump_doc=bump_value,
            strict_xsd=strict_xsd,
            xsd_dir=xsd_dir,
            lote_source=lote_source,
            skip_ruc_gate=skip_ruc_gate,
            skip_ruc_gate_reason=skip_ruc_gate_reason,
        )
        last_result = result
        response = result.get("response") or {}
        code = None
        prot = None
        if isinstance(response, dict):
            code = (
                response.get("codigo_respuesta")
                or response.get("dCodRes")
                or response.get("d_cod_res")
            )
            prot = response.get("d_prot_cons_lote")
            if prot in (None, "", 0, "0"):
                prot = response.get("dProtConsLote")

        code_str = (str(code).strip()) if code is not None else ""
        prot_value = prot
        detail = {
            "run": idx + 1,
            "bump_doc": bump_value,
            "success": result.get("success") is True,
            "dCodRes": code_str or None,
            "dProtConsLote": prot_value,
            "error_type": result.get("error_type"),
            "error": result.get("error"),
        }
        metrics["run_details"].append(detail)

        if detail["success"]:
            metrics["success_runs"] += 1
            if prot_value not in (None, "", 0, "0"):
                metrics["prot_nonzero"] += 1
        else:
            error_upper = (result.get("error") or "").upper()
            if result.get("error_type") == "SifenClientError" or "HTTP" in error_upper:
                metrics["http_errors"] += 1

        if code_str == "0301":
            metrics["code_0301"] += 1
            print("⚠️  dCodRes=0301 recibido — detenido para evitar spam (posible bloqueo 10-60 min).")
            print("   Sugerencia: esperar y/o cambiar CDC antes de reintentar.")
            break
        else:
            backoff_seconds = 1

    print("\n=== STRESS SUMMARY ===")
    print(
        f"Total runs: {metrics['total_runs']} | Success: {metrics['success_runs']} | "
        f"dProtConsLote>0: {metrics['prot_nonzero']} | "
        f"dCodRes=0301: {metrics['code_0301']} | HTTP errors: {metrics['http_errors']}"
    )

    all_success = metrics["success_runs"] == metrics["total_runs"] and metrics["http_errors"] == 0
    summary_text = (
        f"{metrics['success_runs']}/{metrics['total_runs']} OK, "
        f"{metrics['code_0301']} con dCodRes=0301, "
        f"{metrics['prot_nonzero']} con dProtConsLote>0, "
        f"{metrics['http_errors']} errores HTTP"
    )
    metrics["summary"] = summary_text

    final_result = {
        "success": all_success,
        "response": last_result.get("response") if last_result else None,
        "response_file": last_result.get("response_file") if last_result else None,
        "error": None if all_success else f"Stress mode falló: {summary_text}",
        "stress_summary": metrics,
    }
    if not all_success and last_result and last_result.get("error"):
        final_result.setdefault("last_error", last_result.get("error"))
    if last_result and last_result.get("error_type"):
        final_result.setdefault("error_type", last_result.get("error_type"))
    return final_result


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


def send_sirecepde(
    xml_path: Path,
    env: str = "test",
    artifacts_dir: Optional[Path] = None,
    dump_http: bool = False,
    skip_ruc_gate: Optional[bool] = None,
    skip_ruc_gate_reason: Optional[str] = None,
    bump_doc: Optional[str] = None,
    strict_xsd: bool = False,
    xsd_dir: Optional[str] = None,
    lote_source: Optional[str] = None,
) -> dict:
    """
    Envía un XML siRecepDE al servicio SOAP de Recepción de SIFEN
    
    Args:
        xml_path: Path al archivo XML siRecepDE
        env: Ambiente ('test' o 'prod')
        artifacts_dir: Directorio para guardar respuestas (opcional)
        lote_source: 'last_lote' (default) para usar artifacts/last_lote.xml o 'memory'
        
    Returns:
        Diccionario con resultado del envío
    """
    # Inicializar variable did para evitar UnboundLocalError
    did = None
    
    # Configurar bypass del GATE (puede venir por ENV o CLI)
    env_skip_gate = os.getenv("SIFEN_SKIP_RUC_GATE", "").strip().lower() in ("1", "true", "yes", "y", "s", "si")
    gate_bypass_active = env_skip_gate or bool(skip_ruc_gate)
    if gate_bypass_active:
        if skip_ruc_gate:
            gate_bypass_reason = skip_ruc_gate_reason or "CLI --skip-ruc-gate"
        elif env_skip_gate:
            gate_bypass_reason = skip_ruc_gate_reason or "ENV:SIFEN_SKIP_RUC_GATE=1"
        else:
            gate_bypass_reason = skip_ruc_gate_reason
    else:
        gate_bypass_reason = None

    # Leer XML como bytes
    print(f"📄 Cargando XML: {xml_path}")
    try:
        xml_bytes = xml_path.read_bytes()
    except Exception as e:
        return {
            "success": False,
            "error": f"Error al leer archivo XML: {str(e)}",
            "error_type": type(e).__name__
        }
    
    # Detectar si el XML ya es un lote rLoteDE (pre-firmado)
    input_is_lote = False
    xml_root_original = None
    
    # DEBUG: Check dVerFor in original bytes
    print(f"🔍 DEBUG: dVerFor en xml_bytes original: {b'<dVerFor>150</dVerFor>' in xml_bytes}")
    
    try:
        parser_detect = etree.XMLParser(remove_blank_text=False)
        xml_root_original = etree.fromstring(xml_bytes, parser=parser_detect)
        input_is_lote = local_tag(xml_root_original.tag) == "rLoteDE"
        
        # DEBUG: Check after parsing
        if input_is_lote:
            rde_nodes = xml_root_original.xpath(".//*[local-name()='rDE']")
            if rde_nodes:
                dVerFor = rde_nodes[0].find("{http://ekuatia.set.gov.py/sifen/xsd}dVerFor")
                print(f"🔍 DEBUG: dVerFor después de parsear: {dVerFor is not None}")
                if dVerFor is not None:
                    print(f"   Valor: {dVerFor.text}")
                    
    except Exception as e:
        # Si falla el parse, continuar (se detectará más adelante)
        print(f"⚠️  WARNING: No se pudo parsear XML para detección de lote: {e}")
        import traceback
        traceback.print_exc()

    # Normalización/bump solo si NO es lote prearmado
    if not input_is_lote:
        xml_bytes = normalize_despaisrec_tags(xml_bytes)
        xml_bytes = apply_timbrado_override(xml_bytes, artifacts_dir=artifacts_dir)

        if bump_doc:
            try:
                xml_bytes = apply_bump_doc(
                    xml_bytes=xml_bytes,
                    bump_doc_value=bump_doc,
                    env=env,
                    artifacts_dir=artifacts_dir,
                )
            except Exception as e:
                return {
                    "success": False,
                    "error": f"No se pudo aplicar bump-doc ({bump_doc}): {e}",
                    "error_type": type(e).__name__,
                }
    else:
        if bump_doc:
            print("⚠️  WARNING: Ignorando --bump-doc porque el archivo ya es un rLoteDE firmado.")
    
    xml_size = len(xml_bytes)
    print(f"   Tamaño: {xml_size} bytes ({xml_size / 1024:.2f} KB)\n")
    
    # Import config module needed later
    try:
        from app.sifen_client.config import get_sifen_config
    except ImportError:
        get_sifen_config = None
    
    # Validar RUC del emisor antes de enviar (evitar código 1264)
    # Solo validar si no está activo el bypass del gate
    if not gate_bypass_active:
        try:
            from app.sifen_client.ruc_validator import validate_emisor_ruc
            
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
                    "note": "Configure SIFEN_EMISOR_RUC con el RUC real del contribuyente habilitado (formato: RUC-DV, ej. 4554737-8)"
                }
            
            print("✓ RUC del emisor validado (no es dummy)\n")
        except ImportError:
            # Si no se puede importar el validador, continuar sin validación (no crítico)
            print("⚠️  No se pudo importar validador de RUC, continuando sin validación\n")
        except Exception as e:
            # Si falla la validación por otro motivo, continuar (no bloquear)
            print(f"⚠️  Error en validación de RUC (no bloqueante): {e}\n")
    else:
        print(f"⚠️  Bypass de validación RUC activo: {gate_bypass_reason}\n")
    
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
    ruc_emisor_for_diag: Optional[str] = None
    ruc_gate_cached: Optional[str] = None
    ruc_check_data: Optional[Dict[str, Any]] = None
    
    # Configurar cliente SIFEN
    print(f"🔧 Configurando cliente SIFEN (ambiente: {env})...")
    if get_sifen_config is None:
        error_msg = "No se pudo importar get_sifen_config (módulo app.sifen_client.config no disponible)"
        print(f"❌ {error_msg}")
        return {
            "success": False,
            "error": error_msg,
            "error_type": "ImportError"
        }
    
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
    goto_send = False  # Flag para indicar si debemos saltar directamente al envío (modo AS-IS)
    try:
        if input_is_lote:
            print("📦 Usando lote provisto (rLoteDE) — se omite firma P12")
            try:
                lote_root = xml_root_original if xml_root_original is not None else etree.fromstring(xml_bytes)
            except Exception as e:
                raise RuntimeError(f"No se pudo parsear el lote provisto: {e}") from e

            rde_nodes = lote_root.xpath(".//*[local-name()='rDE']")
            if not rde_nodes:
                raise RuntimeError("El XML provisto es rLoteDE pero no contiene ningún rDE")
            has_sifen_ns = any(etree.QName(el).namespace == SIFEN_NS for el in rde_nodes if isinstance(el.tag, str))
            if not has_sifen_ns:
                raise RuntimeError("El rLoteDE provisto no contiene rDE en el namespace SIFEN")

            first_de = None
            for elem in rde_nodes[0].xpath(".//*[local-name()='DE']"):
                first_de = elem
                break
            de_id_detected = first_de.get("Id") if first_de is not None else None
            signature_present = bool(lote_root.xpath(".//*[local-name()='Signature']"))
            print(
                f"   rDE count={len(rde_nodes)}, "
                f"DE.Id={de_id_detected or 'N/A'}, "
                f"Signature={'sí' if signature_present else 'no'}"
            )

            structure = _analyze_lote_structure(lote_root)
            if not structure.valid:
                raise RuntimeError(
                    structure.message
                    or "El rLoteDE provisto no cumple la estructura mínima (rDE directo o xDE -> rDE)."
                )

            normalized_lote_root = lote_root
            if structure.direct_rde_sifen_count > 0 and structure.xde_wrapper_count == 0:
                normalized_lote_root = _wrap_direct_rde_with_xde(lote_root)
                # ✅ MUY IMPORTANTE: estos bytes son los que deben ir al ZIP
                xml_bytes = etree.tostring(
                    normalized_lote_root,
                    xml_declaration=True,
                    encoding="utf-8",
                    pretty_print=False,
                )
                # ✅ y este tree es el que debe seguir el flujo (huellas, guards, etc.)
                xml_root_original = normalized_lote_root
                print(
                    f"   ↺ Normalizado: {structure.direct_rde_sifen_count} rDE directos envueltos en xDE "
                    "para cumplir con el layout esperado."
                )

            lote_xml_bytes = xml_bytes
            zip_bytes = _zip_lote_xml_bytes(lote_xml_bytes)
            zip_base64 = base64.b64encode(zip_bytes).decode("ascii")
            print("✓ Lote provisto validado\n")
            
            # DEBUG: Check dVerFor before sending
            if b'<dVerFor>150</dVerFor>' in lote_xml_bytes:
                print("✅ DEBUG: dVerFor encontrado en lote_xml_bytes")
            else:
                print("❌ DEBUG: dVerFor NO encontrado en lote_xml_bytes")
                # Show what we have instead
                if b'<rDE' in lote_xml_bytes:
                    start = lote_xml_bytes.find(b'<rDE')
                    end = lote_xml_bytes.find(b'>', start) + 1
                    print(f"   rDE opening: {lote_xml_bytes[start:end]}")
            
            # MODO AS-IS: Para lotes pre-armados, omitir el flujo normal de _select_lote_payload
            # y usar directamente el lote proporcionado por el usuario
            print(f"📦 Modo LOTE AS-IS: usando el XML tal cual se recibió: {xml_path}")
            
            # Opcional: Validación rápida con xmlsec si está disponible
            if os.getenv("SIFEN_VALIDATE_LOTE_BEFORE_SEND", "1") in ("1", "true", "True"):
                try:
                    import subprocess
                    result = subprocess.run(
                        ["xmlsec1", "--verify", "--insecure", "--id-attr:Id", "DE", str(xml_path)],
                        capture_output=True,
                        text=True,
                        timeout=30
                    )
                    if result.returncode == 0:
                        print("✅ Validación xmlsec1 del lote: OK")
                    else:
                        print(f"⚠️  Validación xmlsec1 del lote: FALLÓ\n{result.stderr}")
                except (subprocess.TimeoutExpired, FileNotFoundError, Exception) as ex:
                    print(f"⚠️  No se pudo validar con xmlsec1: {ex}")
            
            # Crear una selección especial para modo AS-IS
            selection = LotePayloadSelection(
                lote_bytes=lote_xml_bytes,
                zip_bytes=zip_bytes,
                zip_base64=zip_base64,
                source=f"file:{xml_path}",
                lote_path=xml_path,
                zip_path=None,
            )
            
            # Para modo AS-IS, saltar directamente al envío (omitir _select_lote_payload)
            goto_send = True
        else:
            # GUARD-RAIL: Verificar dependencias críticas antes de firmar
            try:
                _check_signing_dependencies()
            except RuntimeError as e:
                error_msg = f"BLOQUEADO: {str(e)}. Ejecutar scripts/bootstrap_env.sh"
                try:
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

            try:
                print("📦 Construyendo y firmando lote desde XML individual...")
                
                # Leer certificado de firma (fallback a mTLS o CERT_PATH si no hay específico de firma)
                sign_cert_path = os.getenv("SIFEN_SIGN_P12_PATH") or os.getenv("SIFEN_MTLS_P12_PATH") or os.getenv("SIFEN_CERT_PATH")
                sign_cert_password = os.getenv("SIFEN_SIGN_P12_PASSWORD") or os.getenv("SIFEN_MTLS_P12_PASSWORD") or os.getenv("SIFEN_CERT_PASSWORD")
                
                if not sign_cert_path or not sign_cert_password:
                    return {
                        "success": False,
                        "error": "Falta certificado de firma (SIFEN_SIGN_P12_PATH o SIFEN_MTLS_P12_PATH y su contraseña)",
                        "error_type": "ConfigurationError"
                    }
                
                # Verificar si el XML ya es un lote firmado (rLoteDE)
                xml_root = etree.fromstring(xml_bytes)
                is_already_lote = xml_root.tag == f"{{{SIFEN_NS}}}rLoteDE"
                
                if is_already_lote:
                    print("✓ XML detectado como lote ya firmado (rLoteDE)")
                    # Para lotes ya firmados, solo necesitamos:
                    # 1. Verificar que tenga dVerFor
                    # 2. Crear el ZIP sin modificar el XML
                    # 3. No volver a firmar
                    
                    # Verificar dVerFor
                    rde = xml_root.find(f".//{{{SIFEN_NS}}}rDE")
                    if rde is not None:
                        dver = rde.find(".//dVerFor")
                        if dver is None or dver.text != "150":
                            print("⚠️  Agregando dVerFor=150 al lote existente")
                            dver_elem = etree.SubElement(rde, "dVerFor")
                            dver_elem.text = "150"
                            # Mover dVerFor al principio
                            children = list(rde)
                            rde.clear()
                            rde.append(dver_elem)
                            for child in children:
                                rde.append(child)
                    
                    # Serializar y crear ZIP
                    lote_xml_bytes = etree.tostring(xml_root, xml_declaration=True, encoding="utf-8", pretty_print=False)
                    
                    # Crear ZIP
                    import zipfile
                    import io
                    zip_buffer = io.BytesIO()
                    with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as zf:
                        zf.writestr('lote.xml', lote_xml_bytes)
                    zip_bytes = zip_buffer.getvalue()
                    
                    # Base64
                    import base64
                    zip_base64 = base64.b64encode(zip_bytes).decode('ascii')
                    
                    # Guardar artifacts
                    if artifacts_dir:
                        zip_path = artifacts_dir / "last_lote.zip"
                        zip_path.write_bytes(zip_bytes)
                        lote_path = artifacts_dir / "last_lote.xml"
                        lote_path.write_bytes(lote_xml_bytes)
                else:
                    print("🔐 Construyendo lote completo y firmando rDE in-place...")
                    # Flujo normal para DE individual
                    try:
                        # Crear directorio del run
                        timestamp = dt.datetime.now().strftime("%Y%m%d_%H%M%S")
                        run_dir = (artifacts_dir or Path("artifacts")) / f"runs_async/{timestamp}_{env}"
                        run_dir.mkdir(parents=True, exist_ok=True)
                        
                        # Guardar DE original (unsigned)
                        de_unsigned_path = run_dir / f"de_unsigned_{timestamp}.xml"
                        de_unsigned_path.write_bytes(xml_bytes)
                        print(f"📄 UNSIGNED: {de_unsigned_path}")
                        
                        # Verificar que DE unsigned no tiene Signature
                        if b'<Signature' in xml_bytes:
                            print("⚠️  WARNING: DE unsigned contiene Signature - no debería tenerla")
                        else:
                            print("✅ DE unsigned verificado: no contiene Signature")
                        
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
                            
                            # Extraer y guardar rDE firmado
                            import xml.etree.ElementTree as ET
                            root = ET.fromstring(lote_xml_bytes)
                            ns = {'sifen': 'http://ekuatia.set.gov.py/sifen/xsd'}
                            rde = root.find('.//sifen:rDE', ns)
                            
                            if rde is not None:
                                rde_bytes = ET.tostring(rde, encoding='utf-8', method='xml')
                                # Extraer ID del DE para el nombre
                                de_elem = rde.find('.//sifen:DE', ns)
                                if de_elem is not None:
                                    de_id = de_elem.get('Id', 'unknown')
                                else:
                                    de_id = 'unknown'
                                
                                # Guardar rDE firmado
                                if artifacts_dir:
                                    rde_signed_path = artifacts_dir / f"rde_signed_{de_id}.xml"
                                    rde_signed_path.write_bytes(rde_bytes)
                                
                                # Extraer y guardar lote.xml del ZIP para debug
                                if zip_bytes:
                                    import zipfile
                                    import io
                                    with zipfile.ZipFile(io.BytesIO(zip_bytes), 'r') as zf:
                                        with zf.open('lote.xml') as xml_file:
                                            xml_content = xml_file.read()
                                            lote_extraido_path = run_dir / "lote_extraido.xml"
                                            lote_extraido_path.write_bytes(xml_content)
                                
                                print("\n🔍 Comandos para verificación local:")
                                print(f"  xmlsec1 --verify --insecure --id-attr:Id DE {rde_signed_path if 'rde_signed_path' in locals() else lote_extraido_path}")
                                print(f"  xmlsec1 --verify --insecure --id-attr:Id http://ekuatia.set.gov.py/sifen/xsd:DE {lote_extraido_path}")
                                
                                # Continuar con el flujo normal...
                        else:
                            zip_base64 = result
                            zip_bytes = base64.b64decode(zip_base64)
                            lote_xml_bytes = None
                    except Exception as e:
                        error_msg = f"Error al construir lote: {str(e)}"
                        error_type = type(e).__name__
                        import traceback
                        traceback.print_exc()
                        return {
                            "success": False,
                            "error": error_msg,
                            "error_type": error_type,
                            "traceback": traceback.format_exc()
                        }
            except Exception as e:
                error_msg = f"Error al procesar lote: {str(e)}"
                print(f"❌ {error_msg}", file=sys.stderr)
                import traceback
                traceback.print_exc(file=sys.stderr)
                return {
                    "success": False,
                    "error": error_msg,
                    "error_type": type(e).__name__,
                    "traceback": traceback.format_exc()
                }
            
            # EXTRAER rDE FIRMADO del lote para usarlo en el SOAP
            # El xml_bytes original ya no sirve - necesitamos el rDE firmado
            if zip_bytes:
                import zipfile
                import io
                with zipfile.ZipFile(io.BytesIO(zip_bytes), 'r') as zf:
                    with zf.open('lote.xml') as xml_file:
                        lote_content = xml_file.read()
                        # Parsear el lote para extraer el rDE firmado
                        lote_root = etree.fromstring(lote_content)
                        rde_elem = None
                        for elem in lote_root:
                            if elem.tag == '{http://ekuatia.set.gov.py/sifen/xsd}xDE':
                                if len(elem) > 0 and elem[0].tag == '{http://ekuatia.set.gov.py/sifen/xsd}rDE':
                                    rde_elem = elem[0]
                                    break
                        if rde_elem is not None:
                            # Asegurar que dVerFor esté presente
                            dverfor = rde_elem.find(".//dVerFor")
                            if dverfor is None:
                                dverfor = rde_elem.find(f".//{{{SIFEN_NS}}}dVerFor")
                            if dverfor is None:
                                # Agregar dVerFor como primer hijo
                                dverfor_new = etree.SubElement(rde_elem, f"{{{SIFEN_NS}}}dVerFor")
                                dverfor_new.text = "150"
                                rde_elem.insert(0, dverfor_new)
                                print("🔧 dVerFor agregado al rDE extraído del lote")
                            
                            # Actualizar xml_bytes con el rDE firmado
                            xml_bytes = etree.tostring(
                                rde_elem,
                                encoding='utf-8',
                                xml_declaration=True,
                                pretty_print=False
                            )
                            print("✅ xml_bytes actualizado con rDE firmado del lote")
                        else:
                            print("⚠️  No se pudo extraer rDE del lote, usando xml_bytes original")
                
                print("✓ Lote construido y rDE firmado exitosamente\n")
                
                # Guardar artifacts para diagnóstico 0160
                try:
                    artifacts_dir = Path("artifacts")
                    artifacts_dir.mkdir(parents=True, exist_ok=True)
                    
                    # Extraer CDC del XML para nombrar archivos
                    cdc_for_filename = "unknown"
                    try:
                        xml_root = etree.fromstring(xml_bytes)
                        de_elem = xml_root.find(f".//{{{SIFEN_NS}}}DE")
                        if de_elem is None:
                            for elem in xml_root.iter():
                                if isinstance(elem.tag, str) and local_tag(elem.tag) == "DE":
                                    de_elem = elem
                                    break
                        if de_elem is not None:
                            cdc_for_filename = de_elem.get("Id") or de_elem.get("id") or "unknown"
                    except Exception:
                        pass
                    
                    # Extraer dId del XML para nombrar archivos
                    did_for_filename = "unknown"
                    try:
                        xml_root = etree.fromstring(xml_bytes)
                        d_id_elem = xml_root.find(f".//{{{SIFEN_NS}}}dId")
                        if d_id_elem is not None and d_id_elem.text:
                            did_for_filename = d_id_elem.text.strip()
                    except Exception:
                        pass
                    
                    # Guardar lote_built_<dId>.xml (lote completo final antes de zip)
                    if lote_xml_bytes:
                        lote_built_path = artifacts_dir / f"lote_built_{did_for_filename}.xml"
                        lote_built_path.write_bytes(lote_xml_bytes)
                        print(f"   💾 {lote_built_path}")
                    
                    # Guardar rde_signed_<CDC>.xml (DE firmado con Signature)
                    try:
                        # Extraer rDE firmado del lote
                        if lote_xml_bytes:
                            lote_root = etree.fromstring(lote_xml_bytes)
                            rde_elem = None
                            for elem in lote_root:
                                if isinstance(elem.tag, str) and local_tag(elem.tag) == "rDE":
                                    rde_elem = elem
                                    break
                            if rde_elem is not None:
                                rde_signed_bytes = etree.tostring(
                                    rde_elem,
                                    encoding="utf-8",
                                    xml_declaration=True,
                                    pretty_print=False
                                )
                                rde_signed_path = artifacts_dir / f"rde_signed_{cdc_for_filename}.xml"
                                rde_signed_path.write_bytes(rde_signed_bytes)
                                print(f"   💾 {rde_signed_path}")
                    except Exception as e:
                        print(f"   ⚠️  No se pudo guardar rde_signed: {e}")
                    
                    # Guardar lote_zip_<dId>.zip (ZIP para inspección local)
                    lote_zip_path = artifacts_dir / f"lote_zip_{did_for_filename}.zip"
                    lote_zip_path.write_bytes(zip_bytes)
                    print(f"   💾 {lote_zip_path}")
                    
                except Exception as e:
                    print(f"   ⚠️  Error al guardar artifacts de diagnóstico: {e}")
            
            print("✓ Lote construido y rDE firmado exitosamente\n")
            
            # Construir payload XML para SOAP
            payload_xml = build_r_envio_lote_xml(
                did=did,
                xml_bytes=xml_bytes,
                zip_base64=zip_base64
            )
            
            # Validar payload con XSD (opcional, solo para debug)
            validation_result = validate_xml_with_xsd(payload_xml, env=env)
            
            if not validation_result.valid:
                print(f"❌ Validación XSD fallida: {validation_result.message}")
                if validation_result.xml_path and validation_result.xml_path.exists():
                    print(f"   Ver: {validation_result.xml_path}")
                if validation_result.report_path and validation_result.report_path.exists():
                    print(f"   Reporte: {validation_result.report_path}")
            else:
                print("✅ Validación XSD exitosa")
            
            # Sanity checks: RUC, etc.
            _run_sanity_checks(lote_xml_bytes, cert_path=sign_cert_path)
            
            # Modo AS-IS: usar XML/ZIP tal cual sin firmar ni construir
            if goto_send:
                try:
                    # Para modo AS-IS, xml_bytes ya debe contener el rDE firmado
                    if not xml_bytes:
                        return {
                            "success": False,
                            "error": "Modo AS-IS requiere que --xml apunte a un rDE firmado",
                            "error_type": "ValidationError"
                        }
                    
                    # Generar ZIP desde el rDE firmado
                    zip_base64 = build_lote_base64_from_single_xml(xml_bytes, return_debug=False)
                    zip_bytes = base64.b64decode(zip_base64)
                    
                    # Generar dId
                    did = make_did_15()
                    
                    # Construir payload
                    payload_xml = build_r_envio_lote_xml(
                        did=did,
                        xml_bytes=xml_bytes,
                        zip_base64=zip_base64
                    )
                    
                    # Enviar
                    print("\n📡 Enviando a SIFEN (modo AS-IS)...")
                    client = SoapClient(env=env)
                    response = client.recepcion_lote(payload_xml)
                    
                    return {
                        "success": response.ok,
                        "response": response,
                        "payload_xml": payload_xml,
                        "xml_bytes": xml_bytes,
                        "zip_bytes": zip_bytes,
                        "zip_base64": zip_base64,
                        "artifacts_dir": artifacts_dir
                    }
                except Exception as e:
                    error_msg = f"Error en modo AS-IS: {str(e)}"
                    print(f"❌ {error_msg}", file=sys.stderr)
                    import traceback
                    traceback.print_exc(file=sys.stderr)
                    return {
                        "success": False,
                        "error": error_msg,
                        "error_type": type(e).__name__,
                        "traceback": traceback.format_exc()
                    }
            
            # Enviar a SIFEN
            print("\n📡 Enviando a SIFEN...")
            client = SoapClient(env=env)
            response = client.recepcion_lote(payload_xml)
            
            return {
                "success": response.ok,
                "response": response,
                "payload_xml": payload_xml,
                "lote_xml_bytes": lote_xml_bytes,
                "zip_bytes": zip_bytes,
                "zip_base64": zip_base64,
                "validation": validation_result,
                "artifacts_dir": artifacts_dir
            }
    except Exception as e:
        error_msg = f"Error general al procesar: {str(e)}"
        print(f"❌ {error_msg}", file=sys.stderr)
        import traceback
        traceback.print_exc(file=sys.stderr)
        return {
            "success": False,
            "error": error_msg,
            "error_type": type(e).__name__,
            "traceback": traceback.format_exc()
        }


def make_did_15() -> str:
    """Genera un dId único de 15 dígitos: YYYYMMDDHHMMSS + 1 dígito random"""
    import random
    base = dt.datetime.now().strftime("%Y%m%d%H%M%S")  # 14 dígitos
    return base + str(random.randint(0, 9))  # + 1 dígito random = 15


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
  SIFEN_VALIDATE_XSD     1/true para validar XSD local antes de enviar
"""
    )
    
    parser.add_argument(
        "--env",
        choices=["test", "prod"],
        help="Ambiente SIFEN (test/prod). Por defecto usa SIFEN_ENV o 'test'."
    )
    parser.add_argument(
        "--xml",
        required=True,
        help="Path al archivo XML a enviar. Puede ser 'latest' para usar el más reciente."
    )
    parser.add_argument(
        "--dump-http",
        action="store_true",
        help="Imprime完整的 HTTP request/response en stderr"
    )
    parser.add_argument(
        "--strict-xsd",
        action="store_true",
        help="Abortar si la validación XSD local falla (en lugar de solo advertir)"
    )
    parser.add_argument(
        "--bump-doc",
        type=int,
        metavar="N",
        help="Incrementa números de documento en N (para testing rápido)"
    )
    parser.add_argument(
        "--lote-source",
        choices=["last_lote", "last_lote_built", "last_sent"],
        help="Fuente del lote a enviar (ver docs/USAGE_SEND_SIRECEPDE.md)"
    )
    
    args = parser.parse_args()
    
    # Determinar ambiente
    env = args.env or os.getenv("SIFEN_ENV", "test")
    
    # Determinar path del XML
    xml_path = args.xml
    if xml_path == "latest":
        xml_path = find_latest_xml(env)
        if not xml_path:
            print("❌ No se encontró ningún XML reciente", file=sys.stderr)
            return 1
        print(f"→ Usando XML más reciente: {xml_path}")
    
    # Verificar que el archivo existe
    xml_path = Path(xml_path)
    if not xml_path.exists():
        print(f"❌ El archivo no existe: {xml_path}", file=sys.stderr)
        return 1
    
    # Verificar variables de entorno requeridas
    required_vars = ["SIFEN_CERT_PATH", "SIFEN_CERT_PASSWORD"]
    missing_vars = [var for var in required_vars if not os.getenv(var)]
    
    if missing_vars:
        print(f"❌ Faltan variables de entorno requeridas: {', '.join(missing_vars)}", file=sys.stderr)
        print("Consulte docs/SETUP.md para configurar las variables.", file=sys.stderr)
        return 1
    
    # Enviar
    result = send_sirecepde_lote(
        xml_path=xml_path,
        env=env,
        dump_http=args.dump_http,
        strict_xsd=args.strict_xsd,
        bump_doc=args.bump_doc,
        lote_source=args.lote_source,
        skip_ruc_gate=False,
        skip_last_lote_mismatch=False,
        goto_send=args.goto_send
    )
    
    exit_code = 0 if result.get("success") is True else 1
    _print_cli_result(result)
    if args.dump_http:
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
