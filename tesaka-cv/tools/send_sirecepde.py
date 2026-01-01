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
from pathlib import Path
from typing import Optional, Union, Tuple
from datetime import datetime
from io import BytesIO
import base64
import zipfile

# Agregar el directorio padre al path para imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from dotenv import load_dotenv

# Cargar variables de entorno
load_dotenv()

# Constantes de namespace SIFEN
SIFEN_NS = "http://ekuatia.set.gov.py/sifen/xsd"
NS = {"s": SIFEN_NS}

# Helper regex para detectar XML declaration
_XML_DECL_RE = re.compile(br"^\s*<\?xml[^>]*\?>\s*", re.I)


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

try:
    import lxml.etree as etree  # noqa: F401
except ImportError:
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
    
    # Redactar xDE en el payload para el debug file
    payload_redacted = re.sub(
        r'<xDE[^>]*>.*?</xDE>',
        f'<xDE>__BASE64_REDACTED_LEN_{len(zip_base64)}__</xDE>',
        payload_xml,
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
        f.write(payload_redacted)
        f.write("\n---- SOAP END ----\n")
        f.write(f"\nNOTE: Este payload NO fue enviado a SIFEN porque PRECHECK falló.\n")
        f.write(f"Para inspeccionar el ZIP real, usar: --zip-file /tmp/lote_payload.zip\n")
    
    # 2. Guardar soap_last_request_headers.txt
    headers_file = artifacts_dir / "soap_last_request_headers.txt"
    with headers_file.open("w", encoding="utf-8") as f:
        f.write("Content-Type: application/xml; charset=utf-8\n")
        f.write("Accept: application/soap+xml, text/xml, */*\n")
    
    # 3. Guardar soap_last_request.xml (payload redactado)
    request_file = artifacts_dir / "soap_last_request.xml"
    request_file.write_text(payload_redacted, encoding="utf-8")
    
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


def _local(tag: str) -> str:
    """Extrae el nombre local de un tag (sin namespace)."""
    return tag.split("}", 1)[-1] if "}" in tag else tag


def normalize_rde_before_sign(xml_bytes: bytes) -> bytes:
    """
    Normaliza el XML rDE antes de firmar:
    - Cambia dDesPaisRec -> dDesPaisRe (si existe)
    - Mueve gCamFuFD de dentro de <DE> a fuera, dentro de <rDE>, antes de <Signature>
    """
    parser = etree.XMLParser(remove_blank_text=False)
    root = etree.fromstring(xml_bytes, parser)

    def local(tag): return tag.split("}", 1)[-1] if "}" in tag else tag
    def find_by_local(el, name):
        for x in el.iter():
            if local(x.tag) == name:
                return x
        return None

    # Tomar rDE (raíz o anidado)
    rde = root if local(root.tag) == "rDE" else find_by_local(root, "rDE")
    if rde is None:
        return xml_bytes

    # 1) dDesPaisRec -> dDesPaisRe (si existe)
    dd_rec = find_by_local(rde, "dDesPaisRec")
    if dd_rec is not None:
        parent = dd_rec.getparent()
        idx = parent.index(dd_rec)
        new_el = etree.Element(etree.QName(SIFEN_NS, "dDesPaisRe"))
        new_el.text = dd_rec.text
        parent.remove(dd_rec)
        parent.insert(idx, new_el)

    # 2) gCamFuFD debe ser hijo de rDE, no de DE
    de = None
    for ch in rde:
        if local(ch.tag) == "DE":
            de = ch
            break

    if de is not None:
        gcam = None
        for ch in list(de):
            if local(ch.tag) == "gCamFuFD":
                gcam = ch
                break

        if gcam is not None:
            de.remove(gcam)

            # Insertar antes de Signature si existe; si no, al final
            sig = None
            for ch in rde:
                if local(ch.tag) == "Signature":
                    sig = ch
                    break

            if sig is not None:
                rde.insert(rde.index(sig), gcam)
            else:
                rde.append(gcam)

    return etree.tostring(root, xml_declaration=True, encoding="utf-8")


def reorder_signature_before_gcamfufd(xml_bytes: bytes) -> bytes:
    """
    Reordena los hijos de <rDE> para que Signature venga antes de gCamFuFD.
    Orden esperado: dVerFor, DE, Signature, gCamFuFD
    NO rompe la firma: solo cambia el orden de hermanos.
    """
    def local(tag: str) -> str:
        return tag.split("}", 1)[-1] if "}" in tag else tag

    root = etree.fromstring(xml_bytes)

    # Localizar <rDE> (puede ser raíz o anidado)
    rde = root if local(root.tag) == "rDE" else next((e for e in root.iter() if local(e.tag) == "rDE"), None)
    if rde is None:
        return xml_bytes

    # Encontrar Signature y gCamFuFD como hijos directos de rDE
    children = list(rde)
    sig = next((c for c in children if local(c.tag) == "Signature"), None)
    gcam = next((c for c in children if local(c.tag) == "gCamFuFD"), None)

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
    rde.remove(sig)
    # Recalcular índice de gCamFuFD después de remover sig
    children_after = list(rde)
    gcam_idx_after = children_after.index(gcam)
    rde.insert(gcam_idx_after, sig)

    return etree.tostring(root, xml_declaration=True, encoding="utf-8")


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
    
    def local_tag(tag: str) -> str:
        return tag.split("}", 1)[-1] if "}" in tag else tag
    
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
        print("🔐 Firmando XML completo (rDE no tiene Signature como hijo directo)...")
        
        # Guardar XML original antes de firmar (debug)
        if debug_enabled and artifacts_dir:
            artifacts_dir.mkdir(exist_ok=True)
            (artifacts_dir / "xml_before_sign_normalize.xml").write_bytes(xml_bytes)
            print(f"💾 Guardado: {artifacts_dir / 'xml_before_sign_normalize.xml'}")
        
        # Normalizar XML completo antes de firmar
        xml_bytes = normalize_rde_before_sign(xml_bytes)
        xml_bytes = ensure_rde_default_namespace(xml_bytes)
        
        # Firmar XML COMPLETO (no el fragmento rDE aislado)
        try:
            from app.sifen_client.xmlsec_signer import sign_de_with_p12
            signed_full = sign_de_with_p12(xml_bytes, cert_path, cert_password)
            print("✓ XML completo firmado exitosamente")
        except Exception as e:
            error_msg = f"Error al firmar XML completo: {e}"
            print(f"❌ {error_msg}", file=sys.stderr)
            traceback.print_exc(file=sys.stderr)
            raise RuntimeError(error_msg)
        
        # Guardar XML firmado (debug)
        if debug_enabled and artifacts_dir:
            (artifacts_dir / "xml_after_sign_normalize.xml").write_bytes(signed_full)
            print(f"💾 Guardado: {artifacts_dir / 'xml_after_sign_normalize.xml'}")
        
        # Re-parsear XML firmado y localizar rDE
        try:
            root = etree.fromstring(signed_full)
        except Exception as e:
            raise ValueError(f"Error al re-parsear XML firmado: {e}")
        
        # Buscar rDE en el XML firmado
        if local_tag(root.tag) == "rDE":
            rde_el = root
            is_root_rde = True
        else:
            rde_el = _find_by_localname(root, "rDE")
            if rde_el is None:
                error_msg = "No se encontró <rDE> en el XML firmado"
                print(f"❌ {error_msg}", file=sys.stderr)
                print(f"   Root tag: {root.tag} (local: {local_tag(root.tag)})", file=sys.stderr)
                raise ValueError(error_msg)
            is_root_rde = False
        
        # Validar que ahora tenga Signature como hijo directo
        has_signature_after = any(
            child.tag == f"{{{DSIG_NS}}}Signature" or local_tag(child.tag) == "Signature"
            for child in list(rde_el)
        )
        
        if not has_signature_after:
            # Diagnóstico detallado
            root_tag = root.tag
            root_local = local_tag(root_tag)
            root_ns = root_tag.split("}", 1)[0][1:] if "}" in root_tag else "VACÍO"
            rde_children = [local_tag(c.tag) for c in list(rde_el)]
            
            error_msg = (
                f"ERROR: Después de firmar, el rDE NO tiene <ds:Signature> como hijo directo.\n"
                f"Root tag: {root_local} (ns: {root_ns})\n"
                f"rDE hijos directos: {', '.join(rde_children) if rde_children else '(ninguno)'}"
            )
            print(f"❌ {error_msg}", file=sys.stderr)
            raise RuntimeError(error_msg)
        
        print("✓ rDE firmado tiene Signature como hijo directo (validado)")
        
        # Guardar rDE después de firma (debug)
        if debug_enabled and artifacts_dir:
            rde_after_bytes = etree.tostring(rde_el, xml_declaration=False, encoding="utf-8")
            (artifacts_dir / "rde_after_sign.xml").write_bytes(rde_after_bytes)
            print(f"💾 Guardado: {artifacts_dir / 'rde_after_sign.xml'}")
        
        # Usar el XML firmado completo como base
        xml_bytes = signed_full
    else:
        # Ya tiene Signature, pero verificar orden
        rde_el = rde_el  # No cambiar referencia
        print("✓ rDE ya tiene Signature, verificando orden...")
    
    # Reordenar hijos de rDE: dVerFor, DE, Signature, gCamFuFD (determinístico)
    # Obtener referencias usando find() con namespaces
    dverfor = rde_el.find(f"./{{{SIFEN_NS}}}dVerFor")
    de = rde_el.find(f"./{{{SIFEN_NS}}}DE")
    gcamfufd = rde_el.find(f"./{{{SIFEN_NS}}}gCamFuFD")
    
    # Buscar Signature: primer hijo directo cuyo localname == 'Signature' y ns == DSIG_NS
    signature = None
    for child in list(rde_el):
        if local_tag(child.tag) == "Signature" and child.tag == f"{{{DSIG_NS}}}Signature":
            signature = child
            break
    
    # Verificar si hay otros hijos que no sean los esperados
    expected_children = {dverfor, de, signature, gcamfufd}
    others = [child for child in list(rde_el) if child not in expected_children]
    
    # Construir orden: dVerFor, DE, Signature, gCamFuFD, otros
    ordered_children = []
    if dverfor is not None:
        ordered_children.append(dverfor)
    if de is not None:
        ordered_children.append(de)
    if signature is not None:
        ordered_children.append(signature)
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


def ensure_rde_default_namespace(xml_bytes: bytes) -> bytes:
    """
    Asegura que el elemento rDE tenga namespace default SIFEN_NS en su tag de apertura.
    
    Inserta xmlns="http://ekuatia.set.gov.py/sifen/xsd" en el tag de apertura de rDE
    si no lo tiene, sin modificar el resto del documento.
    
    Args:
        xml_bytes: XML que contiene rDE (puede ser rDE root o tener rDE anidado)
        
    Returns:
        XML con rDE que tiene xmlns default SIFEN_NS
        
    Raises:
        ValueError: Si no se encuentra rDE en el XML
    """
    import re
    
    # Buscar el tag de apertura de rDE (sin prefijo)
    pattern_no_prefix = br"<rDE\b([^>]*)>"
    match = re.search(pattern_no_prefix, xml_bytes)
    
    if not match:
        # Buscar con prefijo (ej: <ns:rDE ...>)
        pattern_with_prefix = br"<([A-Za-z_][\w.-]*):rDE\b([^>]*)>"
        match = re.search(pattern_with_prefix, xml_bytes)
        if match:
            # Si tiene prefijo y ya tiene xmlns para ese prefijo, no modificar
            prefix = match.group(1).decode('utf-8')
            attrs = match.group(2)
            if f'xmlns:{prefix}='.encode('utf-8') in attrs:
                # Ya tiene namespace declarado para el prefijo, no modificar
                return xml_bytes
            # Si tiene prefijo pero no xmlns, no podemos agregar xmlns default fácilmente
            # En este caso, retornar sin modificar (asumir que está bien)
            return xml_bytes
    
    if not match:
        raise ValueError("No se encontró tag <rDE> en el XML")
    
    # Extraer atributos del tag de apertura
    attrs_str = match.group(1 if not match.lastindex or match.lastindex == 1 else 2).decode('utf-8')
    
    # Verificar si ya tiene xmlns default (sin prefijo)
    if 'xmlns="' in attrs_str or 'xmlns=\'' in attrs_str:
        # Ya tiene xmlns default, no modificar
        return xml_bytes
    
    # Si tiene xmlns con prefijo (ej: xmlns:xsi="...") pero NO tiene xmlns default,
    # podemos agregar xmlns default sin problema (no hay conflicto)
    
    # Insertar xmlns="http://ekuatia.set.gov.py/sifen/xsd" en los atributos
    # Insertar al inicio de los atributos (después del espacio si hay otros attrs)
    if attrs_str.strip():
        new_attrs = f' xmlns="{SIFEN_NS}" {attrs_str}'
    else:
        new_attrs = f' xmlns="{SIFEN_NS}"'
    
    # Reemplazar el tag de apertura
    if match.lastindex and match.lastindex > 1:
        # Caso con prefijo: reemplazar todo el tag
        prefix = match.group(1).decode('utf-8')
        old_tag = f'<{prefix}:rDE{attrs_str}>'.encode('utf-8')
        new_tag = f'<{prefix}:rDE{new_attrs}>'.encode('utf-8')
    else:
        # Caso sin prefijo
        old_tag = f'<rDE{attrs_str}>'.encode('utf-8')
        new_tag = f'<rDE{new_attrs}>'.encode('utf-8')
    
    # Reemplazar solo la primera ocurrencia (el tag de apertura)
    result = xml_bytes.replace(old_tag, new_tag, 1)
    
    return result


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


def build_lote_base64_from_single_xml(xml_bytes: bytes, return_debug: bool = False) -> Union[str, Tuple[str, bytes, bytes]]:
    """
    Crea un ZIP con el rDE firmado envuelto en rLoteDE.
    
    El ZIP contiene un único archivo "lote.xml" con:
    - Root: <rLoteDE> (SIN namespace, sin xmlns)
    - Contenido: un <rDE> completo (ya normalizado, firmado y reordenado) como hijo directo.
      El rDE mantiene su xmlns="http://ekuatia.set.gov.py/sifen/xsd" declarado en su propio tag.
    
    IMPORTANTE: 
    - Selecciona SIEMPRE el rDE que tiene <ds:Signature> como hijo directo.
    - NO modifica la firma ni los hijos del rDE, solo lo envuelve en rLoteDE.
    - Usa extracción por regex desde bytes originales (NO re-serializa con lxml) para preservar
      exactamente la firma, namespaces y whitespace del rDE firmado.
    - Según ejemplos oficiales SIFEN: rLoteDE NO debe tener namespace; el namespace debe estar
      declarado en rDE (no en rLoteDE). Esto evita que lxml "hoistee" el xmlns al wrapper.
    
    Args:
        xml_bytes: XML que contiene el rDE (puede ser rDE root o tener rDE anidado)
        return_debug: Si True, retorna tupla (base64, lote_xml_bytes, zip_bytes)
        
    Returns:
        Base64 del ZIP como string, o tupla si return_debug=True
        
    Raises:
        ValueError: Si no se encuentra rDE o si el rDE no tiene Signature como hijo directo
        RuntimeError: Si rLoteDE sale con xmlns= (bug de construcción)
    """
    import copy
    
    # Namespace de firma digital
    DSIG_NS = "http://www.w3.org/2000/09/xmldsig#"
    
    # Helper para obtener local name
    def local_tag(tag: str) -> str:
        return tag.split("}", 1)[-1] if "}" in tag else tag
    
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
            
            # Asegurar que DE tenga namespace SIFEN_NS
            ensure_sifen_ns(de_el)
            
            # Crear rDE mínimo con namespace SIFEN_NS
            rde_el = etree.Element(f"{{{SIFEN_NS}}}rDE", nsmap={None: SIFEN_NS})
            
            # Agregar dVerFor si no existe en DE
            # (verificar si ya existe en el DE o en algún hijo)
            has_dverfor = False
            for child in de_el.iter():
                if local_tag(child.tag) == "dVerFor":
                    has_dverfor = True
                    break
            
            if not has_dverfor:
                dverfor = etree.SubElement(rde_el, f"{{{SIFEN_NS}}}dVerFor")
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
    
    # Guardar artifact de debug del rDE fragment final (si artifacts_dir existe)
    try:
        artifacts_dir = Path("artifacts")
        if artifacts_dir.exists():
            rde_fragment_xml = etree.tostring(rde_el, xml_declaration=True, encoding="utf-8", pretty_print=True)
            debug_rde_file = artifacts_dir / "debug_rde_fragment.xml"
            debug_rde_file.write_bytes(rde_fragment_xml)
            print(f"💾 Guardado artifact debug: {debug_rde_file}")
    except Exception as e:
        # Silencioso: no fallar si no se puede guardar el artifact
        pass
    
    # IMPORTANTE: NO "reconstruyas" rDE ni cambies hijos; solo lo vas a envolver.
    # Según ejemplos oficiales SIFEN:
    # - rLoteDE NO debe tener namespace (root sin xmlns)
    # - El namespace debe estar declarado en rDE (no en rLoteDE)
    # Esto evita que lxml "hoistee" el xmlns al wrapper y rompa la firma
    
    # Detectar root para decidir estrategia de extracción
    root_local, root_ns = _root_info(xml_bytes)
    
    # DE suelto -> wrapper rDE byte-preserving (sin re-serializar para preservar firma)
    if root_local == "DE":
        print(f"🔍 DIAGNÓSTICO [build_lote_base64] Root es DE, construyendo wrapper rDE byte-preserving...")
        # Remover XML declaration si existe (no debe haber declaración dentro del wrapper)
        de_bytes = _strip_xml_decl(xml_bytes).lstrip()
        # Construir rDE fragment envolviendo DE bytes tal cual (preserva firma)
        rde_fragment = (
            f'<rDE xmlns="{SIFEN_NS}"><dVerFor>150</dVerFor>'.encode("utf-8")
            + de_bytes
            + b"</rDE>"
        )
        print(f"🔍 DIAGNÓSTICO [build_lote_base64] rDE fragment construido desde DE: {len(rde_fragment)} bytes")
        
        # Guardar artifact de debug del rDE fragment construido
        try:
            artifacts_dir = Path("artifacts")
            if artifacts_dir.exists():
                debug_rde_file = artifacts_dir / "debug_rde_fragment.xml"
                debug_rde_file.write_bytes(rde_fragment)
                print(f"💾 Guardado artifact debug: {debug_rde_file}")
        except Exception:
            # Silencioso: no fallar si no se puede guardar el artifact
            pass
    else:
        # Caso normal: extraer rDE existente desde bytes (preserva firma)
        try:
            rde_fragment = _extract_rde_fragment_bytes(xml_bytes)
            print(f"🔍 DIAGNÓSTICO [build_lote_base64] rDE fragment extraído: {len(rde_fragment)} bytes")
        except Exception as e:
            # Debugging robusto cuando falla la extracción
            artifacts_dir = Path("artifacts")
            if artifacts_dir.exists():
                try:
                    (artifacts_dir / "debug_input_before_rde_extract.xml").write_bytes(xml_bytes)
                    print(f"💾 DEBUG: guardado debug_input_before_rde_extract.xml ({len(xml_bytes)} bytes)")
                except Exception:
                    pass

            try:
                parser = etree.XMLParser(recover=True, remove_blank_text=True)
                root = etree.fromstring(xml_bytes, parser)
                qn = etree.QName(root)
                has_rde = bool(root.xpath("//*[local-name()='rDE']"))
                has_de = bool(root.xpath("//*[local-name()='DE']"))
                print("🔍 DEBUG extract rDE: root=", qn.localname, "ns=", qn.namespace)
                print("🔍 DEBUG extract rDE: has_rDE=", has_rde, "has_DE=", has_de)
            except Exception as pe:
                print("🔍 DEBUG parse failed:", repr(pe))

            print("🔍 DEBUG first_250:", xml_bytes[:250].decode("utf-8", errors="ignore"))
            raise RuntimeError(f"Error al extraer fragmento rDE desde bytes: {e}")
    
    # IMPORTANTE: si el rDE no trae xmlns default, NO lo inventes acá (eso puede romper firma).
    # Solo envolvemos EXACTO.
    
    # Construir lote.xml con rLoteDE sin namespace usando concatenación de bytes
    lote_xml_bytes = (
        b'<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        b"<rLoteDE>"
        + rde_fragment +
        b"</rLoteDE>"
    )
    
    # Hard-guard: si aparece xmlns en el tag de apertura de rLoteDE, abortar (así no perdés horas)
    # Buscar el tag de apertura <rLoteDE ...> y verificar que NO tenga xmlns=
    rlote_tag_start = lote_xml_bytes.find(b"<rLoteDE")
    if rlote_tag_start >= 0:
        rlote_tag_end = lote_xml_bytes.find(b">", rlote_tag_start)
        if rlote_tag_end > rlote_tag_start:
            rlote_tag = lote_xml_bytes[rlote_tag_start:rlote_tag_end]
            if b"xmlns=" in rlote_tag:
                raise RuntimeError(f"BUG: rLoteDE salió con xmlns= (debe ser SIN namespace). Tag: {rlote_tag}")
    
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
        return b64, lote_xml_bytes, zip_bytes
    return b64


def build_r_envio_lote_xml(did: int, xml_bytes: bytes, zip_base64: Optional[str] = None) -> str:
    """
    Construye el XML rEnvioLote con el lote comprimido en Base64.
    
    Args:
        did: ID del documento
        xml_bytes: XML original (puede ser rDE o siRecepDE)
        zip_base64: Base64 del ZIP (opcional, se calcula si no se proporciona)
        
    Returns:
        XML rEnvioLote como string
    """
    if zip_base64 is None:
        xde_b64 = build_lote_base64_from_single_xml(xml_bytes)
    else:
        xde_b64 = zip_base64

    # Construir rEnvioLote con prefijo xsd (nsmap {"xsd": SIFEN_NS})
    rEnvioLote = etree.Element(etree.QName(SIFEN_NS, "rEnvioLote"), nsmap={"xsd": SIFEN_NS})
    dId = etree.SubElement(rEnvioLote, etree.QName(SIFEN_NS, "dId"))
    dId.text = str(did)
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


def send_sirecepde(xml_path: Path, env: str = "test", artifacts_dir: Optional[Path] = None) -> dict:
    """
    Envía un XML siRecepDE al servicio SOAP de Recepción de SIFEN
    
    Args:
        xml_path: Path al archivo XML siRecepDE
        env: Ambiente ('test' o 'prod')
        artifacts_dir: Directorio para guardar respuestas (opcional)
        
    Returns:
        Diccionario con resultado del envío
    """
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
    
    # Aplicar override de timbrado/fecha inicio si están definidos (ANTES de normalizar/firmar)
    xml_bytes = apply_timbrado_override(xml_bytes, artifacts_dir=artifacts_dir)
    
    # Normalizar rDE antes de firmar (dDesPaisRec -> dDesPaisRe, mover gCamFuFD)
    xml_bytes = normalize_rde_before_sign(xml_bytes)
    
    # Asegurar que rDE tenga namespace default SIFEN_NS antes de firmar
    # Esto es crítico: si rDE no tiene xmlns, cuando lo envolvemos en rLoteDE (sin namespace),
    # el rDE queda sin namespace y SIFEN rechazará con 0160
    xml_bytes = ensure_rde_default_namespace(xml_bytes)
    
    # Firmar XML si hay certificado de firma disponible
    sign_p12_path = os.getenv("SIFEN_SIGN_P12_PATH")
    sign_p12_password = os.getenv("SIFEN_SIGN_P12_PASSWORD")

    if sign_p12_path and sign_p12_password:
        try:
            from app.sifen_client.xmlsec_signer import sign_de_with_p12
            print(f"🔐 Firmando XML con certificado: {Path(sign_p12_path).name}")
            xml_signed = sign_de_with_p12(xml_bytes, sign_p12_path, sign_p12_password)
            print("✓ XML firmado exitosamente\n")
            
            # Hard-guard: verificar que el rDE firmado tiene xmlns default SIFEN_NS
            # Si no lo tiene, cuando lo envolvemos en rLoteDE (sin namespace), el rDE quedará sin namespace
            rde_fragment = _extract_rde_fragment_bytes(xml_signed)
            if b'xmlns="' + SIFEN_NS.encode('utf-8') + b'"' not in rde_fragment:
                # Verificar también con comillas simples
                if b"xmlns='" + SIFEN_NS.encode('utf-8') + b"'" not in rde_fragment:
                    raise RuntimeError(
                        f"ERROR CRÍTICO: El rDE firmado NO contiene xmlns=\"{SIFEN_NS}\" en su tag de apertura. "
                        "Esto causará que cuando se envuelva en rLoteDE (sin namespace), el rDE quede sin namespace "
                        "y SIFEN rechazará con 0160. Verificar ensure_rde_default_namespace()."
                    )
            
            # ✅ Reordenar: Signature debe venir antes de gCamFuFD (POST-FIRMA)
            xml_signed = reorder_signature_before_gcamfufd(xml_signed)
            
            # DEBUG: verificar orden de hijos de rDE
            if os.getenv("SIFEN_DEBUG_SOAP", "0") in ("1", "true", "True"):
                try:
                    root_debug = etree.fromstring(xml_signed)
                    def local_debug(tag): return tag.split("}", 1)[-1] if "}" in tag else tag
                    rde_debug = root_debug if local_debug(root_debug.tag) == "rDE" else next(
                        (e for e in root_debug.iter() if local_debug(e.tag) == "rDE"), None
                    )
                    if rde_debug is not None:
                        children_order = [local_debug(c.tag) for c in list(rde_debug)]
                        print(f"🧪 DEBUG orden hijos rDE: {', '.join(children_order)}")
                except Exception:
                    pass  # No romper el flujo si falla el debug
            
            # DEBUG: guardar para inspección rápida
            Path("/tmp/rde_signed_reordered.xml").write_bytes(xml_signed)
            print("🧪 DEBUG escrito: /tmp/rde_signed_reordered.xml")
            
            # Usar xml_signed para el resto del flujo
            xml_bytes = xml_signed
        except Exception as e:
            return {
                "success": False,
                "error": f"Error al firmar XML: {str(e)}",
                "error_type": type(e).__name__
            }
    elif sign_p12_path or sign_p12_password:
        missing = "SIFEN_SIGN_P12_PASSWORD" if not sign_p12_password else "SIFEN_SIGN_P12_PATH"
        return {
            "success": False,
            "error": f"Falta certificado de firma para XMLDSig: {missing}",
            "error_type": "ConfigurationError"
        }
    
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
        print("📦 Construyendo lote desde XML individual...")
        
        # GARANTIZAR que el rDE esté firmado antes de construir el lote
        # Leer certificado de firma (fallback a mTLS si no hay específico de firma)
        sign_cert_path = os.getenv("SIFEN_SIGN_P12_PATH") or os.getenv("SIFEN_MTLS_P12_PATH")
        sign_cert_password = os.getenv("SIFEN_SIGN_P12_PASSWORD") or os.getenv("SIFEN_MTLS_P12_PASSWORD")
        
        if sign_cert_path and sign_cert_password:
            print("🔐 Verificando y normalizando rDE (firma y orden)...")
            try:
                xml_bytes = sign_and_normalize_rde_inside_xml(
                    xml_bytes=xml_bytes,
                    cert_path=sign_cert_path,
                    cert_password=sign_cert_password,
                    artifacts_dir=artifacts_dir
                )
                print("✓ rDE verificado/normalizado exitosamente\n")
            except Exception as e:
                error_msg = f"Error al verificar/normalizar rDE: {str(e)}"
                print(f"❌ {error_msg}", file=sys.stderr)
                import traceback
                traceback.print_exc(file=sys.stderr)
                return {
                    "success": False,
                    "error": error_msg,
                    "error_type": type(e).__name__,
                    "traceback": traceback.format_exc()
                }
        else:
            print("⚠️  No se encontró certificado de firma (SIFEN_SIGN_P12_PATH o SIFEN_MTLS_P12_PATH)")
            print("   Continuando sin verificar firma del rDE...")
        
        # Obtener dId del XML original si está disponible, sino usar 1
        try:
            xml_root = etree.fromstring(xml_bytes)
            d_id_elem = xml_root.find(f".//{{{SIFEN_NS}}}dId")
            if d_id_elem is not None and d_id_elem.text:
                did = int(d_id_elem.text)
            else:
                did = 1
        except:
            did = 1
        
        # Construir el ZIP base64 primero para poder loguear tamaños (usar bytes directamente)
        # También obtener lote_xml_bytes para validación XSD
        result = build_lote_base64_from_single_xml(xml_bytes, return_debug=True)
        if isinstance(result, tuple):
            zip_base64, lote_xml_bytes, zip_bytes = result
        else:
            zip_base64 = result
            zip_bytes = base64.b64decode(zip_base64)
            lote_xml_bytes = None
        
        # Construir el payload de lote completo (reutilizando zip_base64)
        payload_xml = build_r_envio_lote_xml(did=did, xml_bytes=xml_bytes, zip_base64=zip_base64)
        
        print(f"✓ Lote construido:")
        print(f"   dId: {did}")
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
        
        with SoapClient(config) as client:
            response = client.recepcion_lote(payload_xml)
            
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
                
                # Guardar lote en base de datos
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
    result = send_sirecepde(
        xml_path=xml_path,
        env=env,
        artifacts_dir=artifacts_dir
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
