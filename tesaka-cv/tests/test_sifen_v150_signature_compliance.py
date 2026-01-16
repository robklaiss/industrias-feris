#!/usr/bin/env python3
"""
Test de cumplimiento NT16 (MT v150) para firmas XMLDSig

Verifica que las firmas generadas cumplan estrictamente con:
- CanonicalizationMethod válido
- SignatureMethod: rsa-sha256/384/512
- DigestMethod: sha256/384/512
- Reference/@URI apunta a #<DE/@Id>
- Transforms: SOLO enveloped-signature

Ejecutar:
    python3 -m pytest tests/test_sifen_v150_signature_compliance.py -v
"""
import os
import sys
from pathlib import Path
import pytest

# Agregar directorio padre al path
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.sifen_client.xml_generator_v150 import create_rde_xml_v150
from app.sifen_client.xmldsig_signer import sign_de_xml, assert_sifen_v150_signature_shape, XMLDSigError

# Certificado de prueba (debe existir)
CERT_PATH = os.getenv("SIFEN_CERT_PATH", "/Users/robinklaiss/.sifen/certs/F1T_65478.p12")
CERT_PASS = os.getenv("SIFEN_CERT_PASS", "")


@pytest.mark.skipif(not Path(CERT_PATH).exists(), reason="Certificado no encontrado")
@pytest.mark.skipif(not CERT_PASS, reason="SIFEN_CERT_PASS no configurado")
def test_signature_complies_with_nt16():
    """
    Test principal: Genera XML, firma, y verifica cumplimiento NT16
    """
    # 1) Generar XML mínimo
    xml_unsigned = create_rde_xml_v150(
        ruc="4554737",
        dv_ruc="8",
        timbrado="12345678",
        establecimiento="001",
        punto_expedicion="001",
        numero_documento="0000001",
        tipo_documento="1",
    )
    
    assert xml_unsigned, "XML no generado"
    assert "<DE" in xml_unsigned, "XML no contiene elemento DE"
    
    # 2) Firmar XML
    signed_xml = sign_de_xml(xml_unsigned, CERT_PATH, CERT_PASS)
    
    assert signed_xml, "XML firmado vacío"
    assert "<ds:Signature" in signed_xml or "<Signature" in signed_xml, "XML no contiene firma"
    
    # 3) Validar cumplimiento NT16
    # Esta función lanza XMLDSigError si no cumple
    assert_sifen_v150_signature_shape(signed_xml)
    
    # Si llegamos aquí, el test pasó
    print("\n✅ Firma cumple con NT16 (MT v150)")


@pytest.mark.skipif(not Path(CERT_PATH).exists(), reason="Certificado no encontrado")
@pytest.mark.skipif(not CERT_PASS, reason="SIFEN_CERT_PASS no configurado")
def test_signature_method_is_rsa_sha256():
    """
    Test específico: SignatureMethod debe ser rsa-sha256
    """
    from lxml import etree
    
    xml_unsigned = create_rde_xml_v150(
        ruc="4554737",
        dv_ruc="8",
        timbrado="12345678",
        establecimiento="001",
        punto_expedicion="001",
        numero_documento="0000002",
        tipo_documento="1",
    )
    
    signed_xml = sign_de_xml(xml_unsigned, CERT_PATH, CERT_PASS)
    
    root = etree.fromstring(signed_xml.encode("utf-8"))
    ns = {"ds": "http://www.w3.org/2000/09/xmldsig#"}
    
    sig_methods = root.xpath("//ds:SignatureMethod/@Algorithm", namespaces=ns)
    assert sig_methods, "No se encontró SignatureMethod"
    
    sig_alg = sig_methods[0]
    assert sig_alg == "http://www.w3.org/2001/04/xmldsig-more#rsa-sha256", \
        f"SignatureMethod incorrecto: {sig_alg}"
    
    print(f"\n✅ SignatureMethod correcto: {sig_alg}")


@pytest.mark.skipif(not Path(CERT_PATH).exists(), reason="Certificado no encontrado")
@pytest.mark.skipif(not CERT_PASS, reason="SIFEN_CERT_PASS no configurado")
def test_canonicalization_method_is_valid():
    """
    Test específico: CanonicalizationMethod debe ser uno de los válidos NT16
    """
    from lxml import etree
    
    xml_unsigned = create_rde_xml_v150(
        ruc="4554737",
        dv_ruc="8",
        timbrado="12345678",
        establecimiento="001",
        punto_expedicion="001",
        numero_documento="0000003",
        tipo_documento="1",
    )
    
    signed_xml = sign_de_xml(xml_unsigned, CERT_PATH, CERT_PASS)
    
    root = etree.fromstring(signed_xml.encode("utf-8"))
    ns = {"ds": "http://www.w3.org/2000/09/xmldsig#"}
    
    c14n_methods = root.xpath("//ds:CanonicalizationMethod/@Algorithm", namespaces=ns)
    assert c14n_methods, "No se encontró CanonicalizationMethod"
    
    c14n_alg = c14n_methods[0]
    valid_c14n = [
        "http://www.w3.org/TR/2001/REC-xml-c14n-20010315",
        "http://www.w3.org/TR/2001/REC-xml-c14n-20010315#WithComments",
        "http://www.w3.org/2001/10/xml-exc-c14n",
        "http://www.w3.org/2001/10/xml-exc-c14n#WithComments",
    ]
    
    assert c14n_alg in valid_c14n, \
        f"CanonicalizationMethod inválido: {c14n_alg}. Válidos: {valid_c14n}"
    
    print(f"\n✅ CanonicalizationMethod válido: {c14n_alg}")


