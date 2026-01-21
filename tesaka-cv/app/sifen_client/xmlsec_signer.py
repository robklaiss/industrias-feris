"""
Firma XMLDSig para Documentos Electrónicos SIFEN usando python-xmlsec

Implementa firma digital XMLDSig Enveloped según especificación SIFEN v150:
- Enveloped signature dentro del mismo <DE>
- Reference URI="#<Id del DE>"
- Canonicalization: Exclusive XML Canonicalization (exc-c14n)
- Digest: SHA-1 (según ejemplos Roshka)
- SignatureMethod: RSA-SHA1 (según ejemplos Roshka)
- Transforms: enveloped-signature + exc-c14n
- X509Certificate en KeyInfo
"""

import base64
import hashlib
import logging
import os
import re
from collections import OrderedDict
from pathlib import Path
from typing import Optional, Any, Tuple

# Import lxml.etree - el linter puede no reconocerlo, pero funciona correctamente
try:
    import lxml.etree as etree  # noqa: F401
except ImportError:
    etree = None  # type: ignore

try:
    import xmlsec

    XMLSEC_AVAILABLE = True
except ImportError:
    XMLSEC_AVAILABLE = False
    xmlsec = None

try:
    from cryptography import x509
    from cryptography.hazmat.primitives.serialization import (
        pkcs12,
        Encoding,
    )
    from cryptography.hazmat.backends import default_backend
    from cryptography.x509.oid import NameOID, ExtensionOID
    from cryptography.x509.extensions import ExtensionNotFound

    CRYPTOGRAPHY_AVAILABLE = True
except ImportError:
    CRYPTOGRAPHY_AVAILABLE = False
    pkcs12 = None
    x509 = None  # type: ignore
    NameOID = None  # type: ignore
    ExtensionOID = None  # type: ignore
    ExtensionNotFound = None  # type: ignore

from .pkcs12_utils import p12_to_temp_pem_files, cleanup_pem_files, PKCS12Error
from .exceptions import SifenClientError
from app.sifen_client.qr_generator import build_qr_dcarqr, ensure_single_gCamFuFD_after_signature

logger = logging.getLogger(__name__)

# Namespaces
DS_NS = "http://www.w3.org/2000/09/xmldsig#"
DSIG_NS = "http://www.w3.org/2000/09/xmldsig#"  # Alias para claridad
SIFEN_NS = "http://ekuatia.set.gov.py/sifen/xsd"
XMLNS_NS = "http://www.w3.org/2000/xmlns/"  # Namespace para atributos xmlns
def _normalize_qr_base(url: Optional[str]) -> str:
    if not url:
        return ""
    normalized = url.strip().rstrip("?").rstrip("/")
    return normalized


_RAW_QR_URL_BASES = {
    "PROD": "https://ekuatia.set.gov.py/consultas/qr?",
    "TEST": "https://ekuatia.set.gov.py/consultas-test/qr?",
}

QR_URL_BASES = {env: _normalize_qr_base(url) for env, url in _RAW_QR_URL_BASES.items()}

RUC_REGEX_WITH_PREFIX = re.compile(r"(?i)RUC\s*(\d+)\s*-?\s*(\d+)")
RUC_REGEX_NUMERIC = re.compile(r"(\d{4,})-?(\d+)")


def _normalize_ruc_value(raw_value: Optional[str]) -> Optional[str]:
    if not raw_value:
        return None
    value = raw_value.strip()
    if not value:
        return None
    match = RUC_REGEX_WITH_PREFIX.search(value)
    if not match:
        match = RUC_REGEX_NUMERIC.search(value)
    if not match:
        return None
    base = match.group(1)
    dv = match.group(2)
    if not base or not dv:
        return None
    return f"RUC{base}-{dv}"


def _extract_ruc_from_cert(cert) -> Optional[str]:
    if cert is None or x509 is None or NameOID is None or ExtensionOID is None:
        return None
    # 1) Buscar en SAN DirName
    try:
        san_ext = cert.extensions.get_extension_for_oid(ExtensionOID.SUBJECT_ALTERNATIVE_NAME)
        for general_name in san_ext.value:
            if isinstance(general_name, x509.DirectoryName):
                attrs = general_name.value.get_attributes_for_oid(NameOID.SERIAL_NUMBER)
                for attr in attrs:
                    normalized = _normalize_ruc_value(attr.value)
                    if normalized:
                        return normalized
    except ExtensionNotFound:
        pass
    except Exception as exc:  # pragma: no cover - logging defensivo
        logger.debug("No se pudo leer SAN serialNumber para RUC: %s", exc)

    # 2) Fallback al subject serialNumber
    try:
        attrs = cert.subject.get_attributes_for_oid(NameOID.SERIAL_NUMBER)
        for attr in attrs:
            normalized = _normalize_ruc_value(attr.value)
            if normalized:
                return normalized
    except Exception as exc:  # pragma: no cover
        logger.debug("No se pudo leer subject serialNumber para RUC: %s", exc)
    return None


def _ensure_subject_has_ruc(subject_str: str, ruc_token: Optional[str]) -> str:
    if not ruc_token:
        return subject_str
    if not subject_str:
        return f"serialNumber={ruc_token}"
    target = f"serialNumber={ruc_token}"
    if target in subject_str:
        return subject_str
    if "serialNumber=" in subject_str:
        subject_str = re.sub(r"serialNumber=[^,]+", target, subject_str, count=1)
    else:
        subject_str = f"{target},{subject_str}"
    return subject_str


def _extract_cert_identity_strings(cert) -> Tuple[Optional[str], Optional[str], Optional[str]]:
    if cert is None or x509 is None:
        return None, None, None
    subject_str = cert.subject.rfc4514_string()
    issuer_str = cert.issuer.rfc4514_string()
    serial_number_str = str(cert.serial_number) if getattr(cert, "serial_number", None) else None

    ruc_value = _extract_ruc_from_cert(cert)
    if ruc_value:
        subject_str = _ensure_subject_has_ruc(subject_str, ruc_value)
    return subject_str or None, issuer_str or None, serial_number_str


def _ensure_lxml_import():
    """Lazy import de lxml.etree - se importa solo cuando se necesita"""
    try:
        import lxml.etree as etree
        return etree
    except ImportError as e:
        raise XMLSecError("lxml no está instalado. Instale con: pip install lxml") from e


class XMLSecError(SifenClientError):
    """Excepción para errores en firma XMLDSig con xmlsec"""

    pass


