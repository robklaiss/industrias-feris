#!/usr/bin/env python3
"""
Test para verificar que el digest XMLDSig permanece válido después del proceso.
Este test detecta si hay mutaciones post-firma que causarían error 0160.
"""

import hashlib
import base64
import sys
from pathlib import Path
from lxml import etree

# Namespaces
DS_NS = "http://www.w3.org/2000/09/xmldsig#"
SIFEN_NS = "http://ekuatia.set.gov.py/sifen/xsd"
NS_MAP = {"ds": DS_NS, "s": SIFEN_NS}


def calculate_digest(node):
    """Calcula SHA-256 digest de un nodo usando exc-c14n."""
    c14n = etree.tostring(node, method="c14n", exclusive=True, with_comments=False)
    digest = hashlib.sha256(c14n).digest()
    return base64.b64encode(digest).decode('ascii')


def verify_xml_digest(xml_bytes):
    """
    Verifica que el DigestValue en la firma coincida con el digest real.
    
    Args:
        xml_bytes: Bytes del XML a verificar
        
    Returns:
        True si el digest es válido, False si hay mismatch
    """
    try:
        root = etree.fromstring(xml_bytes)
    except Exception as e:
        print(f"❌ Error parseando XML: {e}")
        return False
    
    # Encontrar Signature
    sig_nodes = root.xpath("//ds:Signature", namespaces=NS_MAP)
    if not sig_nodes:
        print("❌ No se encontró ds:Signature")
        return False
    
    sig = sig_nodes[0]
    
    # Encontrar Reference
    ref = sig.find(".//ds:Reference", namespaces=NS_MAP)
    if ref is None:
        print("❌ No se encontró ds:Reference")
        return False
    
    # Obtener URI
    uri = ref.get("URI")
    if not uri or not uri.startswith("#"):
        print("❌ Reference URI inválido")
        return False
    
    element_id = uri[1:]
    
    # Encontrar elemento referenciado
    referenced = root.xpath(f"//*[@Id='{element_id}']")
    if not referenced:
        print(f"❌ No se encontró elemento con Id='{element_id}'")
        return False
    
    # Obtener digest declarado
    digest_value = ref.find(".//ds:DigestValue", namespaces=NS_MAP)
    if digest_value is None or digest_value.text is None:
        print("❌ No se encontró ds:DigestValue")
        return False
    
    declared_digest = digest_value.text.strip()
    
    # Calcular digest real
    actual_digest = calculate_digest(referenced[0])
    
    # Comparar
    if declared_digest == actual_digest:
        print("✅ Digest válido - no hay mutaciones post-firma")
        return True
    else:
        print("❌ DIGEST MISMATCH - XML modificado después de firmar")
        print(f"   Declarado: {declared_digest[:32]}...")
        print(f"   Real:     {actual_digest[:32]}...")
        return False


def test_0160_digest_mismatch():
    """Test que verifica el fix 0160 - digest mismatch"""
    
    # Buscar XML firmado reciente en artifacts
    artifacts_dir = Path("tesaka-cv/artifacts")
    if not artifacts_dir.exists():
        print("❌ Directorio artifacts no encontrado")
        sys.exit(1)
    
    # Buscar el XML más reciente que contenga Signature
    xml_files = list(artifacts_dir.glob("*_SENT.xml")) + list(artifacts_dir.glob("*_from_zip.xml"))
    
    if not xml_files:
        print("❌ No se encontraron XML firmados para verificar")
        sys.exit(1)
    
    # Usar el más reciente
    xml_file = sorted(xml_files, key=lambda x: x.stat().st_mtime)[-1]
    print(f"🔍 Verificando digest en: {xml_file}")
    
    # Leer y verificar
    xml_bytes = xml_file.read_bytes()
    
    if verify_xml_digest(xml_bytes):
        print("✅ Test 0160 passed: digest válido")
        sys.exit(0)
    else:
        print("❌ Test 0160 failed: digest mismatch")
        sys.exit(1)


if __name__ == "__main__":
    test_0160_digest_mismatch()