@pytest.mark.skipif(not Path(CERT_PATH).exists(), reason="Certificado no encontrado")
@pytest.mark.skipif(not CERT_PASS, reason="SIFEN_CERT_PASS no configurado")
def test_transforms_only_enveloped_signature():
    """
    Test específico: Transforms debe contener SOLO enveloped-signature
    """
    from lxml import etree
    
    xml_unsigned = create_rde_xml_v150(
        ruc="4554737",
        dv_ruc="8",
        timbrado="12345678",
        establecimiento="001",
        punto_expedicion="001",
        numero_documento="0000004",
        tipo_documento="1",
    )
    
    signed_xml = sign_de_xml(xml_unsigned, CERT_PATH, CERT_PASS)
    
    root = etree.fromstring(signed_xml.encode("utf-8"))
    ns = {"ds": "http://www.w3.org/2000/09/xmldsig#"}
    
    transforms = root.xpath("//ds:Transforms/ds:Transform/@Algorithm", namespaces=ns)
    assert transforms, "No se encontraron Transforms"
    
    assert len(transforms) == 1, \
        f"NT16 requiere EXACTAMENTE 1 Transform. Encontrados: {len(transforms)}: {transforms}"
    
    transform_alg = transforms[0]
    expected = "http://www.w3.org/2000/09/xmldsig#enveloped-signature"
    
    assert transform_alg == expected, \
        f"Transform incorrecto: {transform_alg}. Esperado: {expected}"
    
    print(f"\n✅ Transforms correcto: 1 transform (enveloped-signature)")


@pytest.mark.skipif(not Path(CERT_PATH).exists(), reason="Certificado no encontrado")
@pytest.mark.skipif(not CERT_PASS, reason="SIFEN_CERT_PASS no configurado")
def test_reference_uri_points_to_de_id():
    """
    Test específico: Reference/@URI debe apuntar a #<DE/@Id>
    """
    from lxml import etree
    
    xml_unsigned = create_rde_xml_v150(
        ruc="4554737",
        dv_ruc="8",
        timbrado="12345678",
        establecimiento="001",
        punto_expedicion="001",
        numero_documento="0000005",
        tipo_documento="1",
    )
    
    signed_xml = sign_de_xml(xml_unsigned, CERT_PATH, CERT_PASS)
    
    root = etree.fromstring(signed_xml.encode("utf-8"))
    ns = {"ds": "http://www.w3.org/2000/09/xmldsig#", "sifen": "http://ekuatia.set.gov.py/sifen/xsd"}
    
    # Obtener Reference/@URI
    ref_uris = root.xpath("//ds:Reference/@URI", namespaces=ns)
    assert ref_uris, "No se encontró Reference/@URI"
    ref_uri = ref_uris[0]
    
    # Obtener DE/@Id
    de_nodes = root.xpath("//sifen:DE", namespaces=ns)
    if not de_nodes:
        de_nodes = root.xpath("//DE")
    assert de_nodes, "No se encontró elemento DE"
    
    de_id = de_nodes[0].get("Id")
    assert de_id, "DE no tiene atributo Id"
    
    expected_uri = f"#{de_id}"
    assert ref_uri == expected_uri, \
        f"Reference/@URI incorrecto: {ref_uri}. Esperado: {expected_uri}"
    
    print(f"\n✅ Reference/@URI correcto: {ref_uri}")


@pytest.mark.skipif(not Path(CERT_PATH).exists(), reason="Certificado no encontrado")
@pytest.mark.skipif(not CERT_PASS, reason="SIFEN_CERT_PASS no configurado")
def test_digest_method_is_sha256():
    """
    Test específico: DigestMethod debe ser sha256
    """
    from lxml import etree
    
    xml_unsigned = create_rde_xml_v150(
        ruc="4554737",
        dv_ruc="8",
        timbrado="12345678",
        establecimiento="001",
        punto_expedicion="001",
        numero_documento="0000006",
        tipo_documento="1",
    )
    
    signed_xml = sign_de_xml(xml_unsigned, CERT_PATH, CERT_PASS)
    
    root = etree.fromstring(signed_xml.encode("utf-8"))
    ns = {"ds": "http://www.w3.org/2000/09/xmldsig#"}
    
    digest_methods = root.xpath("//ds:DigestMethod/@Algorithm", namespaces=ns)
    assert digest_methods, "No se encontró DigestMethod"
    
    digest_alg = digest_methods[0]
    valid_digest = [
        "http://www.w3.org/2001/04/xmlenc#sha256",
        "http://www.w3.org/2001/04/xmldsig-more#sha384",
        "http://www.w3.org/2001/04/xmlenc#sha512",
    ]
    
    assert digest_alg in valid_digest, \
        f"DigestMethod inválido: {digest_alg}. Válidos: {valid_digest}"
    
    print(f"\n✅ DigestMethod válido: {digest_alg}")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