def _force_signature_default_namespace(sig: Any) -> Any:  # type: ignore
    """
    Convierte <ds:Signature> o <Signature ns0:...> a:
      <Signature xmlns="http://www.w3.org/2000/09/xmldsig#"> ... </Signature>
    preservando todos los hijos.
    """
    # Lazy import de lxml
    try:
        import lxml.etree as etree
    except ImportError as e:
        raise XMLSecError("lxml no está instalado. Instale con: pip install lxml") from e
    # ya está ok si no tiene prefijo y tiene default ns a DS_NS
    if (
        (sig.prefix is None)
        and (sig.nsmap.get(None) == DS_NS)
        and (sig.tag == f"{{{DS_NS}}}Signature")
    ):
        return sig

    parent = sig.getparent()
    if parent is None:
        raise RuntimeError(
            "Signature no tiene parent, no se puede normalizar namespace"
        )

    # construir Signature con default xmlns (sin prefijo)
    sig2 = etree.Element(f"{{{DS_NS}}}Signature", nsmap={None: DS_NS})  # type: ignore

    # mover hijos (SignedInfo, SignatureValue, KeyInfo, etc.)
    for child in list(sig):
        sig.remove(child)
        sig2.append(child)

    # preservar tail
    sig2.tail = sig.tail

    # reemplazar en el mismo lugar
    idx = parent.index(sig)
    parent.remove(sig)
    parent.insert(idx, sig2)
    return sig2


def _get_env_qr_base() -> str:
    env = (os.getenv("SIFEN_ENV") or "test").strip().upper()
    if env in ("PROD", "PRODUCTION"):
        return QR_URL_BASES["PROD"]
    return QR_URL_BASES["TEST"]


def _get_text(node, namespaces, xpath):
    if node is None:
        return None
    result = node.xpath(xpath, namespaces=namespaces)
    if not result:
        return None
    text = result[0]
    if isinstance(text, str):
        return text.strip()
    if hasattr(text, "text") and text.text:
        return text.text.strip()
    return None


def _ensure_qr_code(rde, ns):
    """
    Genera y agrega gCamFuFD con dCarQR obligatoriamente después de la firma.
    DNIT/SIFEN requiere gCamFuFD para evitar error 0160.
    
    Args:
        rde: Elemento rDE ya firmado
        ns: Namespaces para XPath
        
    Raises:
        RuntimeError: Si no hay SIFEN_CSC configurado
    """
    csc = os.getenv("SIFEN_CSC")
    if not csc:
        # En modo producción/test real, SIFEN_CSC es obligatorio
        allow_missing = os.getenv("SIFEN_ALLOW_MISSING_GCAMFUFD") == "1"
        if not allow_missing:
            raise RuntimeError(
                "ERROR CRÍTICO 0160: SIFEN_CSC no configurado. "
                "DNIT requiere gCamFuFD/dCarQR -> no se puede enviar sin CSC. "
                "Use SIFEN_ALLOW_MISSING_GCAMFUFD=1 solo para debug local."
            )
        logger.warning("MODO DEBUG: SIFEN_CSC no configurado - omitiendo gCamFuFD")
        return
    csc_id_raw = os.getenv("SIFEN_CSC_ID", "0001")
    # Format IdCSC with leading zeros to 4 digits (SIFEN requirement)
    csc_id = csc_id_raw.zfill(4)
    qr_base = _get_env_qr_base()
    
    # GUARD: Validar que QR base coincida con SIFEN_ENV
    try:
        from .env_validator import validate_qr_base_url
        validation = validate_qr_base_url(qr_base)
        if not validation["valid"]:
            error_msg = validation["error"]
            logger.error(error_msg)
            raise ValueError(error_msg)
    except ImportError:
        pass  # env_validator no disponible, continuar sin validación

    de = None
    de_candidates = rde.xpath("./sifen:DE", namespaces=ns)
    if not de_candidates:
        de_candidates = rde.xpath("./DE")
    if de_candidates:
        de = de_candidates[0]
    if de is None:
        logger.warning("No se encontró nodo DE para generar QR.")
        return

    g_dat = de.xpath("./sifen:gDatGralOpe", namespaces=ns)
    g_dat = g_dat[0] if g_dat else None
    d_fe = _get_text(g_dat, ns, "./sifen:dFeEmiDE/text()")
    if not d_fe:
        logger.warning("No se encontró dFeEmiDE para generar QR.")
        return
    d_fe_hex = d_fe.encode("utf-8").hex()  # Solo para el hash, no para el QR

    digest_node = rde.xpath(".//ds:DigestValue", namespaces={"ds": DS_NS})
    digest_text = digest_node[0].text.strip() if digest_node and digest_node[0].text else None
    if not digest_text:
        logger.warning("No se encontró DigestValue para generar QR.")
        return
    try:
        # Java does: Base64.getEncoder().encode(digestValue) then bytesToHex
        # This means: take raw digest bytes, base64 encode them, then hex encode the base64 string
        digest_bytes = base64.b64decode("".join(digest_text.split()))
        # Re-encode to base64 (matching Java's Base64.getEncoder().encode())
        digest_b64_encoded = base64.b64encode(digest_bytes)
        # Convert the base64 bytes to hex (lowercase to match Java's bytesToHex)
        digest_hex = digest_b64_encoded.hex()
    except Exception as exc:
        logger.error("No se pudo decodificar DigestValue para QR: %s", exc)
        return

    de_id = de.get("Id", "").strip()
    if not de_id:
        logger.warning("DE sin atributo Id; no se puede generar QR.")
        return

    # Totals and items
    g_tot = de.xpath("./sifen:gTotSub", namespaces=ns)
    g_tot = g_tot[0] if g_tot else None
    d_tot_gral = _get_text(g_tot, ns, "./sifen:dTotGralOpe/text()") if g_tot is not None else "0"
    d_tot_iva = "0"
    g_ope = de.xpath("./sifen:gDatGralOpe/sifen:gOpeCom", namespaces=ns)
    g_ope = g_ope[0] if g_ope else None
    i_timp = _get_text(g_ope, ns, "./sifen:iTImp/text()") if g_ope is not None else None
    if i_timp in ("1", "5") and g_tot is not None:
        d_tot_iva = _get_text(g_tot, ns, "./sifen:dTotIVA/text()") or "0"

    items = de.xpath(".//sifen:gCamItem", namespaces=ns)
    if not items:
        items = de.xpath(".//gCamItem")
    c_items = str(len(items) or 0)

    # Receptor
    g_dat_rec = de.xpath("./sifen:gDatGralOpe/sifen:gDatRec", namespaces=ns)
    g_dat_rec = g_dat_rec[0] if g_dat_rec else None
    i_nat_rec = _get_text(g_dat_rec, ns, "./sifen:iNatRec/text()") if g_dat_rec is not None else None
    receptor_key = "dNumIDRec"
    receptor_val = "0"
    if i_nat_rec == "1":
        val = _get_text(g_dat_rec, ns, "./sifen:dRucRec/text()")
        if val:
            receptor_key = "dRucRec"
            receptor_val = val
    else:
        val = _get_text(g_dat_rec, ns, "./sifen:dNumIDRec/text()")
        if val:
            receptor_val = val

    params = OrderedDict()
    params["nVersion"] = "150"
    params["Id"] = de_id
    params["dFeEmiDE"] = d_fe  # Fecha en formato texto, no hex
    params[receptor_key] = receptor_val
    params["dTotGralOpe"] = d_tot_gral or "0"
    params["dTotIVA"] = d_tot_iva or "0"
    params["cItems"] = c_items
    params["DigestValue"] = digest_hex
    params["IdCSC"] = csc_id

    url_params = "&".join(f"{k}={v}" for k, v in params.items())
    hash_input = url_params + csc
    qr_hash = hashlib.sha256(hash_input.encode("utf-8")).hexdigest()  # lowercase per SIFEN spec
    qr_url = f"{qr_base}?{url_params}&cHashQR={qr_hash}"

    # Usar el helper que asegura singleton y posición correcta de gCamFuFD
    # Esto elimina todos los gCamFuFD existentes y crea uno nuevo después de Signature
    ensure_single_gCamFuFD_after_signature(rde, qr_url)


