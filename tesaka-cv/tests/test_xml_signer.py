"""
Tests unitarios para xml_signer
"""
import pytest
import tempfile
from pathlib import Path
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.backends import default_backend
from lxml import etree

from app.sifen_client.xml_signer import XmlSigner, XmlSignerError


@pytest.fixture
def sample_xml():
    """XML de ejemplo para firmar"""
    return """<?xml version="1.0" encoding="UTF-8"?>
<DE xmlns="http://ekuatia.set.gov.py/sifen/xsd">
    <dId>1</dId>
    <dFeEmi>20250129</dFeEmi>
    <gEmis>
        <dRucEm>4554737</dRucEm>
        <dDVEmi>8</dDVEmi>
        <dNomEmi>Marcio Ruben Feris Aguilera</dNomEmi>
    </gEmis>
</DE>"""


@pytest.fixture
def test_certificate_and_key():
    """
    Crea un certificado y clave de prueba para testing
    Nota: En producción, usar certificados reales emitidos por PSC
    """
    # Generar clave privada RSA 2048
    private_key = rsa.generate_private_key(
        public_exponent=65537,
        key_size=2048,
        backend=default_backend()
    )
    
    # Crear certificado autofirmado (solo para testing)
    from cryptography import x509
    from datetime import datetime, timedelta
    
    subject = issuer = x509.Name([
        x509.NameAttribute(x509.NameOID.COUNTRY_NAME, "PY"),
        x509.NameAttribute(x509.NameOID.STATE_OR_PROVINCE_NAME, "Asunción"),
        x509.NameAttribute(x509.NameOID.ORGANIZATION_NAME, "Test SIFEN"),
        x509.NameAttribute(x509.NameOID.COMMON_NAME, "4554737-8"),
    ])
    
    cert = x509.CertificateBuilder().subject_name(
        subject
    ).issuer_name(
        issuer
    ).public_key(
        private_key.public_key()
    ).serial_number(
        x509.random_serial_number()
    ).not_valid_before(
        datetime.utcnow()
    ).not_valid_after(
        datetime.utcnow() + timedelta(days=365)
    ).add_extension(
        x509.SubjectAlternativeName([
            x509.DNSName("test.sifen.py"),
        ]),
        critical=False,
    ).sign(private_key, hashes.SHA256(), default_backend())
    
    return cert, private_key


@pytest.fixture
def test_pfx_file(test_certificate_and_key, tmp_path):
    """
    Crea un archivo PFX de prueba
    """
    cert, private_key = test_certificate_and_key
    password = b"test_password"
    
    # Serializar a PKCS#12
    from cryptography.hazmat.primitives.serialization import pkcs12
    
    pfx_data = pkcs12.serialize_key_and_certificates(
        name=b"test_cert",
        key=private_key,
        cert=cert,
        cas=None,
        encryption_algorithm=serialization.BestAvailableEncryption(password)
    )
    
    # Guardar en archivo temporal
    pfx_file = tmp_path / "test_cert.pfx"
    pfx_file.write_bytes(pfx_data)
    
    return str(pfx_file), password.decode()


def test_xml_signer_init_missing_cert():
    """Test que falla si no se proporciona certificado"""
    with pytest.raises(XmlSignerError, match="Certificado no especificado"):
        XmlSigner()


def test_xml_signer_init_cert_not_found():
    """Test que falla si el certificado no existe"""
    with pytest.raises(XmlSignerError, match="Certificado no encontrado"):
        XmlSigner(cert_path="/ruta/inexistente/cert.pfx")


def test_xml_signer_load_certificate(test_pfx_file):
    """Test que carga correctamente un certificado PFX"""
    cert_path, password = test_pfx_file
    
    signer = XmlSigner(cert_path=cert_path, cert_password=password)
    
    assert signer.certificate is not None
    assert signer.private_key is not None
    assert signer.certificate.subject is not None


def test_xml_signer_validate_certificate(test_pfx_file):
    """Test que valida el certificado (fechas, algoritmo)"""
    cert_path, password = test_pfx_file
    
    signer = XmlSigner(cert_path=cert_path, cert_password=password)
    
    # El certificado debe estar válido
    info = signer.get_certificate_info()
    assert 'subject' in info
    assert 'issuer' in info
    assert 'not_valid_after' in info
    assert info['key_size'] == 2048


def test_xml_signer_sign(sample_xml, test_pfx_file):
    """Test que firma un XML correctamente"""
    cert_path, password = test_pfx_file
    
    signer = XmlSigner(cert_path=cert_path, cert_password=password)
    signed_xml = signer.sign(sample_xml)
    
    # Verificar que el XML firmado contiene la firma
    assert signed_xml is not None
    assert 'Signature' in signed_xml
    assert 'SignedInfo' in signed_xml
    assert 'ds:' in signed_xml or 'xmlns:ds' in signed_xml
    
    # Verificar que es XML válido
    root = etree.fromstring(signed_xml.encode('utf-8'))
    assert root is not None


def test_xml_signer_verify(sample_xml, test_pfx_file):
    """Test que verifica correctamente una firma"""
    cert_path, password = test_pfx_file
    
    signer = XmlSigner(cert_path=cert_path, cert_password=password)
    signed_xml = signer.sign(sample_xml)
    
    # Verificar la firma
    is_valid = signer.verify(signed_xml)
    assert is_valid is True


def test_xml_signer_verify_tampered(sample_xml, test_pfx_file):
    """Test que detecta cuando un XML firmado ha sido modificado"""
    cert_path, password = test_pfx_file
    
    signer = XmlSigner(cert_path=cert_path, cert_password=password)
    signed_xml = signer.sign(sample_xml)
    
    # Modificar el XML firmado
    tampered_xml = signed_xml.replace("<dId>1</dId>", "<dId>999</dId>")
    
    # La verificación debe fallar
    is_valid = signer.verify(tampered_xml)
    assert is_valid is False


def test_xml_signer_get_certificate_info(test_pfx_file):
    """Test que obtiene información del certificado"""
    cert_path, password = test_pfx_file
    
    signer = XmlSigner(cert_path=cert_path, cert_password=password)
    info = signer.get_certificate_info()
    
    assert 'subject' in info
    assert 'issuer' in info
    assert 'serial_number' in info
    assert 'not_valid_before' in info
    assert 'not_valid_after' in info
    assert 'key_size' in info
    assert info['key_size'] == 2048

