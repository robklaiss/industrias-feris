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

import os
import re
import logging
import base64
from pathlib import Path
from typing import Optional
from lxml import etree

try:
    import xmlsec
    XMLSEC_AVAILABLE = True
except ImportError:
    XMLSEC_AVAILABLE = False
    xmlsec = None

try:
    from cryptography.hazmat.primitives.serialization import pkcs12, Encoding, PrivateFormat, NoEncryption
    from cryptography.hazmat.backends import default_backend
    CRYPTOGRAPHY_AVAILABLE = True
except ImportError:
    CRYPTOGRAPHY_AVAILABLE = False
    pkcs12 = None

from .pkcs12_utils import p12_to_temp_pem_files, cleanup_pem_files, PKCS12Error
from .exceptions import SifenClientError

logger = logging.getLogger(__name__)

# Namespaces
DS_NS = "http://www.w3.org/2000/09/xmldsig#"
DSIG_NS = "http://www.w3.org/2000/09/xmldsig#"  # Alias para claridad
SIFEN_NS = "http://ekuatia.set.gov.py/sifen/xsd"


class XMLSecError(SifenClientError):
    """Excepción para errores en firma XMLDSig con xmlsec"""
    pass


def _force_signature_default_namespace(sig: etree._Element) -> etree._Element:
    """
    Convierte <ds:Signature> o <Signature ns0:...> a:
      <Signature xmlns="http://www.w3.org/2000/09/xmldsig#"> ... </Signature>
    preservando todos los hijos.
    """
    # ya está ok si no tiene prefijo y tiene default ns a DS_NS
    if (sig.prefix is None) and (sig.nsmap.get(None) == DS_NS) and (sig.tag == f"{{{DS_NS}}}Signature"):
        return sig

    parent = sig.getparent()
    if parent is None:
        raise RuntimeError("Signature no tiene parent, no se puede normalizar namespace")

    # construir Signature con default xmlns (sin prefijo)
    sig2 = etree.Element(f"{{{DS_NS}}}Signature", nsmap={None: DS_NS})

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


def _force_signature_default_ns(sig_node: etree._Element) -> etree._Element:
    """
    Reemplaza <ds:Signature> por <Signature xmlns="DSIG_NS"> preservando hijos.
    """
    parent = sig_node.getparent()
    if parent is None:
        return sig_node

    # Crear Signature con namespace default (sin prefijo)
    new_sig = etree.Element(f"{{{DSIG_NS}}}Signature", nsmap={None: DSIG_NS})
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


def _force_dsig_default_namespace(sig: etree._Element) -> etree._Element:
    """
    Convierte <ds:Signature ...> a:
      <Signature xmlns="http://www.w3.org/2000/09/xmldsig#"> ... </Signature>
    sin cambiar contenido (solo cómo serializa el namespace).
    """
    parent = sig.getparent()

    sig2 = etree.Element(f"{{{DSIG_NS}}}Signature", nsmap={None: DSIG_NS})

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


def force_signature_default_ns(sig: etree._Element) -> etree._Element:
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
    parent = sig.getparent()
    if parent is None:
        raise XMLSecError("Signature no tiene parent, no se puede normalizar namespace")
    
    # Crear nuevo nodo <Signature xmlns="DS_NS"> sin prefijo
    # Usar nsmap={None: DS_NS} para forzar default namespace
    new_sig = etree.Element(etree.QName(DS_NS, "Signature"), nsmap={None: DS_NS})
    
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


def _force_signature_default_ds_namespace(sig: etree._Element) -> etree._Element:
    """
    Convierte <ds:Signature ...> en <Signature xmlns="DS_NS"> preservando hijos/attrs.
    IMPORTANTE: en lxml el "prefijo" no está en el tag, depende del nsmap al serializar.
    """
    parent = sig.getparent()
    if parent is None:
        return sig

    # Nuevo nodo Signature con default namespace = DS_NS
    new_sig = etree.Element(etree.QName(DS_NS, "Signature"), nsmap={None: DS_NS})

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