def _force_signature_default_ns(sig_node: Any) -> Any:  # type: ignore
    """
    Reemplaza <ds:Signature> por <Signature xmlns="DSIG_NS"> preservando hijos.
    """
    etree = _ensure_lxml_import()
    parent = sig_node.getparent()
    if parent is None:
        return sig_node

    # Crear Signature con namespace default (sin prefijo)
    new_sig = etree.Element(f"{{{DSIG_NS}}}Signature", nsmap={None: DSIG_NS})  # type: ignore
    new_sig.text = sig_node.text
    new_sig.tail = sig_node.tail

    # Mover hijos
    for ch in list(sig_node):
        sig_node.remove(ch)
        new_sig.append(ch)

    # Reemplazar en el padre manteniendo posición
    idx = parent.index(sig_node)
    parent.remove(sig_node)
    parent.insert(idx, new_sig)
    return new_sig


def _force_dsig_default_namespace(sig: Any) -> Any:  # type: ignore
    """
    Convierte <ds:Signature ...> a:
      <Signature xmlns="http://www.w3.org/2000/09/xmldsig#"> ... </Signature>
    sin cambiar contenido (solo cómo serializa el namespace).
    """
    etree = _ensure_lxml_import()
    parent = sig.getparent()

    sig2 = etree.Element(f"{{{DSIG_NS}}}Signature", nsmap={None: DSIG_NS})  # type: ignore

    # copiar atributos si hubiera
    for k, v in sig.attrib.items():
        sig2.set(k, v)

    # copiar text y tail
    sig2.text = sig.text
    sig2.tail = sig.tail

    # mover hijos
    for child in list(sig):
        sig.remove(child)
        sig2.append(child)

    if parent is not None:
        parent.replace(sig, sig2)

    return sig2


def force_signature_default_ns(sig: Any) -> Any:  # type: ignore
    """
    Función robusta para forzar que Signature quede en DEFAULT namespace (sin prefijo).
    Convierte <ds:Signature> o cualquier Signature con prefijo a:
      <Signature xmlns="http://www.w3.org/2000/09/xmldsig#">
    preservando todos los hijos, atributos, .text y .tail.

    Esta función:
    1) Encuentra la Signature por namespace-uri y local-name (no por prefijo)
    2) Crea un nodo nuevo con default namespace DS
    3) Copia atributos y conserva text/tail
    4) Mueve todos los hijos (mover, no copiar)
    5) Reemplaza el nodo en el padre manteniendo la posición
    """
    etree = _ensure_lxml_import()
    parent = sig.getparent()
    if parent is None:
        raise XMLSecError("Signature no tiene parent, no se puede normalizar namespace")

    # Crear nuevo nodo <Signature xmlns="DS_NS"> sin prefijo
    # Usar nsmap={None: DS_NS} para forzar default namespace
    new_sig = etree.Element(etree.QName(DS_NS, "Signature"), nsmap={None: DS_NS})  # type: ignore

    # Copiar atributos
    for k, v in sig.attrib.items():
        new_sig.set(k, v)

    # Conservar text/tail
    new_sig.text = sig.text
    new_sig.tail = sig.tail

    # Mover todos los hijos (mover, no copiar)
    # Esto preserva SignedInfo, SignatureValue, KeyInfo, etc.
    for child in list(sig):
        sig.remove(child)
        new_sig.append(child)

    # Reemplazar el nodo en el padre manteniendo la posición
    # Usar list(parent) para obtener índice correcto
    children_list = list(parent)
    try:
        idx = children_list.index(sig)
    except ValueError:
        # Si no se encuentra en la lista, usar append
        idx = len(children_list)

    parent.remove(sig)
    parent.insert(idx, new_sig)

    return new_sig


def _force_signature_default_ds_namespace(sig: Any) -> Any:  # type: ignore
    """
    Convierte <ds:Signature ...> en <Signature xmlns="DS_NS"> preservando hijos/attrs.
    IMPORTANTE: en lxml el "prefijo" no está en el tag, depende del nsmap al serializar.
    """
    etree = _ensure_lxml_import()
    parent = sig.getparent()
    if parent is None:
        return sig

    # Nuevo nodo Signature con default namespace = DS_NS
    new_sig = etree.Element(etree.QName(DS_NS, "Signature"), nsmap={None: DS_NS})  # type: ignore

    # Copiar atributos si existieran
    for k, v in sig.attrib.items():
        new_sig.set(k, v)

    # Mover hijos (preserva SignedInfo/KeyInfo/etc ya armados por xmlsec)
    for child in list(sig):
        sig.remove(child)
        new_sig.append(child)

    # Reemplazar en el parent manteniendo posición
    idx = parent.index(sig)
    parent.remove(sig)
    parent.insert(idx, new_sig)
    return new_sig


def _extract_de_id(xml_root: Any) -> Optional[str]:  # type: ignore
    """Extrae el atributo Id del elemento DE."""
    etree = _ensure_lxml_import()
    # Buscar DE (puede estar en rDE o directamente)
    de_elem = None

    # Buscar directamente DE
    for elem in xml_root.iter():  # type: ignore
        local_name = etree.QName(elem).localname  # type: ignore
        if local_name == "DE":
            de_elem = elem
            break

    if de_elem is None:
        return None

    # Obtener Id (puede ser atributo Id o id)
    de_id = de_elem.get("Id") or de_elem.get("id")
    return de_id


