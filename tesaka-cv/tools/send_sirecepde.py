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
from typing import Optional
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


def build_lote_base64_from_single_xml(xml_bytes: bytes, return_debug: bool = False) -> str | tuple[str, bytes, bytes]:
    """
    Crea un ZIP con el rDE firmado envuelto en rLoteDE.
    
    El ZIP contiene un único archivo "lote.xml" con:
    - Root: <rLoteDE xmlns="http://ekuatia.set.gov.py/sifen/xsd">
    - Contenido: un <rDE> completo (ya normalizado, firmado y reordenado) como hijo directo.
    
    IMPORTANTE: 
    - Selecciona SIEMPRE el rDE que tiene <ds:Signature> como hijo directo.
    - NO modifica la firma ni los hijos del rDE, solo lo envuelve en rLoteDE.
    
    Args:
        xml_bytes: XML que contiene el rDE (puede ser rDE root o tener rDE anidado)
        
    Returns:
        Base64 del ZIP como string
        
    Raises:
        ValueError: Si no se encuentra rDE o si el rDE no tiene Signature como hijo directo
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
    
    # Parsear xml_bytes
    try:
        xml_root = etree.fromstring(xml_bytes)
    except Exception as e:
        raise ValueError(f"Error al parsear XML: {e}")
    
    # Construir lista de candidatos rDE
    candidates_rde = []
    
    # Caso a) si local-name(root) == "rDE"
    if local_tag(xml_root.tag) == "rDE":
        candidates_rde = [xml_root]
    else:
        # Caso b) buscar todos los rDE con namespace SIFEN
        candidates_rde = xml_root.findall(f".//{{{SIFEN_NS}}}rDE")
        # Caso c) si sigue vacío, buscar sin namespace
        if not candidates_rde:
            candidates_rde = xml_root.xpath(".//*[local-name()='rDE']")
    
    # Si no se encontró ningún rDE
    if not candidates_rde:
        raise ValueError(
            "No se encontró rDE en el XML de entrada (no se puede construir lote)."
        )
    
    # Seleccionar el candidato correcto: el que tiene Signature como hijo directo
    signed = [el for el in candidates_rde if is_signed_rde(el)]
    
    if len(signed) >= 1:
        rde_el = signed[0]
    else:
        # Opcional: buscar por gCamFuFD como fallback (pero igualmente validar Signature)
        gcam = [
            el for el in candidates_rde
            if any(local_tag(child.tag) == "gCamFuFD" for child in list(el))
        ]
        if gcam:
            rde_el = gcam[0]
            # Validar que tenga Signature (si no, abortar)
            if not is_signed_rde(rde_el):
                raise ValueError(
                    "Se encontró rDE pero NO contiene <ds:Signature> como hijo directo. "
                    "Probablemente se pasó XML no firmado o se eligió el rDE equivocado."
                )
        else:
            raise ValueError(
                "Se encontró rDE pero NO contiene <ds:Signature> como hijo directo. "
                "Probablemente se pasó XML no firmado o se eligió el rDE equivocado."
            )
    
    # Debug: mostrar información de selección
    debug_enabled = os.getenv("SIFEN_DEBUG_SOAP", "0") in ("1", "true", "True")
    if debug_enabled:
        print(f"🧪 DEBUG [build_lote_base64] candidates_rDE: {len(candidates_rde)}")
        print(f"🧪 DEBUG [build_lote_base64] selected_rDE_signed: {is_signed_rde(rde_el)}")
        selected_children = [local_tag(c.tag) for c in list(rde_el)]
        print(f"🧪 DEBUG [build_lote_base64] selected_rDE_children: {', '.join(selected_children)}")
    
    # IMPORTANTE: NO "reconstruyas" rDE ni cambies hijos; solo lo vas a envolver.
    # Usar deepcopy para no perder attrs o ns
    rde_copy = copy.deepcopy(rde_el)
    
    # Construir wrapper rLoteDE
    rlote_de = etree.Element(
        etree.QName(SIFEN_NS, "rLoteDE"),
        nsmap={None: SIFEN_NS}
    )
    rlote_de.append(rde_copy)
    
    # Serializar lote_content
    lote_xml_bytes = etree.tostring(
        rlote_de,
        xml_declaration=True,
        encoding="utf-8",
        pretty_print=False
    )
    
    # Crear ZIP con exactamente un archivo "lote.xml"
    mem = BytesIO()
    with zipfile.ZipFile(mem, mode="w", compression=zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("lote.xml", lote_xml_bytes)
    zip_bytes = mem.getvalue()
    
    # Check rápido dentro de build_lote_base64_from_single_xml (solo cuando SIFEN_DEBUG_SOAP=1)
    if debug_enabled:
        try:
            # Abrir el ZIP en memoria y verificar
            with zipfile.ZipFile(BytesIO(zip_bytes), "r") as zf:
                zip_files = zf.namelist()
                print(f"🧪 DEBUG [build_lote_base64] ZIP files: {zip_files}")
                
                if "lote.xml" in zip_files:
                    lote_content = zf.read("lote.xml")
                    lote_root = etree.fromstring(lote_content)
                    
                    root_tag = local_tag(lote_root.tag)
                    print(f"🧪 DEBUG [build_lote_base64] root: {root_tag}")
                    
                    # Verificar que existe rDE dentro de rLoteDE
                    rde_found = lote_root.find(f".//{{{SIFEN_NS}}}rDE")
                    if rde_found is None:
                        rde_found = lote_root.find(".//rDE")
                    
                    has_rde = rde_found is not None
                    print(f"🧪 DEBUG [build_lote_base64] has_rDE: {has_rde}")
                    
                    if has_rde and root_tag == "rLoteDE":
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
                    elif root_tag != "rLoteDE":
                        print(f"⚠️  WARNING [build_lote_base64] root debería ser rLoteDE, es {root_tag}")
        except Exception as e:
            print(f"⚠️  DEBUG [build_lote_base64] error al verificar ZIP: {e}")
    
    # Base64 estándar sin saltos
    return base64.b64encode(zip_bytes).decode("ascii")


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
    
    # Normalizar rDE antes de firmar (dDesPaisRec -> dDesPaisRe, mover gCamFuFD)
    xml_bytes = normalize_rde_before_sign(xml_bytes)
    
    # Firmar XML si hay certificado de firma disponible
    sign_p12_path = os.getenv("SIFEN_SIGN_P12_PATH")
    sign_p12_password = os.getenv("SIFEN_SIGN_P12_PASSWORD")

    if sign_p12_path and sign_p12_password:
        try:
            from app.sifen_client.xmlsec_signer import sign_de_with_p12
            print(f"🔐 Firmando XML con certificado: {Path(sign_p12_path).name}")
            xml_signed = sign_de_with_p12(xml_bytes, sign_p12_path, sign_p12_password)
            print("✓ XML firmado exitosamente\n")
            
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
                    
                    return {
                        "success": False,
                        "error": error_msg,
                        "error_type": "XSDValidationError",
                        "validation_result": validation_result
                    }
                
                print()  # Línea en blanco después de validación
    except Exception as e:
        return {
            "success": False,
            "error": f"Error al construir lote: {str(e)}",
            "error_type": type(e).__name__
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