def _extract_de_id(xml_root: etree._Element) -> Optional[str]:
    """Extrae el atributo Id del elemento DE."""
    # Buscar DE (puede estar en rDE o directamente)
    de_elem = None
    
    # Buscar directamente DE
    for elem in xml_root.iter():
        local_name = etree.QName(elem).localname
        if local_name == "DE":
            de_elem = elem
            break
    
    if de_elem is None:
        return None
    
    # Obtener Id (puede ser atributo Id o id)
    de_id = de_elem.get("Id") or de_elem.get("id")
    return de_id


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
    if not XMLSEC_AVAILABLE:
        raise XMLSecError(
            "python-xmlsec no está instalado. Instale con: pip install python-xmlsec"
        )
    
    if not CRYPTOGRAPHY_AVAILABLE:
        raise XMLSecError(
            "cryptography no está instalado. Instale con: pip install cryptography"
        )
    
    p12_path_obj = Path(p12_path)
    if not p12_path_obj.exists():
        raise XMLSecError(f"Certificado P12 no encontrado: {p12_path}")
    
    # 1) Parsear XML con parser que no elimine espacios en blanco
    try:
        parser = etree.XMLParser(remove_blank_text=False)
        root = etree.fromstring(xml_bytes, parser=parser)
    except Exception as e:
        raise XMLSecError(f"Error al parsear XML: {e}")
    
    # Obtener tree completo
    tree = root.getroottree()
    
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
        if '}' in tag:
            return tag.split('}')[1]
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
            rde = rde_list[0]
            logger.debug("rDE encontrado en el árbol")
        else:
            # Si no existe rDE, crearlo y mover DE dentro
            # El parent actual puede ser xDE o el root
            # rDE debe tener xmlns:xsi y xsi:schemaLocation
            rde = etree.Element(
                f"{{{SIFEN_NS}}}rDE",
                nsmap={None: SIFEN_NS, "xsi": XSI_NS}
            )
            rde.set(f"{{{XSI_NS}}}schemaLocation", "http://ekuatia.set.gov.py/sifen/xsd siRecepDE_v150.xsd")
            
            # Remover DE del parent actual
            parent.remove(de)
            
            # Mover DE dentro de rDE
            rde.append(de)
            
            # Insertar rDE en el parent original
            parent.append(rde)
            
            logger.info("Creado wrapper rDE alrededor de DE con xmlns:xsi y xsi:schemaLocation")
    
    # Asegurar que DE esté dentro de rDE
    if de.getparent() is not rde:
        # DE no está en rDE, moverlo
        old_parent = de.getparent()
        if old_parent is not None:
            old_parent.remove(de)
        rde.append(de)
        logger.info("DE movido dentro de rDE")
    
    # Asegurar que rDE tenga xmlns:xsi y xsi:schemaLocation
    if not rde.get(f"{{{XSI_NS}}}schemaLocation"):
        rde.set(f"{{{XSI_NS}}}schemaLocation", "http://ekuatia.set.gov.py/sifen/xsd siRecepDE_v150.xsd")
        # Asegurar que xsi esté en nsmap
        if "xsi" not in (rde.nsmap or {}):
            # Actualizar nsmap (lxml no permite modificar nsmap directamente, pero podemos recrear)
            current_nsmap = rde.nsmap.copy() if rde.nsmap else {}
            current_nsmap["xsi"] = XSI_NS
            # Nota: lxml maneja nsmap automáticamente al serializar si los atributos están presentes
    
    # BORRAR firmas existentes dentro de rDE (cualquier nodo Signature en DS namespace)
    for old in rde.xpath(f".//*[local-name()='Signature' and namespace-uri()='{ds_ns}']"):
        old_parent = old.getparent()
        if old_parent is not None:
            old_parent.remove(old)
            logger.info("Firma existente eliminada antes de firmar")
    
    # Registrar el atributo Id como ID (IMPORTANTÍSIMO para Reference URI)
    xmlsec.tree.add_ids(tree, ["Id"])
    
    # 4) Crear la firma como hijo de rDE (parent) y luego insertarla inmediatamente después de DE
    # IMPORTANTE: NO usar ns="ds" en template.create. Queremos SIN prefijo.
    try:
        sig = xmlsec.template.create(
            rde,                         # node: rDE (padre) - la firma será hermano de DE
            xmlsec.Transform.C14N,       # C14N 1.0 (no EXCL_C14N para CanonicalizationMethod)
            xmlsec.Transform.RSA_SHA256, # RSA_SHA256
            ns=None                      # SIN prefijo (default namespace)
        )
    except Exception as e:
        raise XMLSecError(f"Error al crear plantilla de firma: {e}")
    
    # Insertar signature como hermano de DE dentro de rDE, justo después de </DE>
    # Remover sig del parent si ya está en algún lugar
    sig_parent = sig.getparent()
    if sig_parent is not None:
        sig_parent.remove(sig)
    
    # Encontrar índice de DE dentro de rDE e insertar después
    try:
        idx = list(rde).index(de)
        rde.insert(idx + 1, sig)
        logger.debug(f"Firma insertada como hermano de DE en rDE (índice {idx + 1})")
    except (ValueError, IndexError) as e:
        # Fallback: append al final de rDE
        rde.append(sig)
        logger.warning(f"No se pudo insertar firma después de DE, se agregó al final: {e}")
    
    # 5) Configurar template/refs/transforms con los URIs indicados (rsa-sha256/sha256 + enveloped + exc-c14n)
    try:
        ref = xmlsec.template.add_reference(sig, xmlsec.Transform.SHA256, uri=f"#{de_id}")
        xmlsec.template.add_transform(ref, xmlsec.Transform.ENVELOPED)
        xmlsec.template.add_transform(ref, xmlsec.Transform.EXCL_C14N)
        logger.debug(f"Reference agregada: URI=#{de_id}, SHA256, ENVELOPED+EXCL_C14N")
    except Exception as e:
        raise XMLSecError(f"Error al agregar referencia: {e}")
    
    # 7) KeyInfo / X509
    try:
        key_info = xmlsec.template.ensure_key_info(sig)  # sin ns kwarg
        x509 = xmlsec.template.add_x509_data(key_info)
        xmlsec.template.x509_data_add_certificate(x509)
        logger.debug("KeyInfo/X509Data agregado")
    except Exception as e:
        raise XMLSecError(f"Error al agregar KeyInfo/X509Data: {e}")
    
    # 8) Cargar key/cert desde PEM (ya existen temporales desde P12) y firmar
    cert_pem_path = None
    key_pem_path = None
    ctx = None
    try:
        cert_pem_path, key_pem_path = p12_to_temp_pem_files(p12_path, p12_password)
        
        # Cargar key+cert desde PEM
        key = xmlsec.Key.from_file(key_pem_path, xmlsec.KeyFormat.PEM)
        key.load_cert_from_file(cert_pem_path, xmlsec.KeyFormat.PEM)
        
        # Cargar certificados adicionales si existen en el P12
        try:
            with open(p12_path, "rb") as f:
                p12_bytes = f.read()
            password_bytes = p12_password.encode("utf-8") if p12_password else None
            key_obj, cert_obj, addl_certs = pkcs12.load_key_and_certificates(
                p12_bytes,
                password_bytes,
                backend=default_backend()
            )
            if addl_certs:
                from cryptography import x509
                for addl_cert in addl_certs:
                    try:
                        addl_cert_pem = addl_cert.public_bytes(Encoding.PEM)
                        key.load_cert_from_memory(
                            addl_cert_pem,
                            xmlsec.KeyFormat.PEM
                        )
                    except Exception as e:
                        logger.warning(f"No se pudo cargar certificado adicional: {e}")
        except ValueError:
            # Si cryptography falla, continuar sin certificados adicionales
            logger.debug("No se pudieron cargar certificados adicionales del P12")
        
        # Crear contexto de firma
        ctx = xmlsec.SignatureContext()
        ctx.key = key
        
        # IMPORTANTÍSIMO: Registrar Ids antes de firmar (ya lo hicimos arriba, pero asegurar)
        xmlsec.tree.add_ids(tree, ["Id"])
        
        # Firmar
        ctx.sign(sig)
        logger.info("DE firmado exitosamente con XMLDSig (RSA-SHA256/SHA-256)")
        
    except PKCS12Error as e:
        raise XMLSecError(f"Error al convertir certificado P12: {e}") from e
    except Exception as e:
        raise XMLSecError(f"Error al cargar certificado o firmar: {e}") from e
    finally:
        # Limpiar archivos PEM temporales
        if cert_pem_path and key_pem_path:
            cleanup_pem_files(cert_pem_path, key_pem_path)
    
    # 7) POST-PROCESADO para forzar default namespace y matar prefijos
    DS_NS_URI = "http://www.w3.org/2000/09/xmldsig#"
    
    # Limpiar namespaces primero
    etree.cleanup_namespaces(tree)
    
    # Buscar Signature firmada por namespace-uri y local-name (independiente del prefijo)
    sig_found = None
    # Buscar en rDE primero (donde debería estar)
    sig_candidates = rde.xpath(f'.//*[namespace-uri()="{DS_NS_URI}" and local-name()="Signature"]')
    if sig_candidates:
        sig_found = sig_candidates[0]
    else:
        # Fallback: buscar en todo el árbol
        sig_candidates = root.xpath(f'//*[namespace-uri()="{DS_NS_URI}" and local-name()="Signature"]')
        if sig_candidates:
            sig_found = sig_candidates[0]
    
    if sig_found is None:
        raise XMLSecError("Post-procesado falló: no se encontró Signature firmada después de ctx.sign()")
    
    # Serializar temporalmente para verificar si contiene "<ds:" o "xmlns:ds"
    temp_out = etree.tostring(tree, encoding="utf-8", xml_declaration=True)
    
    # Si el XML serializado contiene "<ds:" o "xmlns:ds", reconstruir el nodo Signature
    if b"<ds:" in temp_out or b'xmlns:ds=' in temp_out:
        logger.debug("Post-procesado: detectado prefijo ds: o xmlns:ds, reconstruyendo nodo Signature")
        # Reconstruir el nodo Signature usando default namespace
        parent_sig = sig_found.getparent()
        if parent_sig is None:
            raise XMLSecError("Post-procesado falló: Signature no tiene parent")
        
        # Crear nuevo nodo Signature con default namespace
        new_sig = etree.Element(etree.QName(DS_NS, "Signature"), nsmap={None: DS_NS})
        
        # Copiar atributos
        for k, v in sig_found.attrib.items():
            new_sig.set(k, v)
        
        # Conservar text/tail
        new_sig.text = sig_found.text
        new_sig.tail = sig_found.tail
        
        # Mover hijos (mover, no copiar)
        for child in list(sig_found):
            sig_found.remove(child)
            new_sig.append(child)
        
        # Reemplazar en el parent misma posición
        idx = list(parent_sig).index(sig_found)
        parent_sig.remove(sig_found)
        parent_sig.insert(idx, new_sig)
        
        sig_found = new_sig
    
    # Limpiar namespaces otra vez después de reconstruir
    etree.cleanup_namespaces(tree)
    
    # Serializar el documento COMPLETO
    try:
        out = etree.tostring(tree, encoding="utf-8", xml_declaration=True)
    except Exception as e:
        raise XMLSecError(f"Error al serializar XML firmado: {e}") from e
    
    # 8) POST-CHECK ESTRICTO antes de devolver
    DS_NS_URI = "http://www.w3.org/2000/09/xmldsig#"
    SIFEN_NS_URI = "http://ekuatia.set.gov.py/sifen/xsd"

    # 8.1) Validar que NO exista "<ds:" ni "xmlns:ds" en el texto serializado
    if b"<ds:" in out:
        raise XMLSecError("Post-check falló: todavía existe '<ds:' en el XML serializado (debe ser default namespace sin prefijo)")
    if b'xmlns:ds=' in out:
        raise XMLSecError("Post-check falló: todavía existe 'xmlns:ds=' en el XML serializado (debe ser default namespace sin prefijo)")

    # 8.2) Validar que SÍ exista '<Signature xmlns="http://www.w3.org/2000/09/xmldsig#"' en el texto serializado
    if b'<Signature xmlns="http://www.w3.org/2000/09/xmldsig#"' not in out:
        raise XMLSecError("Post-check falló: no se encontró '<Signature xmlns=\"http://www.w3.org/2000/09/xmldsig#\"' en el XML serializado")

    # 3) Post-check estructural con lxml
    # tree/root ya existen en tu función
    root2 = tree.getroot()

    # 3.1) Ubicar rDE y DE
    rde_check = root2.find(f".//{{{SIFEN_NS_URI}}}rDE")
    if rde_check is None:
        raise XMLSecError("Post-check falló: no se encontró <rDE> (SIFEN_NS_URI)")

    de2 = rde_check.find(f"./{{{SIFEN_NS_URI}}}DE")
    if de2 is None:
        # por si DE vino sin namespace:
        de2 = rde_check.find("./DE")
    if de2 is None:
        raise XMLSecError("Post-check falló: no se encontró <DE> dentro de <rDE>")

    de_id_check = de2.get("Id")
    if not de_id_check:
        raise XMLSecError("Post-check falló: <DE> no tiene atributo Id")

    # 3.2) Signature debe ser HERMANO de DE y en DS_NS_URI (prefijo NO importa)
    # Validar que el parent directo del Signature sea rDE (namespace SIFEN)
    sig2 = None
    children = list(rde_check)
    for i, ch in enumerate(children):
        if ch is de2 and i + 1 < len(children):
            cand = children[i + 1]
            if cand.tag == f"{{{DS_NS_URI}}}Signature":
                sig2 = cand
            break

    if sig2 is None:
        # fallback: buscar cualquier Signature en DS_NS_URI dentro de rDE
        sig_any = rde_check.find(f".//{{{DS_NS_URI}}}Signature")
        if sig_any is not None:
            raise XMLSecError("Post-check falló: Signature existe pero NO está inmediatamente después de <DE> dentro de <rDE>")
        raise XMLSecError("Post-check falló: no se encontró Signature en DS_NS_URI dentro de <rDE>")

    # Validar que el parent directo del Signature sea rDE (tag endswith "}rDE")
    sig2_parent = sig2.getparent()
    if sig2_parent is None:
        raise XMLSecError("Post-check falló: Signature no tiene parent")
    if not sig2_parent.tag.endswith("}rDE") and sig2_parent.tag != "rDE":
        raise XMLSecError(f"Post-check falló: el parent directo del Signature es '{sig2_parent.tag}' (se esperaba rDE)")

    # Validar orden: Signature debe estar después de DE dentro de rDE
    de_idx = -1
    sig_idx = -1
    for i, ch in enumerate(children):
        if ch is de2:
            de_idx = i
        if ch is sig2:
            sig_idx = i
    if de_idx == -1 or sig_idx == -1:
        raise XMLSecError("Post-check falló: no se pudo determinar el orden de DE y Signature")
    if sig_idx <= de_idx:
        raise XMLSecError(f"Post-check falló: Signature está en índice {sig_idx}, DE está en {de_idx} (Signature debe estar después de DE)")

    # 8.3) Deben existir SignatureValue, DigestValue, X509Certificate
    if sig2.find(f".//{{{DS_NS_URI}}}SignatureValue") is None:
        raise XMLSecError("Post-check falló: falta SignatureValue")
    if sig2.find(f".//{{{DS_NS_URI}}}DigestValue") is None:
        raise XMLSecError("Post-check falló: falta DigestValue")
    if sig2.find(f".//{{{DS_NS_URI}}}X509Certificate") is None:
        raise XMLSecError("Post-check falló: falta X509Certificate")

    # 8.4) Validar Reference URI="#Id"
    ref = sig2.find(f".//{{{DS_NS_URI}}}Reference")
    uri = ref.get("URI") if ref is not None else None
    if uri != f"#{de_id_check}":
        raise XMLSecError(f"Post-check falló: Reference URI esperado '#{de_id_check}', vino '{uri}'")

    logger.info("Post-check estructural OK: rDE/DE/Signature ubicados correctamente, SignatureValue/DigestValue/X509Certificate presentes, Reference URI válido, Signature sin prefijo ds: ni xmlns:ds")
    return out