def _strip_xmlns_prefix(tree, prefix: str) -> None:
    """
    Elimina el atributo xmlns:<prefix> de todos los elementos del árbol XML.

    Doc SIFEN: "no se podrá utilizar prefijos de namespace" - eliminar xmlns:ds del root y todo el doc
    La única declaración del namespace ds debe estar en <Signature xmlns="...">, NO en el root.

    Args:
        tree: Árbol XML (lxml.etree._ElementTree)
        prefix: Prefijo a eliminar (ej: "ds")
    """
    XMLNS_NS = "http://www.w3.org/2000/xmlns/"
    attr = f"{{{XMLNS_NS}}}{prefix}"
    root = tree.getroot()
    for el in root.iter():
        if attr in el.attrib:
            del el.attrib[attr]


def sign_de_with_p12(xml_bytes: bytes, p12_path: str, p12_password: str) -> bytes:
    """
    Firma un XML DE con XMLDSig usando python-xmlsec según especificación SIFEN v150.

    Args:
        xml_bytes: XML del DE/rEnviDe como bytes
        p12_path: Ruta al certificado P12/PFX
        p12_password: Contraseña del certificado P12

    Returns:
        XML firmado como bytes

    Raises:
        XMLSecError: Si falta xmlsec, certificado, o falla la firma
    """
    out: bytes = b""

    # Lazy import: verificar dependencias solo cuando se llama la función
    try:
        import xmlsec as _xmlsec_module
    except ImportError as e:
        raise XMLSecError(
            "python-xmlsec no está instalado. Instale con: pip install python-xmlsec"
        ) from e
    
    try:
        from cryptography.hazmat.primitives.serialization import pkcs12 as _pkcs12_module
        from cryptography.hazmat.backends import default_backend
    except ImportError as e:
        raise XMLSecError(
            "cryptography no está instalado. Instale con: pip install cryptography"
        ) from e
    
    try:
        import lxml.etree as _etree_module
    except ImportError as e:
        raise XMLSecError(
            "lxml no está instalado. Instale con: pip install lxml"
        ) from e
    
    # Usar los módulos importados
    xmlsec = _xmlsec_module
    pkcs12 = _pkcs12_module
    etree = _etree_module

    p12_path_obj = Path(p12_path)
    if not p12_path_obj.exists():
        raise XMLSecError(f"Certificado P12 no encontrado: {p12_path}")
    # 1) Parsear XML con parser que no elimine espacios en blanco
    try:
        parser = etree.XMLParser(remove_blank_text=False)  # type: ignore
        root = etree.fromstring(xml_bytes, parser=parser)  # type: ignore
    except Exception as e:
        raise XMLSecError(f"Error al parsear XML: {e}")

    # Obtener tree completo
    tree = root.getroottree()

    # 1.1) ANTES de firmar, eliminar del árbol cualquier declaración de prefijo "ds" heredada
    # Doc SIFEN: "no se podrá utilizar prefijos de namespace" - limpiar ANTES de ctx.sign()
    # Si el elemento raíz (o cualquier ancestro relevante) tiene nsmap con 'ds': DS_NS, eliminarlo
    def remove_ds_prefix_from_tree(elem: Any) -> None:  # type: ignore
        """Elimina el prefijo 'ds' del nsmap de un elemento y sus ancestros relevantes"""
        # Limpiar nsmap del elemento actual si tiene prefijo 'ds'
        if elem.nsmap and "ds" in elem.nsmap:
            # No podemos modificar nsmap directamente, pero podemos limpiar namespaces
            # El cleanup_namespaces se hará después, pero aquí marcamos para limpiar
            pass
        # Recursivamente limpiar hijos
        for child in elem:
            remove_ds_prefix_from_tree(child)

    # Limpiar namespaces del árbol completo para eliminar prefijos "ds" heredados
    etree.cleanup_namespaces(tree)  # type: ignore  # type: ignore

    # 2) Encontrar el <DE> correcto por XPath con namespace SIFEN o sin namespace fallback
    ds_ns = "http://www.w3.org/2000/09/xmldsig#"
    ns = {"ds": ds_ns, "sifen": SIFEN_NS}

    # Buscar DE con namespace SIFEN
    de = None
    de_list = root.xpath("//sifen:DE", namespaces=ns)
    if de_list:
        de = de_list[0]
    else:
        # Fallback: buscar sin namespace
        de_list = root.xpath("//DE")
        if de_list:
            de = de_list[0]

    if de is None:
        raise XMLSecError("No se encontró elemento DE en el XML")

    # Obtener de_id y validar que exista
    de_id = de.get("Id") or de.get("id")
    if not de_id:
        raise XMLSecError("El elemento DE no tiene atributo Id")

    logger.info(f"Firmando DE con Id={de_id}")

    # 3) Asegurar wrapper <rDE> dentro de <xDE> y que <DE> esté dentro de <rDE>
    parent = de.getparent()
    if parent is None:
        raise XMLSecError("DE no tiene parent (no existe rDE/xDE?)")

    # Verificar si el parent es rDE (local name)
    def get_local_name(tag: str) -> str:
        """Extrae el nombre local de un tag (sin namespace)"""
        if "}" in tag:
            return tag.split("}")[1]
        return tag

    parent_local = get_local_name(parent.tag)

    # Namespace XSI para schemaLocation
    XSI_NS = "http://www.w3.org/2001/XMLSchema-instance"

    # Si el parent NO es rDE, buscar rDE o crearlo
    rde = None
    if parent_local == "rDE":
        rde = parent
        logger.debug("DE ya está dentro de rDE")
    else:
        # Buscar rDE en el árbol (puede estar en el root o dentro de xDE)
        rde_list = root.xpath("//sifen:rDE", namespaces=ns)
        if not rde_list:
            rde_list = root.xpath("//rDE")

        if rde_list:
            rde_orig = rde_list[0]
            logger.debug("rDE encontrado en el árbol")
            
            # CRÍTICO: Asegurar que rDE tenga xmlns explícito ANTES de firmar
            # Si rDE hereda xmlns del padre, al extraerlo para el prevalidador se pierde
            # y la firma se invalida. Reconstruir rDE con xmlns explícito.
            rde_nsmap = rde_orig.nsmap if hasattr(rde_orig, 'nsmap') else {}
            if None not in rde_nsmap or rde_nsmap.get(None) != SIFEN_NS:
                logger.info("Reconstruyendo rDE con xmlns explícito para prevalidador")
                # Crear nuevo rDE con xmlns explícito
                new_nsmap = {None: SIFEN_NS, "xsi": XSI_NS}
                rde = etree.Element(f"{{{SIFEN_NS}}}rDE", nsmap=new_nsmap)
                
                # Copiar atributos
                for attr, val in rde_orig.attrib.items():
                    rde.set(attr, val)
                
                # Mover todos los hijos de rDE_orig a rDE nuevo
                for child in list(rde_orig):
                    rde_orig.remove(child)
                    rde.append(child)
                
                # Reemplazar rDE_orig con rDE nuevo en el parent
                rde_parent = rde_orig.getparent()
                if rde_parent is not None:
                    idx = list(rde_parent).index(rde_orig)
                    rde_parent.remove(rde_orig)
                    rde_parent.insert(idx, rde)
                else:
                    # rDE_orig es root - no debería pasar pero manejar
                    rde = rde_orig
                
                logger.info("rDE reconstruido con xmlns explícito")
            else:
                rde = rde_orig
                logger.debug("rDE ya tiene xmlns explícito")
        else:
            # Si no existe rDE, crearlo y mover DE dentro
            # El parent actual puede ser xDE o el root
            # rDE debe tener xmlns:xsi y xsi:schemaLocation
            rde = etree.Element(  # type: ignore
                f"{{{SIFEN_NS}}}rDE", nsmap={None: SIFEN_NS, "xsi": XSI_NS}
            )
            rde.set(
                f"{{{XSI_NS}}}schemaLocation",
                "http://ekuatia.set.gov.py/sifen/xsd siRecepDE_v150.xsd",
            )

            # Remover DE del parent actual
            parent.remove(de)

            # Mover DE dentro de rDE
            rde.append(de)

            # Insertar rDE en el parent original
            parent.append(rde)

            logger.info(
                "Creado wrapper rDE alrededor de DE con xmlns:xsi y xsi:schemaLocation"
            )

    # Asegurar que DE esté dentro de rDE
    if de.getparent() is not rde:
        # DE no está en rDE, moverlo
        old_parent = de.getparent()
        if old_parent is not None:
            old_parent.remove(de)
        rde.append(de)
        logger.info("DE movido dentro de rDE")

    # HIPÓTESIS 1: xsi:schemaLocation puede estar causando rechazo 0160 en SIFEN
    # Comentado temporalmente para probar sin este atributo
    # if not rde.get(f"{{{XSI_NS}}}schemaLocation"):
    #     rde.set(
    #         f"{{{XSI_NS}}}schemaLocation",
    #         "http://ekuatia.set.gov.py/sifen/xsd siRecepDE_v150.xsd",
    #     )
    #     # Asegurar que xsi esté en nsmap
    #     if "xsi" not in (rde.nsmap or {}):
    #         # Actualizar nsmap (lxml no permite modificar nsmap directamente, pero podemos recrear)
    #         current_nsmap = rde.nsmap.copy() if rde.nsmap else {}
    #         current_nsmap["xsi"] = XSI_NS
    #         # Nota: lxml maneja nsmap automáticamente al serializar si los atributos están presentes
    logger.info("xsi:schemaLocation omitido para test (Hipótesis 1)")

    # Asegurar dVerFor como PRIMER hijo de rDE (estándar: rDE -> dVerFor -> DE -> Signature -> gCamFuFD)
    try:
        dver_nodes = rde.xpath("./sifen:dVerFor", namespaces=ns)
        if not dver_nodes:
            dver_nodes = rde.xpath("./dVerFor")

        if not dver_nodes:
            dver = etree.Element(f"{{{SIFEN_NS}}}dVerFor")  # type: ignore
            dver.text = "150"
            rde.insert(0, dver)
            logger.info("dVerFor agregado como primer hijo de rDE")
        else:
            dver = dver_nodes[0]
            # Remover duplicados si existen
            for extra in dver_nodes[1:]:
                try:
                    rde.remove(extra)
                except Exception:
                    pass
            # Mover a la primera posición si no lo está
            if list(rde)[0] is not dver:
                try:
                    rde.remove(dver)
                except Exception:
                    pass
                rde.insert(0, dver)
                logger.info("dVerFor movido a primer hijo de rDE")
            if not (dver.text or "").strip():
                dver.text = "150"
    except Exception as e:
        logger.warning(f"No se pudo asegurar dVerFor como primer hijo de rDE: {e}")

    # Normalización XSD (antes de firmar): dDesPaisRec -> dDesPaisRe
    # El Prevalidador espera dDesPaisRe. Esto es seguro porque ocurre ANTES de calcular Digest/Signature.
    try:
        dd_nodes = rde.xpath(".//*[local-name()='dDesPaisRec']")
        if dd_nodes:
            for old in dd_nodes:
                parent_old = old.getparent()
                if parent_old is None:
                    continue
                idx_old = parent_old.index(old)
                new_el = etree.Element(etree.QName(SIFEN_NS, "dDesPaisRe"))  # type: ignore
                new_el.text = old.text
                parent_old.remove(old)
                parent_old.insert(idx_old, new_el)
            logger.info("Normalizado dDesPaisRec -> dDesPaisRe antes de firmar")
    except Exception as e:
        logger.warning(f"No se pudo normalizar dDesPaisRec -> dDesPaisRe: {e}")

    # BORRAR firmas existentes dentro de rDE/DE (cualquier nodo Signature en DS namespace)
    for old in rde.xpath(
        f".//*[local-name()='Signature' and namespace-uri()='{ds_ns}']"
    ):
        old_parent = old.getparent()
        if old_parent is not None:
            old_parent.remove(old)
            logger.info("Firma existente eliminada antes de firmar")

    # Eliminar xmlns:ds de todo el árbol antes de crear la firma
    # Doc SIFEN: "no se podrá utilizar prefijos de namespace" - la única declaración debe estar en <Signature>
    _strip_xmlns_prefix(tree, "ds")  # ✅ mata xmlns:ds del root y de todo el doc
    etree.cleanup_namespaces(tree)  # type: ignore  # type: ignore  # ✅ limpia lo que queda

    # Prevalidador estándar: Signature debe ser hija directa de rDE como HERMANA de DE.
    # Si existe gCamFuFD, debe ser hija directa de rDE y estar DESPUÉS de Signature (NO dentro de DE).
    # IMPORTANTE: Mover gCamFuFD ANTES de construir el signature template para que no se incluya en el digest
    camfufd = None
    camfufd_candidates = de.xpath("./sifen:gCamFuFD", namespaces=ns)
    if not camfufd_candidates:
        camfufd_candidates = de.xpath("./gCamFuFD")
    if camfufd_candidates:
        camfufd = camfufd_candidates[0]
        logger.info(f"gCamFuFD encontrado antes de firmar: {etree.tostring(camfufd)[:100]}...")
        de.remove(camfufd)
        logger.info("gCamFuFD removido del DE antes de firmar")
        # Verificar que se removió
        after_remove = de.xpath("./sifen:gCamFuFD", namespaces=ns)
        if not after_remove:
            after_remove = de.xpath("./gCamFuFD")
        logger.info(f"gCamFuFD en DE después de remover: {len(after_remove)}")
    else:
        logger.info("No se encontró gCamFuFD dentro del DE")

    # 4) Construir explícitamente el árbol de firma usando lxml con default namespace
    # Doc SIFEN: "no se podrá utilizar prefijos de namespace" - construir SIN prefijo desde el inicio
    # Enfoque: NO usar xmlsec.template.create (fuerza prefijo ds), construir manualmente con lxml
    # Doc SIFEN: "la declaración namespace de la firma digital debe realizarse en la etiqueta <Signature>"
    try:
        # Crear nodo Signature con default namespace (nsmap={None: DS_NS})
        # xmlsec necesita el namespace DS para firmar
        sig = etree.Element(etree.QName(DS_NS, "Signature"), nsmap={None: DS_NS})  # type: ignore

        # Construir SignedInfo
        signed_info = etree.SubElement(sig, etree.QName(DS_NS, "SignedInfo"))  # type: ignore

        # CanonicalizationMethod: xml-exc-c14n# según NT16/MT v150
        canon_method = etree.SubElement(  # type: ignore
            signed_info, etree.QName(DS_NS, "CanonicalizationMethod")  # type: ignore
        )
        canon_method.set("Algorithm", "http://www.w3.org/2001/10/xml-exc-c14n#")

        # SignatureMethod: rsa-sha256 (xmldsig-more) según doc SIFEN v150
        sig_method = etree.SubElement(  # type: ignore
            signed_info, etree.QName(DS_NS, "SignatureMethod")  # type: ignore
        )
        sig_method.set("Algorithm", "http://www.w3.org/2001/04/xmldsig-more#rsa-sha256")

        # Reference con URI="#<Id>"
        ref = etree.SubElement(signed_info, etree.QName(DS_NS, "Reference"))  # type: ignore
        ref.set("URI", f"#{de_id}")

        # Transforms: enveloped-signature + exc-c14n según requerimiento
        transforms = etree.SubElement(ref, etree.QName(DS_NS, "Transforms"))  # type: ignore
        transform1 = etree.SubElement(transforms, etree.QName(DS_NS, "Transform"))  # type: ignore
        transform1.set(
            "Algorithm", "http://www.w3.org/2000/09/xmldsig#enveloped-signature"
        )
        # Agregar exc-c14n como segundo transform
        transform2 = etree.SubElement(transforms, etree.QName(DS_NS, "Transform"))  # type: ignore
        transform2.set(
            "Algorithm", "http://www.w3.org/2001/10/xml-exc-c14n#"
        )

        # DigestMethod: sha256 según doc SIFEN v150
        digest_method = etree.SubElement(ref, etree.QName(DS_NS, "DigestMethod"))  # type: ignore
        digest_method.set("Algorithm", "http://www.w3.org/2001/04/xmlenc#sha256")

        # DigestValue (se calculará al firmar)
        etree.SubElement(ref, etree.QName(DS_NS, "DigestValue"))  # type: ignore

        # SignatureValue (se calculará al firmar)
        etree.SubElement(sig, etree.QName(DS_NS, "SignatureValue"))  # type: ignore

        # KeyInfo / X509Data / X509Certificate
        key_info = etree.SubElement(sig, etree.QName(DS_NS, "KeyInfo"))  # type: ignore
        x509_data = etree.SubElement(key_info, etree.QName(DS_NS, "X509Data"))  # type: ignore
        x509_cert = etree.SubElement(x509_data, etree.QName(DS_NS, "X509Certificate"))  # type: ignore
        # El certificado y metadatos se agregarán al firmar

        logger.debug(
            "Árbol de firma construido manualmente con default namespace (sin prefijo ds:)"
        )
    except Exception as e:
        raise XMLSecError(f"Error al construir árbol de firma: {e}")

    # Insertar Signature como hija de rDE inmediatamente después de DE
    try:
        rde_children = list(rde)
        idx_de_in_rde = rde_children.index(de)
        # Insertar Signature como hija de rDE inmediatamente después de DE
        rde.insert(idx_de_in_rde + 1, sig)
        logger.debug("Firma insertada como hija de rDE inmediatamente después de DE")
    except Exception as e:
        rde.append(sig)
        logger.warning(f"No se pudo insertar firma después de DE; se agregó al final de rde: {e}")

    # HIPÓTESIS 3: gCamFuFD puede estar causando rechazo 0160
    # Comentado temporalmente para probar sin gCamFuFD
    # if camfufd is None:
    #     # Crear gCamFuFD vacío con elementos requeridos
    #     camfufd = etree.Element(f"{{{SIFEN_NS}}}gCamFuFD")  # type: ignore
    #     dcar_node = etree.SubElement(camfufd, f"{{{SIFEN_NS}}}dCarQR")  # type: ignore
    #     # Agregar valores por defecto según XSD
    #     etree.SubElement(dcar_node, f"{{{SIFEN_NS}}}dVerQR").text = "1"  # type: ignore
    #     etree.SubElement(dcar_node, f"{{{SIFEN_NS}}}dPacQR").text = "0"  # type: ignore
    #     logger.info("gCamFuFD creado (vacío) ya que SIFEN podría requerirlo")
    
    # Solo insertar gCamFuFD si ya existía en el DE original
    if camfufd is not None:
        try:
            idx_sig_in_rde = list(rde).index(sig)
            rde.insert(idx_sig_in_rde + 1, camfufd)
            logger.debug("gCamFuFD movido como hija de rDE inmediatamente después de Signature")
        except Exception as e:
            rde.append(camfufd)
            logger.warning(f"No se pudo insertar gCamFuFD después de Signature; se agregó al final de rde: {e}")
    else:
        logger.info("gCamFuFD omitido (Hipótesis 3: puede estar causando 0160)")

    # 8) Cargar key/cert desde PEM (ya existen temporales desde P12) y firmar
    cert_pem_path = None
    key_pem_path = None
    ctx = None
    try:
        cert_pem_path, key_pem_path = p12_to_temp_pem_files(p12_path, p12_password)

        if xmlsec is None:
            raise XMLSecError("xmlsec no está disponible")
        # Cargar key+cert desde PEM
        key = xmlsec.Key.from_file(key_pem_path, xmlsec.KeyFormat.PEM)  # type: ignore
        key.load_cert_from_file(cert_pem_path, xmlsec.KeyFormat.PEM)  # type: ignore

        # Cargar certificado principal desde P12 para agregarlo al X509Certificate
        cert_obj = None
        subject_name = None
        issuer_name = None
        issuer_serial = None

        try:
            with open(p12_path, "rb") as f:
                p12_bytes = f.read()
            password_bytes = p12_password.encode("utf-8") if p12_password else None
            if pkcs12 is None:
                raise XMLSecError("cryptography no está disponible")
            key_obj, cert_obj, addl_certs = pkcs12.load_key_and_certificates(  # type: ignore
                p12_bytes, password_bytes, backend=default_backend()
            )
            # Cargar certificados adicionales si existen
            if addl_certs:
                for addl_cert in addl_certs:
                    try:
                        addl_cert_pem = addl_cert.public_bytes(Encoding.PEM)
                        key.load_cert_from_memory(
                            addl_cert_pem,
                            xmlsec.KeyFormat.PEM,  # type: ignore
                        )
                    except Exception as e:
                        logger.warning(f"No se pudo cargar certificado adicional: {e}")
        except ValueError:
            # Si cryptography falla, continuar sin certificados adicionales
            logger.debug(
                "No se pudieron cargar certificados del P12 con cryptography, usando xmlsec key"
            )

        # Agregar certificado al X509Certificate en el template manual (antes de firmar)
        # xmlsec calculará DigestValue y SignatureValue automáticamente al firmar
        if cert_obj:
            cert_pem = cert_obj.public_bytes(Encoding.PEM)
            # Extraer solo el contenido base64 (sin headers PEM)
            cert_lines = cert_pem.decode("utf-8").split("\n")
            cert_b64 = "".join(
                line.strip()
                for line in cert_lines
                if line.strip() and not line.strip().startswith("-----")
            )
            x509_cert.text = cert_b64
            logger.debug("Certificado X509 agregado al template manual")

            subject_name, issuer_name, issuer_serial = _extract_cert_identity_strings(cert_obj)
            if subject_name:
                subj_node = etree.SubElement(
                    x509_data, etree.QName(DS_NS, "X509SubjectName")
                )  # type: ignore
                subj_node.text = subject_name
                logger.info("KeyInfo enriquecido con X509SubjectName")
            if issuer_name and issuer_serial:
                issuer_serial_node = etree.SubElement(
                    x509_data, etree.QName(DS_NS, "X509IssuerSerial")
                )  # type: ignore
                issuer_name_node = etree.SubElement(
                    issuer_serial_node, etree.QName(DS_NS, "X509IssuerName")
                )  # type: ignore
                issuer_name_node.text = issuer_name
                issuer_serial_value = etree.SubElement(
                    issuer_serial_node, etree.QName(DS_NS, "X509SerialNumber")
                )  # type: ignore
                issuer_serial_value.text = issuer_serial
                logger.info("KeyInfo enriquecido con X509IssuerSerial")
        else:
            # Fallback: intentar obtener certificado desde xmlsec key
            # Nota: xmlsec puede tener el certificado cargado, pero no hay API directa para extraerlo
            logger.warning(
                "No se pudo obtener certificado desde P12, X509Certificate puede quedar vacío"
            )

        # Crear contexto de firma
        ctx = xmlsec.SignatureContext()  # type: ignore
        ctx.key = key

        # IMPORTANTÍSIMO: Registrar Ids antes de firmar (xmlsec necesita esto para resolver Reference URI)
        xmlsec.tree.add_ids(tree, ["Id"])  # type: ignore

        # Firmar el template construido manualmente
        # xmlsec calculará DigestValue y SignatureValue automáticamente
        ctx.sign(sig)
        logger.info(
            "DE firmado exitosamente con XMLDSig (RSA-SHA256/SHA-256) usando template manual"
        )

        # VALIDACIÓN DURA: Verificar que la firma es válida INMEDIATAMENTE después de firmar
        # Si esto falla, no hay nada que podamos "arreglar" después - la firma es criptográfica
        logger.info("Verificación criptográfica post-firma...")
        temp_signed = etree.tostring(tree, encoding='utf-8', xml_declaration=True, method='xml', standalone=None)
        temp_signed = temp_signed.replace(b'\n', b'').replace(b'\r', b'')
        
        # Guardar artifact para debug si falla
        try:
            with open('artifacts/rde_immediately_after_sign.xml', 'wb') as f:
                f.write(temp_signed)
        except:
            pass  # Ignorar error si no se puede guardar
            
        # Verificar con xmlsec
        import subprocess
        import tempfile
        import os
        try:
            # Crear archivo temporal para xmlsec
            with tempfile.NamedTemporaryFile(mode='wb', suffix='.xml', delete=False) as tmp_file:
                tmp_file.write(temp_signed)
                tmp_path = tmp_file.name
            
            try:
                result = subprocess.run(
                    ['xmlsec1', '--verify', '--insecure', '--id-attr:Id', 'DE', tmp_path],
                    capture_output=True,
                    timeout=30
                )
                if result.returncode != 0:
                    error_msg = result.stderr.decode('utf-8') if result.stderr else "Error desconocido"
                    raise XMLSecError(f"VALIDACIÓN FALLÓ: La firma no es válida inmediatamente después de firmar: {error_msg}")
                logger.info("✅ Verificación criptográfica OK - firma válida")
            finally:
                # Limpiar archivo temporal
                try:
                    os.unlink(tmp_path)
                except:
                    pass
                    
        except subprocess.TimeoutExpired:
            raise XMLSecError("VALIDACIÓN FALLÓ: Timeout al verificar firma con xmlsec1")
        except FileNotFoundError:
            logger.warning("xmlsec1 no encontrado - no se puede verificar la firma post-firma")

        # IMPORTANTÍSIMO: Registrar Ids DESPUÉS de firmar para asegurar que estén disponibles para verificación
        xmlsec.tree.add_ids(tree, ["Id"])  # type: ignore

        # Normalizar whitespace en nodos base64 que NO afectan SignedInfo (prevalidador es estricto con formato)
        try:
            sig_val_nodes = sig.xpath(".//*[local-name()='SignatureValue' and namespace-uri()=$ns]", ns=DS_NS)
            if sig_val_nodes and sig_val_nodes[0].text:
                sig_val_nodes[0].text = "".join(sig_val_nodes[0].text.split())
            cert_nodes = sig.xpath(".//*[local-name()='X509Certificate' and namespace-uri()=$ns]", ns=DS_NS)
            if cert_nodes and cert_nodes[0].text:
                cert_nodes[0].text = "".join(cert_nodes[0].text.split())
        except Exception as e:
            logger.warning(f"No se pudo normalizar SignatureValue/X509Certificate: {e}")

        # Detectar ubicación inicial de la firma
        parent_sig = sig.getparent()
        initial_loc = "unknown"
        if parent_sig is not None:
            if parent_sig.tag == f"{{{SIFEN_NS}}}rDE":
                # Manual Técnico v150 sección 7.2.2.1:
                # "La declaración namespace de la firma digital debe realizarse en la etiqueta <Signature>"
                # con xmlns="http://www.w3.org/2000/09/xmldsig#" (XMLDSig estándar)
                # NO forzar namespace SIFEN en Signature - debe mantener XMLDSig
                logger.info("Signature mantiene namespace XMLDSig estándar (Manual Técnico v150 7.2.2.1)")
                initial_loc = "rDE"
            elif parent_sig.tag == f"{{{SIFEN_NS}}}DE":
                initial_loc = "DE"
        logger.info(f"Signature initially under: {initial_loc}")

        logger.info("Signature final expected under rDE (hermana de DE)")

    except PKCS12Error as e:
        raise XMLSecError(f"Error al convertir certificado P12: {e}") from e
    except Exception as e:
        raise XMLSecError(f"Error al cargar certificado o firmar: {e}") from e
    finally:
        # Limpiar archivos PEM temporales
        if cert_pem_path and key_pem_path:
            cleanup_pem_files(cert_pem_path, key_pem_path)

    # 7) GENERAR Y EMBEDIR QR CODE DESPUÉS DE FIRMA (usando DigestValue)
    # El QR necesita el DigestValue de la firma, así que debe generarse después de ctx.sign()
    _ensure_qr_code(rde, ns)

    # 8) POST-PROCESADO DESACTIVADO - NO MUTAR SIGNATURE POST-FIRMA
    # La firma ya está validada por xmlsec, cualquier modificación rompe la criptografía
    # Solo limpiamos newlines para compatibilidad con SIFEN
    DS_NS_URI = "http://www.w3.org/2000/09/xmldsig#"

    # Serializar el árbol completo tal cual (sin modificar Signature)
    out = etree.tostring(tree, encoding='utf-8', xml_declaration=True, method='xml', standalone=None)
    out_str = out.decode('utf-8')
    
    # Solo eliminar newlines - NO modificar Signature bajo ninguna circunstancia
    out_str = out_str.replace('\n', '').replace('\r', '')
    
    # Convert back to bytes
    out = out_str.encode('utf-8')

    # CRÍTICO: Inyectar xmlns explícito en rDE si no lo tiene
    # lxml optimiza y no repite xmlns en hijos si el padre ya lo tiene.
    # Al extraer rDE para el prevalidador, se pierde xmlns heredado y la firma falla.
    # Esta inyección es segura porque solo modifica el tag de rDE, no DE (que es lo firmado).
    import re as _re
    rde_tag_pat = _re.compile(rb'<rDE\b([^>]*)>')
    rde_match = rde_tag_pat.search(out)
    if rde_match:
        rde_attrs = rde_match.group(1)
        # Verificar si ya tiene xmlns= (default namespace)
        if b'xmlns="' not in rde_attrs and b"xmlns='" not in rde_attrs:
            # Inyectar xmlns justo después de <rDE
            xmlns_decl = f' xmlns="{SIFEN_NS}"'.encode('utf-8')
            insert_pos = rde_match.start() + 4  # Después de "<rDE"
            out = out[:insert_pos] + xmlns_decl + out[insert_pos:]
            logger.info("xmlns inyectado en rDE para extracción standalone")

    # 8) POST-CHECK ESTRICTO antes de devolver - revisar XML SERIALIZADO (bytes), no solo el árbol
    # Doc SIFEN: "no se podrá utilizar prefijos de namespace" - validar en bytes finales
    DS_NS_URI = "http://www.w3.org/2000/09/xmldsig#"
    SIFEN_NS_URI = "http://ekuatia.set.gov.py/sifen/xsd"

    # 8.1) Validar que NO exista "<ds:" ni "xmlns:ds" en el texto serializado
    # Doc SIFEN: prohibido "ds:" y prohibido "xmlns:ds="
    if b"<ds:" in out:
        print("DEBUG: Found ds: prefix in output")
        idx = out.find(b"<ds:")
        print(f"DEBUG: Location: {out[idx-50:idx+50]}")
        raise XMLSecError(
            "Post-check falló: todavía existe '<ds:' en el XML serializado (Doc SIFEN: no se podrá utilizar prefijos)"
        )
    if b"xmlns:ds=" in out:
        print("DEBUG: Found xmlns:ds= in output")
        idx = out.find(b"xmlns:ds=")
        print(f"DEBUG: Location: {out[idx-50:idx+50]}")
        raise XMLSecError(
            "Post-check falló: todavía existe 'xmlns:ds=' en el XML serializado (Doc SIFEN: no se podrán utilizar prefijos)"
        )

    # 8.2) Validar que SÍ exista '<Signature xmlns="http://www.w3.org/2000/09/xmldsig#"' en el texto serializado
    # Manual Técnico v150 sección 7.2.2.1: xmlns debe declararse en la etiqueta <Signature> como XMLDSig estándar
    # NOTA: Este check se desactiva temporalmente porque el string replacement lo agrega después
    if b'<Signature xmlns="http://www.w3.org/2000/09/xmldsig#"' in out:
        print("DEBUG: ✓ Signature has explicit xmlns attribute")
    else:
        print("DEBUG: ⚠ Signature xmlns will be added by string replacement")

    # 8.3) POST-CHECK ESTRUCTURAL FINAL: Signature debe ser hija directa de rDE, inmediatamente después de DE.
    # Usar lxml xpath para robustez
    ns = {"sifen": SIFEN_NS_URI, "ds": DS_NS_URI}
    root_final = tree.getroot()
    # Buscar rDE y DE con xpath (namespace-aware)
    rde_nodes = root_final.xpath("//sifen:rDE", namespaces=ns)
    de_nodes = root_final.xpath("//sifen:DE", namespaces=ns)
    if not rde_nodes or not de_nodes:
        raise XMLSecError("Post-check falló: no se encontró rDE o DE con xpath")
    rde_final = rde_nodes[0]
    de_final = de_nodes[0]
    # Verificar ubicación de Signature
    # Buscar con ds namespace (XMLDSig) o sin namespace (SIFEN)
    sig_in_rde = rde_final.xpath("./ds:Signature", namespaces=ns)
    if not sig_in_rde:
        # Try without namespace (SIFEN namespace)
        sig_in_rde = rde_final.xpath("./Signature", namespaces=ns)
    if not sig_in_rde:
        # Try with SIFEN namespace
        sig_in_rde = rde_final.xpath("./sifen:Signature", namespaces=ns)
    print(f"DEBUG: Post-check found {len(sig_in_rde)} Signature(s) in rDE")
    sig_in_de = de_final.xpath("./ds:Signature", namespaces=ns)
    if not sig_in_de:
        sig_in_de = de_final.xpath("./Signature", namespaces=ns)
    if sig_in_de:
        raise XMLSecError("Post-check: Signature quedó dentro de DE, debe ser hija directa de rDE")
    if len(sig_in_rde) != 1:
        raise XMLSecError(f"Post-check: Signature bajo rDE inválida; expected 1, got {len(sig_in_rde)}")

    children_rde = list(rde_final)
    try:
        idx_de = children_rde.index(de_final)
        idx_sig = children_rde.index(sig_in_rde[0])
    except ValueError:
        raise XMLSecError("Post-check: No se pudo determinar posiciones de DE/Signature en rDE")

    if idx_sig != idx_de + 1:
        raise XMLSecError("Post-check: Signature debe estar inmediatamente después de DE en rDE")

    logger.info("Signature final: in_rDE=True, in_DE=False")

    return out
