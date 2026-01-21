"""
Firma XMLDSig para Documentos Electrónicos SIFEN usando python-xmlsec
VERSIÓN LIMPIA: Elimina whitespace antes de firmar según reglas SIFEN

Basado en las reglas del knowledge base:
- NO incorporar: line-feed, carriage return, tab, espacios entre etiquetas
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
from app.sifen_client.qr_generator import build_qr_dcarqr

logger = logging.getLogger(__name__)

# Namespaces
DS_NS = "http://www.w3.org/2000/09/xmldsig#"
DSIG_NS = "http://www.w3.org/2000/09/xmldsig#"  # Alias para claridad
SIFEN_NS = "http://ekuatia.set.gov.py/sifen/xsd"
XMLNS_NS = "http://www.w3.org/2000/xmlns/"  # Namespace para atributos xmlns


def _clean_xml_whitespace(xml_bytes: bytes) -> bytes:
    """
    Elimina whitespace entre etiquetas según reglas SIFEN v150.
    
    Reglas del knowledge base:
    - NO incorporar: line-feed, carriage return, tab, espacios entre etiquetas
    - No usar pretty_print que agrega whitespace
    
    Esta función debe ejecutarse ANTES de firmar para no invalidar la firma.
    """
    if etree is None:
        raise RuntimeError("lxml.etree no disponible para limpiar XML")
    
    # Parsear con remove_blank_text=True para eliminar whitespace insignificante
    parser = etree.XMLParser(remove_blank_text=True, remove_comments=False)
    
    try:
        root = etree.fromstring(xml_bytes, parser=parser)
    except Exception as e:
        raise RuntimeError(f"Error parseando XML para limpiar whitespace: {e}")
    
    # Recorrer árbol y eliminar cualquier text/tail que sea solo whitespace
    for element in root.iter():
        if element.text and element.text.strip() == '':
            element.text = None
        if element.tail and element.tail.strip() == '':
            element.tail = None
    
    # Serializar SIN pretty_print, sin XML declaration y sin whitespace final
    cleaned = etree.tostring(
        root, 
        encoding="UTF-8", 
        method="xml",
        pretty_print=False,
        with_tail=False,
        xml_declaration=False  # No agregar XML declaration
    )
    
    # Eliminar cualquier whitespace al final del XML
    cleaned = cleaned.rstrip()
    
    # Eliminar \n después de <?xml ...?> si existe (lxml lo agrega automáticamente)
    # Esto cumple con la regla SIFEN de "NO incorporar: line-feed"
    if cleaned.startswith(b'<?xml'):
        # Buscar el fin de la declaración XML
        end_decl = cleaned.find(b'?>')
        if end_decl != -1:
            # Verificar si hay \n después de ?>
            if len(cleaned) > end_decl + 2 and cleaned[end_decl + 2] == 0x0A:
                # Eliminar el \n
                cleaned = cleaned[:end_decl + 2] + cleaned[end_decl + 3:]
    
    return cleaned


def _sanitize_xmldsig_prefixes(xml_bytes: bytes) -> bytes:
    """
    Elimina prefijos ds: y xmlns:ds= del XML firmado usando lxml.
    Reconstruye el elemento Signature para usar namespace SIFEN (requerimiento específico).
    
    Args:
        xml_bytes: XML firmado que puede contener prefijos ds:
        
    Returns:
        XML sanitizado con Signature usando xmlns="http://ekuatia.set.gov.py/sifen/xsd"
        
    Raises:
        RuntimeError: Si después de sanitizar aún quedan prefijos ds:
    """
    if etree is None:
        raise RuntimeError("lxml.etree no disponible para sanitizar XML")
    
    # SIFEN requiere que Signature use su namespace
    SIFEN_NS = "http://ekuatia.set.gov.py/sifen/xsd"
    
    # Asegurar que el directorio artifacts exista
    import os
    os.makedirs("artifacts", exist_ok=True)
    
    # Parsear el XML
    try:
        parser = etree.XMLParser(remove_blank_text=True, remove_comments=False)
        tree = etree.fromstring(xml_bytes, parser=parser)
    except Exception as e:
        raise RuntimeError(f"Error parseando XML para sanitizar: {e}")
    
    # Encontrar el elemento Signature (con cualquier prefijo o sin prefijo)
    sig_elements = tree.xpath(".//*[local-name()='Signature']")
    if not sig_elements:
        raise RuntimeError("No se encontró elemento Signature en el XML")
    
    if len(sig_elements) > 1:
        raise RuntimeError(f"Se encontraron múltiples elementos Signature: {len(sig_elements)}")
    
    sig_original = sig_elements[0]
    parent = sig_original.getparent()
    if parent is None:
        raise RuntimeError("El elemento Signature no tiene padre")
    
    # Crear nuevo Signature con namespace SIFEN (requerido por SIFEN según memoria solución definitiva)
    # NOTA: Aunque rompe verificación con xmlsec1, SIFEN lo acepta
    SIFEN_NS = "http://ekuatia.set.gov.py/sifen/xsd"
    nsmap = {None: SIFEN_NS}  # Default namespace SIFEN sin prefijo
    new_sig = etree.Element(f"{{{SIFEN_NS}}}Signature", nsmap=nsmap)
    
    # NOTA: No necesitamos setear xmlns explícitamente porque nsmap ya lo define
    
    # Copiar atributos si existen (generalmente Signature no tiene atributos)
    for attr_name, attr_value in sig_original.attrib.items():
        new_sig.set(attr_name, attr_value)
    
    # Copiar hijos recursivamente, eliminando prefijos ds:
    def copy_children(source, target):
        for child in source:
            # Determinar el namespace del hijo
            if child.tag.startswith("{http://www.w3.org/2000/09/xmldsig#}"):
                # Elemento xmldsig - crear sin namespace (heredará default de Signature)
                local_name = child.tag.split("}")[-1]
                new_child = etree.SubElement(target, local_name)  # Sin namespace, heredará de parent
            else:
                # Otro namespace - mantener original
                new_child = etree.SubElement(target, child.tag)
            
            # Copiar atributos
            for attr_name, attr_value in child.attrib.items():
                new_child.set(attr_name, attr_value)
            
            # Copiar texto
            if child.text:
                new_child.text = child.text
            
            # Recursión para hijos anidados
            copy_children(child, new_child)
    
    copy_children(sig_original, new_sig)
    
    # Reemplazar el Signature original por el nuevo
    parent.replace(sig_original, new_sig)
    
    # Serializar el árbol completo
    try:
        # Usar etree.tostring en el árbol completo
        result = etree.tostring(
            tree,
            encoding="UTF-8",
            xml_declaration=True,
            with_tail=False,
            pretty_print=False  # Reverted to False to preserve signature
        )
        
        # IMPORTANTE: Remover XML declaration ya que necesitamos solo el fragment rDE
        # El rDE será insertado dentro de <rLoteDE>
        if result.startswith(b'<?xml'):
            end_decl = result.find(b'?>')
            if end_decl != -1:
                result = result[end_decl + 2:]
                # Remover \n si está presente
                if result.startswith(b'\n'):
                    result = result[1:]
        
    except Exception as e:
        raise RuntimeError(f"Error serializando XML sanitizado: {e}")
    
    # Verificación final de que no quedaron prefijos ds:
    if b"<ds:" in result or b"xmlns:ds=" in result:
        # Guardar debug para análisis
        try:
            with open("artifacts/rde_sanitizer_failed.xml", "wb") as f:
                f.write(result)
        except Exception:
            pass
        raise RuntimeError(
            "Sanitizer falló: quedan prefijos ds: o xmlns:ds= en el XML resultante. "
            "Se guardó artifacts/rde_sanitizer_failed.xml para análisis."
        )
    
    # Guardar versión sanitizada para debug
    try:
        with open("artifacts/rde_signed_sanitized.xml", "wb") as f:
            f.write(result)
    except Exception:
        pass  # No fallar si no se puede guardar debug
    
    # Verificar que Signature exista y sea único
    try:
        parsed = etree.fromstring(result)
        sig_count = len(parsed.xpath(".//*[local-name()='Signature']"))
        if sig_count != 1:
            raise RuntimeError(f"Se esperaba 1 Signature, se encontraron {sig_count}")
    except Exception as e:
        raise RuntimeError(f"Error validando XML final: {e}")
    
    return result


class XMLSecError(SifenClientError):
    """Excepción para errores en firma XMLDSig con xmlsec"""

    pass


def sign_de_with_p12(xml_bytes: bytes, p12_path: str, p12_password: str) -> bytes:
    """
    Firma un XML DE con XMLDSig usando python-xmlsec según especificación SIFEN v150.
    VERSIÓN LIMPIA: Elimina whitespace antes de firmar.
    
    Args:
        xml_bytes: XML del DE/rEnviDe como bytes
        p12_path: Ruta al certificado P12/PFX
        p12_password: Contraseña del certificado P12

    Returns:
        XML firmado como bytes (sin whitespace entre etiquetas)

    Raises:
        XMLSecError: Si falta xmlsec, certificado, o falla la firma
    """
    # 1) LIMPIAR WHITESPACE ANTES DE NADA
    # Según knowledge base: "NO incorporar: line-feed, carriage return, tab, espacios entre etiquetas"
    logger.info("Limpiando whitespace del XML antes de firmar...")
    xml_bytes = _clean_xml_whitespace(xml_bytes)
    logger.info("Whitespace eliminado. XML listo para firmar.")
    
    # Importar la función original del módulo principal
    from .xmlsec_signer import sign_de_with_p12 as original_sign
    
    # 2) Usar la función original para firmar
    signed_bytes = original_sign(xml_bytes, p12_path, p12_password)
    
    # 3) Eliminar XML declaration y \n del resultado
    # La función original agrega xml_declaration=True que incluye \n
    # Según SIFEN: "NO incorporar: line-feed"
    if signed_bytes.startswith(b'<?xml'):
        # Buscar el fin de la declaración XML
        end_decl = signed_bytes.find(b'?>')
        if end_decl != -1:
            # Eliminar la declaración XML completa incluyendo cualquier \n
            signed_bytes = signed_bytes[end_decl + 2:]
            # Eliminar \n si está al principio
            if signed_bytes.startswith(b'\n'):
                signed_bytes = signed_bytes[1:]
    
    # 4) Verificar que no hay whitespace después de firmar
    if b'\n' in signed_bytes or b'\t' in signed_bytes:
        logger.warning("ADVERTENCIA: El XML firmado contiene \\n o \\t")
    
    # 5) Aplicar sanitizer si es necesario
    # sanitizer se necesita solo si hay prefijos ds: (xmlns:ds=)
    # XMLDSig namespace es correcto para Signature
    if b"<ds:" in signed_bytes or b"xmlns:ds=" in signed_bytes:
        logger.warning("Detectados prefijos ds: - aplicando sanitizer")
        signed_bytes = _sanitize_xmldsig_prefixes(signed_bytes)
    
    return signed_bytes
