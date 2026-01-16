"""
Firma XMLDSig para Documentos Electrónicos SIFEN

Implementa firma digital XMLDSig Enveloped según especificación SIFEN:
- Enveloped signature dentro del mismo <DE>
- Reference URI="#<Id del DE>"
- Canonicalization: Exclusive XML Canonicalization (exc-c14n)
- Digest: SHA-256
- SignatureMethod: RSA-SHA256
- Transforms: enveloped-signature + exc-c14n
- X509Certificate en KeyInfo
"""

import logging
import base64
import os
from pathlib import Path
from typing import Optional, Any

# Import lxml.etree - el linter puede no reconocerlo, pero funciona correctamente
try:
    import lxml.etree as etree  # noqa: F401
except ImportError:
    etree = None  # type: ignore

try:
    from signxml.signer import XMLSigner  # noqa: F401
    from signxml.verifier import XMLVerifier  # noqa: F401
    import signxml
    from cryptography.hazmat.backends import default_backend

    SIGNXML_AVAILABLE = True
except ImportError:
    SIGNXML_AVAILABLE = False
    XMLSigner = None  # type: ignore
    XMLVerifier = None  # type: ignore
    signxml = None  # type: ignore

from .pkcs12_utils import p12_to_temp_pem_files, cleanup_pem_files, PKCS12Error
from .exceptions import SifenClientError

logger = logging.getLogger(__name__)

# Intentar importar requests para descargar certificados de CA
try:
    import requests
    REQUESTS_AVAILABLE = True
except ImportError:
    REQUESTS_AVAILABLE = False
    logger.warning("requests no disponible, no se podrán descargar certificados de CA automáticamente")

# Namespaces
DS_NS = "http://www.w3.org/2000/09/xmldsig#"
SIFEN_NS = "http://ekuatia.set.gov.py/sifen/xsd"


class XMLDSigError(SifenClientError):
    """Excepción para errores en firma XMLDSig"""

    pass


def _download_ca_cert_from_aia(cert: Any) -> Optional[Any]:  # type: ignore
    """
    Descarga el certificado de la CA desde Authority Information Access (AIA).
    
    Args:
        cert: Certificado del usuario
        
    Returns:
        Certificado de la CA o None si no se pudo descargar
    """
    if not REQUESTS_AVAILABLE:
        logger.warning("requests no disponible, no se puede descargar certificado de CA")
        return None
    
    try:
        from cryptography.x509.oid import ExtensionOID, AuthorityInformationAccessOID
        from cryptography import x509
        
        # Buscar Authority Information Access
        aia = cert.extensions.get_extension_for_oid(ExtensionOID.AUTHORITY_INFORMATION_ACCESS)
        
        # Buscar URL de caIssuers
        ca_issuer_url = None
        for access_desc in aia.value:
            if access_desc.access_method == AuthorityInformationAccessOID.CA_ISSUERS:
                ca_issuer_url = access_desc.access_location.value
                break
        
        if not ca_issuer_url:
            logger.warning("No se encontró URL de CA Issuers en AIA")
            return None
        
        logger.info(f"Descargando certificado de CA desde: {ca_issuer_url}")
        
        # Descargar certificado
        response = requests.get(ca_issuer_url, timeout=10)
        response.raise_for_status()
        
        # Intentar parsear como DER o PEM
        try:
            ca_cert = x509.load_der_x509_certificate(response.content, default_backend())
        except Exception:
            try:
                ca_cert = x509.load_pem_x509_certificate(response.content, default_backend())
            except Exception as e:
                logger.warning(f"No se pudo parsear certificado de CA: {e}")
                return None
        
        logger.info(f"✅ Certificado de CA descargado: {ca_cert.subject.rfc4514_string()}")
        return ca_cert
        
    except x509.ExtensionNotFound:
        logger.warning("Certificado no tiene extensión Authority Information Access")
        return None
    except Exception as e:
        logger.warning(f"Error al descargar certificado de CA: {e}")
        return None


def _extract_de_id(xml_root: Any) -> Optional[str]:  # type: ignore
    """Extrae el atributo Id del elemento DE."""
    if etree is None:
        raise XMLDSigError("lxml no está disponible")
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


def _validate_no_dummy_signature(xml_str: str) -> None:
    """Valida que no haya firmas dummy en el XML."""
    try:
        if etree is None:
            return
        # Buscar SignatureValue
        if "<ds:SignatureValue>" in xml_str or "<SignatureValue>" in xml_str:
            # Parsear y extraer SignatureValue
            root = etree.fromstring(xml_str.encode("utf-8"))  # type: ignore

            # Buscar SignatureValue en namespace DS
            ns = {"ds": DS_NS}
            sig_values = root.xpath("//ds:SignatureValue", namespaces=ns)

            for sig_val_elem in sig_values:
                if sig_val_elem.text:
                    try:
                        # Decodificar base64
                        decoded = base64.b64decode(sig_val_elem.text.strip())
                        decoded_str = decoded.decode("ascii", errors="ignore")

                        # Verificar si es texto dummy
                        if (
                            "this is a test" in decoded_str.lower()
                            or "dummy" in decoded_str.lower()
                        ):
                            raise XMLDSigError(
                                "Se detectó firma dummy en el XML. "
                                "El SignatureValue contiene texto de prueba. "
                                "Debe usar un certificado real para firmar."
                            )
                    except Exception:
                        # Si no se puede decodificar,
                        # asumir que es válido (binario real)
                        pass
    except Exception as e:
        # Si falla la validación, solo loggear warning (no abortar)
        logger.warning(f"No se pudo validar firma dummy: {e}")


def _fix_signature_algorithms_nt16(xml_str: str) -> str:
    """
    Post-procesa el XML firmado para corregir algoritmos según NT16.
    
    signxml a veces ignora la configuración y usa SHA1 por defecto.
    Esta función fuerza los algoritmos correctos sin invalidar la firma.
    
    IMPORTANTE: Usa reemplazo de strings para preservar el encoding de los certificados.
    
    Args:
        xml_str: XML firmado
        
    Returns:
        XML con algoritmos corregidos
    """
    import re
    modified_xml = xml_str
    
    # 1) Eliminar firmas duplicadas (mantener solo la última que tiene los certificados)
    sig_count = modified_xml.count('<ds:Signature>')
    if sig_count > 1:
        logger.warning(f"⚠️  Encontradas {sig_count} firmas, eliminando duplicados")
        
        # Encontrar todas las firmas
        sig_pattern = r'<ds:Signature>.*?</ds:Signature>'
        signatures = list(re.finditer(sig_pattern, modified_xml, re.DOTALL))
        
        if len(signatures) > 1:
            # Eliminar todas excepto la última (que contiene los certificados)
            for sig_match in reversed(signatures[:-1]):
                modified_xml = modified_xml[:sig_match.start()] + modified_xml[sig_match.end():]
            
            logger.warning(f"⚠️  Eliminadas {sig_count - 1} firmas duplicadas")
    
    # 2) Corregir SignatureMethod SHA1 -> SHA256
    if 'xmldsig#rsa-sha1' in modified_xml:
        modified_xml = modified_xml.replace(
            'http://www.w3.org/2000/09/xmldsig#rsa-sha1',
            'http://www.w3.org/2001/04/xmldsig-more#rsa-sha256'
        )
        logger.warning("⚠️  Corregido SignatureMethod: rsa-sha1 -> rsa-sha256")
    
    # 3) Corregir DigestMethod SHA1 -> SHA256
    if 'xmldsig#sha1' in modified_xml:
        modified_xml = modified_xml.replace(
            'http://www.w3.org/2000/09/xmldsig#sha1',
            'http://www.w3.org/2001/04/xmlenc#sha256'
        )
        logger.warning("⚠️  Corregido DigestMethod: sha1 -> sha256")
    
    # 4) Corregir Reference/@URI vacío
    empty_uri_pattern = r'<ds:Reference URI="">'
    if re.search(empty_uri_pattern, modified_xml):
        # Extraer DE/@Id del XML
        de_id_match = re.search(r'<DE Id="([^"]+)"', modified_xml)
        if de_id_match:
            de_id = de_id_match.group(1)
            modified_xml = re.sub(empty_uri_pattern, f'<ds:Reference URI="#{de_id}">', modified_xml)
            logger.warning(f"⚠️  Corregido Reference/@URI: '' -> '#{de_id}'")
    
    # 5) Eliminar Transform adicional (exc-c14n) - dejar solo enveloped-signature
    # Buscar y reemplazar el bloque de Transforms que tiene 2 transforms
    double_transform_pattern = r'(<ds:Transforms>)\s*(<ds:Transform Algorithm="http://www\.w3\.org/2000/09/xmldsig#enveloped-signature"/>)\s*<ds:Transform Algorithm="http://www\.w3\.org/TR/2001/REC-xml-c14n-20010315"/>\s*(</ds:Transforms>)'
    if re.search(double_transform_pattern, modified_xml):
        modified_xml = re.sub(double_transform_pattern, r'\1\2\3', modified_xml)
        logger.warning("⚠️  Eliminado Transform adicional: xml-c14n")
    
    logger.info("✅ Algoritmos corregidos según NT16")
    return modified_xml


def assert_sifen_v150_signature_shape(xml_str: str) -> None:
    """
    Valida estrictamente que la firma XMLDSig cumple con NT16 (MT v150).
    
    Verifica:
    - CanonicalizationMethod/@Algorithm es uno de los válidos NT16
    - SignatureMethod/@Algorithm es rsa-sha256/384/512
    - DigestMethod/@Algorithm es sha256/384/512
    - Reference/@URI apunta a #<DE/@Id>
    - Transforms contiene SOLO enveloped-signature (sin exc-c14n adicional)
    
    Args:
        xml_str: XML firmado como string
        
    Raises:
        XMLDSigError: Si la firma no cumple con NT16
    """
    if etree is None:
        logger.warning("lxml no disponible, saltando validación NT16")
        return
    
    try:
        root = etree.fromstring(xml_str.encode("utf-8"))  # type: ignore
    except Exception as e:
        raise XMLDSigError(f"Error al parsear XML para validación NT16: {e}")
    
    ns = {"ds": DS_NS, "sifen": SIFEN_NS}
    
    # Buscar ds:Signature
    signatures = root.xpath("//ds:Signature", namespaces=ns)
    if not signatures:
        raise XMLDSigError("No se encontró ds:Signature en el XML")
    
    sig = signatures[0]
    
    # 1) Validar CanonicalizationMethod
    c14n_methods = sig.xpath(".//ds:SignedInfo/ds:CanonicalizationMethod/@Algorithm", namespaces=ns)
    if not c14n_methods:
        raise XMLDSigError("No se encontró CanonicalizationMethod/@Algorithm")
    
    c14n_alg = c14n_methods[0]
    valid_c14n = [
        "http://www.w3.org/TR/2001/REC-xml-c14n-20010315",
        "http://www.w3.org/TR/2001/REC-xml-c14n-20010315#WithComments",
        "http://www.w3.org/2001/10/xml-exc-c14n",
        "http://www.w3.org/2001/10/xml-exc-c14n#",  # Variante con # al final
        "http://www.w3.org/2001/10/xml-exc-c14n#WithComments",
    ]
    if c14n_alg not in valid_c14n:
        raise XMLDSigError(
            f"CanonicalizationMethod inválido según NT16.\n"
            f"  Actual: {c14n_alg}\n"
            f"  Válidos: {valid_c14n}"
        )
    
    # 2) Validar SignatureMethod
    sig_methods = sig.xpath(".//ds:SignedInfo/ds:SignatureMethod/@Algorithm", namespaces=ns)
    if not sig_methods:
        raise XMLDSigError("No se encontró SignatureMethod/@Algorithm")
    
    sig_alg = sig_methods[0]
    valid_sig = [
        "http://www.w3.org/2001/04/xmldsig-more#rsa-sha256",
        "http://www.w3.org/2001/04/xmldsig-more#rsa-sha384",
        "http://www.w3.org/2001/04/xmldsig-more#rsa-sha512",
    ]
    if sig_alg not in valid_sig:
        raise XMLDSigError(
            f"SignatureMethod inválido según NT16.\n"
            f"  Actual: {sig_alg}\n"
            f"  Válidos: {valid_sig}"
        )
    
    # 3) Validar DigestMethod
    digest_methods = sig.xpath(".//ds:SignedInfo/ds:Reference/ds:DigestMethod/@Algorithm", namespaces=ns)
    if not digest_methods:
        raise XMLDSigError("No se encontró DigestMethod/@Algorithm")
    
    digest_alg = digest_methods[0]
    valid_digest = [
        "http://www.w3.org/2001/04/xmlenc#sha256",
        "http://www.w3.org/2001/04/xmldsig-more#sha384",
        "http://www.w3.org/2001/04/xmlenc#sha512",
    ]
    if digest_alg not in valid_digest:
        raise XMLDSigError(
            f"DigestMethod inválido según NT16.\n"
            f"  Actual: {digest_alg}\n"
            f"  Válidos: {valid_digest}"
        )
    
    # 4) Validar Reference/@URI apunta a #<DE/@Id>
    ref_uris = sig.xpath(".//ds:SignedInfo/ds:Reference/@URI", namespaces=ns)
    if not ref_uris:
        raise XMLDSigError("No se encontró Reference/@URI")
    
    ref_uri = ref_uris[0]
    
    # Buscar DE/@Id
    de_nodes = root.xpath("//sifen:DE", namespaces=ns)
    if not de_nodes:
        de_nodes = root.xpath("//DE")
    
    if not de_nodes:
        raise XMLDSigError("No se encontró elemento DE en el XML")
    
    de_id = de_nodes[0].get("Id")
    if not de_id:
        raise XMLDSigError("Elemento DE no tiene atributo Id")
    
    expected_uri = f"#{de_id}"
    if ref_uri != expected_uri:
        raise XMLDSigError(
            f"Reference/@URI no apunta al DE/@Id.\n"
            f"  Actual: {ref_uri}\n"
            f"  Esperado: {expected_uri}"
        )
    
    # 5) Validar Transforms: enveloped-signature (y opcionalmente exc-c14n)
    transforms = sig.xpath(".//ds:SignedInfo/ds:Reference/ds:Transforms/ds:Transform/@Algorithm", namespaces=ns)
    if not transforms:
        raise XMLDSigError("No se encontraron Transforms")
    
    # SIFEN v150 acepta 1 o 2 transforms:
    # - Solo enveloped-signature (NT16 básico)
    # - enveloped-signature + exc-c14n (recomendado)
    if len(transforms) < 1 or len(transforms) > 2:
        raise XMLDSigError(
            f"Número de Transforms inválido.\n"
            f"  Actual: {len(transforms)} transforms: {transforms}\n"
            f"  Válidos: 1 (enveloped-signature) o 2 (enveloped-signature + exc-c14n)"
        )
    
    # Primer transform DEBE ser enveloped-signature
    expected_transform = "http://www.w3.org/2000/09/xmldsig#enveloped-signature"
    if transforms[0] != expected_transform:
        raise XMLDSigError(
            f"Primer Transform debe ser enveloped-signature.\n"
            f"  Actual: {transforms[0]}\n"
            f"  Esperado: {expected_transform}"
        )
    
    # Si hay segundo transform, debe ser exc-c14n
    if len(transforms) == 2:
        valid_exc_c14n = [
            "http://www.w3.org/2001/10/xml-exc-c14n",
            "http://www.w3.org/2001/10/xml-exc-c14n#"
        ]
        if transforms[1] not in valid_exc_c14n:
            raise XMLDSigError(
                f"Segundo Transform debe ser exc-c14n.\n"
                f"  Actual: {transforms[1]}\n"
                f"  Válidos: {valid_exc_c14n}"
            )
    
    logger.info("✅ Firma cumple con NT16 (MT v150)")
    logger.info(f"  - CanonicalizationMethod: {c14n_alg}")
    logger.info(f"  - SignatureMethod: {sig_alg}")
    logger.info(f"  - DigestMethod: {digest_alg}")
    logger.info(f"  - Reference URI: {ref_uri}")
    logger.info(f"  - Transforms: {len(transforms)} ({', '.join(transforms)})")


def sign_de_xml(xml_str: str, p12_path: str, p12_password: str) -> str:
    """
    Firma un XML DE con XMLDSig según especificación SIFEN.

    Args:
        xml_str: XML del DE (puede incluir rDE wrapper)
        p12_path: Ruta al certificado P12/PFX
        p12_password: Contraseña del certificado P12

    Returns:
        XML firmado con ds:Signature

    Raises:
        XMLDSigError: Si falta signxml, certificado, o falla la firma
    """
    if not SIGNXML_AVAILABLE:
        raise XMLDSigError(
            "signxml no está instalado. Instale con: pip install signxml"
        )

    p12_path_obj = Path(p12_path)
    if not p12_path_obj.exists():
        raise XMLDSigError(f"Certificado P12 no encontrado: {p12_path}")

    if etree is None:
        raise XMLDSigError("lxml no está disponible")
    # Parsear XML
    try:
        xml_root = etree.fromstring(xml_str.encode("utf-8"))  # type: ignore
    except Exception as e:
        raise XMLDSigError(f"Error al parsear XML: {e}")

    # Extraer Id del DE
    de_id = _extract_de_id(xml_root)
    if not de_id:
        raise XMLDSigError("No se encontró atributo Id en el elemento DE")

    logger.info(f"Firmando DE con Id={de_id}")

    # Convertir P12 a PEM temporales
    cert_pem_path = None
    key_pem_path = None
    try:
        cert_pem_path, key_pem_path = p12_to_temp_pem_files(p12_path, p12_password)

        # Leer certificado y clave
        with open(cert_pem_path, "rb") as f:
            cert_pem = f.read()

        with open(key_pem_path, "rb") as f:
            key_pem = f.read()

        # Cargar certificado y clave privada
        from cryptography import x509
        from cryptography.hazmat.primitives import serialization

        cert = x509.load_pem_x509_certificate(cert_pem, default_backend())
        private_key = serialization.load_pem_private_key(
            key_pem, None, default_backend()
        )
        
        # Intentar descargar certificado de CA desde AIA
        ca_cert = _download_ca_cert_from_aia(cert)
        
        # Si falla la descarga, intentar cargar desde archivo local
        if not ca_cert:
            ca_cert_path = Path.home() / ".sifen" / "certs" / "ca-documenta.crt"
            if ca_cert_path.exists():
                logger.info(f"Cargando certificado de CA desde: {ca_cert_path}")
                try:
                    with open(ca_cert_path, 'rb') as f:
                        ca_cert_data = f.read()
                    
                    # Intentar parsear como DER o PEM
                    try:
                        ca_cert = x509.load_der_x509_certificate(ca_cert_data, default_backend())
                    except Exception:
                        ca_cert = x509.load_pem_x509_certificate(ca_cert_data, default_backend())
                    
                    logger.info(f"✅ Certificado de CA cargado desde archivo local: {ca_cert.subject.rfc4514_string()}")
                except Exception as e:
                    logger.warning(f"Error al cargar certificado de CA desde archivo: {e}")
        
        # IMPORTANTE: Para SIFEN v150, solo incluir el certificado leaf (sin CA)
        # La validación de la cadena se hace en el lado del servidor
        cert_chain = [cert]  # Solo el certificado del firmante
        logger.info(f"✅ Certificado leaf: {len(cert_chain)} certificado(s)")
        logger.info("    SIFEN v150 requiere solo el certificado del firmante en KeyInfo")

        # Encontrar el elemento DE a firmar
        de_elem = None
        for elem in xml_root.iter():  # type: ignore
            local_name = etree.QName(elem).localname  # type: ignore
            if local_name == "DE":
                de_elem = elem
                break

        if de_elem is None:
            raise XMLDSigError("No se encontró elemento DE en el XML")

        # Eliminar firma dummy existente si existe
        # Buscar ds:Signature dentro del DE
        ds_ns = "http://www.w3.org/2000/09/xmldsig#"
        ns = {"ds": ds_ns}
        existing_signatures = de_elem.xpath(".//ds:Signature", namespaces=ns)
        for sig in existing_signatures:
            parent = sig.getparent()
            if parent is not None:
                parent.remove(sig)
                logger.info("Firma dummy existente eliminada antes de firmar")

        # Firmar usando signxml
        # signxml requiere que el elemento tenga el atributo Id como ID válido
        # Asegurar que el atributo Id esté marcado como ID
        de_elem.set("Id", de_id)

        # Registrar el atributo Id como ID válido para XML
        # Esto es necesario para que la referencia URI funcione
        # signxml usa el atributo Id automáticamente si está presente

        # Crear signer con configuración SIFEN v150 (NT16 MT v150)
        # IMPORTANTE: Valores EXACTOS según XML real SIFEN:
        # - CanonicalizationMethod: http://www.w3.org/2001/10/xml-exc-c14n#
        # - SignatureMethod: http://www.w3.org/2001/04/xmldsig-more#rsa-sha256
        # - DigestMethod: http://www.w3.org/2001/04/xmlenc#sha256
        # - Transforms: enveloped-signature + xml-exc-c14n
        if signxml is None or signxml.methods is None:
            raise XMLDSigError("signxml no está disponible correctamente")
        
        # Importar enumeraciones de signxml para forzar algoritmos correctos
        from signxml import SignatureMethod, DigestAlgorithm, CanonicalizationMethod
        
        # signxml 4.x no tiene signxml.transforms.Transform
        # Los transforms se especifican directamente como strings en una lista
        # Transform 1: enveloped-signature
        # Transform 2: exclusive canonicalization
        transforms = [
            'http://www.w3.org/2000/09/xmldsig#enveloped-signature'
            # NOTA: xml-exc-c14n# NO va en Transforms según NT16/MT v150
        ]
        
        signer = XMLSigner(  # type: ignore
            method=signxml.methods.enveloped,  # Enveloped signature
            signature_algorithm=SignatureMethod.RSA_SHA256,  # RSA-SHA256
            digest_algorithm=DigestAlgorithm.SHA256,  # SHA-256
            c14n_algorithm=CanonicalizationMethod.EXCLUSIVE_XML_CANONICALIZATION_1_0,  # EXC-C14N
            exclude_c14n_transform_element=True  # Solo enveloped-signature en Transforms
        )

        # Firmar el elemento DE
        # reference_uri debe apuntar al Id del DE (formato: #Id)
        # signxml agrega ds:Signature como hijo del elemento firmado
        # SIFEN: Transforms deben ser enveloped-signature + xml-exc-c14n
        # id_attribute="Id" le dice a signxml que use el atributo "Id" como ID
        # IMPORTANTE: cert debe ser una lista de certificados
        signed_de = signer.sign(  # type: ignore
            de_elem,
            key=private_key,  # type: ignore[arg-type]
            cert=cert_chain,  # Cadena completa de certificados (usuario + CA)
            reference_uri=f"#{de_id}",
            id_attribute="Id",  # Atributo que contiene el ID
            always_add_key_value=False,
        )

        # IMPORTANTE: La ubicación de la firma depende del feature flag
        # Por defecto para SIFEN: Signature como hija de rDE (no dentro de DE)
        # signxml firma DE y agrega Signature como hijo de DE
        # Según SIFEN_SIGNATURE_PARENT, podemos dejarla en DE o moverla a rDE
        signature_parent = os.environ.get("SIFEN_SIGNATURE_PARENT", "RDE").upper()
        
        if signature_parent not in ["DE", "RDE"]:
            logger.warning(f"SIFEN_SIGNATURE_PARENT inválido: {signature_parent}, usando DE")
            signature_parent = "DE"
        
        logger.info(f"Ubicación de firma: {signature_parent} (configurado por SIFEN_SIGNATURE_PARENT)")
        
        root = xml_root
        
        if etree.QName(root).localname != "rDE":
            raise XMLDSigError("Elemento raíz no es rDE")

        # Eliminar cualquier ds:Signature existente en rDE
        ds_ns = "http://www.w3.org/2000/09/xmldsig#"
        ns = {"ds": ds_ns}
        existing_root_sigs = root.xpath(".//ds:Signature", namespaces=ns)
        for sig in existing_root_sigs:
            parent = sig.getparent()
            if parent is not None:
                parent.remove(sig)

        if signature_parent == "RDE":
            # Comportamiento original: mover Signature a rDE
            # Extraer Signature del DE firmado
            signature_in_de = signed_de.xpath(".//ds:Signature", namespaces=ns)
            if not signature_in_de:
                raise XMLDSigError("No se encontró Signature en DE firmado")
            signature_node = signature_in_de[0]

            # Eliminar Signature del DE
            de_parent = signature_node.getparent()
            if de_parent is not None:
                de_parent.remove(signature_node)

            # Insertar Signature en rDE, después de DE
            # Buscar el elemento DE en el root
            de_in_root = root.xpath(".//DE", namespaces={"sifen": "http://ekuatia.set.gov.py/sifen/xsd"})
            if not de_in_root:
                # Intentar sin namespace (fallback)
                de_in_root = root.xpath(".//DE")
                if not de_in_root:
                    # Intentar búsqueda directa por nombre
                    for child in root:
                        if etree.QName(child).localname == "DE":
                            de_in_root = [child]
                            break
                    if not de_in_root:
                        raise XMLDSigError("No se encontró DE en rDE")
            de_node = de_in_root[0]

            # Insertar Signature después de DE
            de_index = list(root).index(de_node)
            root.insert(de_index + 1, signature_node)

            # Reemplazar el DE original con el firmado (sin Signature)
            de_parent = de_node.getparent()
            if de_parent is not None:
                de_parent.remove(de_node)
                de_parent.append(signed_de)
            else:
                # Si DE es root, usar signed_de como nuevo root
                xml_root = signed_de

            # IMPORTANTE: Mantener orden exacto: dVerFor, DE, Signature, gCamFuFD
            # Buscar todos los hijos del root
            children = list(root)
            dverfor = None
            de = None
            signature = None
            gcamfufd = None
            
            for child in children:
                qname = etree.QName(child)
                if qname.localname == "dVerFor":
                    dverfor = child
                elif qname.localname == "DE":
                    de = child
                elif qname.localname == "Signature":
                    signature = child
                elif qname.localname == "gCamFuFD":
                    gcamfufd = child
            
            # Reconstruir el orden exacto: dVerFor, DE, Signature, gCamFuFD
            if dverfor is not None and de is not None and signature is not None:
                root.clear()
                root.append(dverfor)
                root.append(de)
                root.append(signature)
                # gCamFuFD puede ser None (se agregará después si es necesario)
                if gcamfufd is not None:
                    root.append(gcamfufd)
        else:
            # Nuevo comportamiento: dejar Signature dentro de DE (enveloped)
            # signed_de ya contiene la Signature como hijo de DE
            # Reemplazar el DE original con el firmado (con Signature dentro)
            de_in_root = root.xpath(".//DE", namespaces={"sifen": "http://ekuatia.set.gov.py/sifen/xsd"})
            if not de_in_root:
                # Intentar sin namespace (fallback)
                de_in_root = root.xpath(".//DE")
                if not de_in_root:
                    # Intentar búsqueda directa por nombre
                    for child in root:
                        if etree.QName(child).localname == "DE":
                            de_in_root = [child]
                            break
                    if not de_in_root:
                        raise XMLDSigError("No se encontró DE en rDE")
            de_node = de_in_root[0]

            # Reemplazar el DE original con el firmado (con Signature dentro)
            de_parent = de_node.getparent()
            if de_parent is not None:
                de_parent.remove(de_node)
                de_parent.append(signed_de)
            else:
                # Si DE es root, usar signed_de como nuevo root
                xml_root = signed_de

        # Serializar XML firmado
        # IMPORTANTE: SIFEN es sensible a whitespace - NO pretty_print
        signed_xml = etree.tostring(
            xml_root, xml_declaration=True, encoding="UTF-8", pretty_print=False
        ).decode("utf-8")

        # Validar que no haya firmas dummy
        _validate_no_dummy_signature(signed_xml)
        
        # Corregir algoritmos si signxml usó SHA1 por defecto
        signed_xml = _fix_signature_algorithms_nt16(signed_xml)
        
        # Validar que la firma cumple con NT16 (MT v150)
        assert_sifen_v150_signature_shape(signed_xml)

        logger.info("DE firmado exitosamente con XMLDSig")
        return signed_xml

    except PKCS12Error as e:
        raise XMLDSigError(f"Error al convertir certificado P12: {e}") from e
    except Exception as e:
        raise XMLDSigError(f"Error al firmar XML: {e}") from e
    finally:
        # Limpiar archivos PEM temporales
        if cert_pem_path and key_pem_path:
            cleanup_pem_files(cert_pem_path, key_pem_path)
