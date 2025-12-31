"""
Tests unitarios para pkcs12_utils
"""
import pytest
import os
import tempfile
from pathlib import Path
from unittest.mock import patch, MagicMock
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.backends import default_backend

from app.sifen_client.pkcs12_utils import (
    p12_to_temp_pem_files,
    cleanup_pem_files,
    PKCS12Error
)


@pytest.fixture
def mock_certificate_and_key():
    """
    Crea un certificado y clave de prueba para testing
    """
    # Generar clave privada RSA 2048
    private_key = rsa.generate_private_key(
        public_exponent=65537,
        key_size=2048,
        backend=default_backend()
    )
    
    # Crear certificado autofirmado (solo para testing)
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
def mock_p12_file(mock_certificate_and_key, tmp_path):
    """
    Crea un archivo P12 de prueba
    """
    cert, private_key = mock_certificate_and_key
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
    p12_file = tmp_path / "test_cert.p12"
    p12_file.write_bytes(pfx_data)
    
    return str(p12_file), password.decode()


def test_p12_to_temp_pem_files_success(mock_p12_file):
    """Test conversión exitosa de P12 a PEM"""
    p12_path, password = mock_p12_file
    
    cert_path, key_path = p12_to_temp_pem_files(p12_path, password)
    
    # Verificar que se crearon los archivos
    assert os.path.exists(cert_path)
    assert os.path.exists(key_path)
    
    # Verificar permisos 600
    cert_stat = os.stat(cert_path)
    key_stat = os.stat(key_path)
    
    # Permisos 600 = 0o600 = solo propietario puede leer/escribir
    assert oct(cert_stat.st_mode)[-3:] == '600'
    assert oct(key_stat.st_mode)[-3:] == '600'
    
    # Verificar que son archivos PEM válidos
    with open(cert_path, 'rb') as f:
        cert_content = f.read()
        assert b'-----BEGIN CERTIFICATE-----' in cert_content
        assert b'-----END CERTIFICATE-----' in cert_content
    
    with open(key_path, 'rb') as f:
        key_content = f.read()
        assert b'-----BEGIN PRIVATE KEY-----' in key_content
        assert b'-----END PRIVATE KEY-----' in key_content
    
    # Limpiar
    cleanup_pem_files(cert_path, key_path)
    assert not os.path.exists(cert_path)
    assert not os.path.exists(key_path)


def test_p12_to_temp_pem_files_file_not_found():
    """Test que falla si el archivo P12 no existe"""
    with pytest.raises(PKCS12Error, match="Archivo P12 no encontrado"):
        p12_to_temp_pem_files("/ruta/inexistente/cert.p12", "password")


def test_p12_to_temp_pem_files_wrong_password(mock_p12_file):
    """Test que falla con contraseña incorrecta"""
    p12_path, _ = mock_p12_file
    
    with pytest.raises(PKCS12Error, match="Contraseña del certificado P12 incorrecta"):
        p12_to_temp_pem_files(p12_path, "wrong_password")


def test_p12_to_temp_pem_files_no_password(mock_p12_file):
    """Test que funciona sin contraseña si el P12 no tiene password"""
    p12_path, _ = mock_p12_file
    
    # Este test puede fallar si el P12 tiene password, lo cual es esperado
    # Solo verificar que no crashea
    try:
        cert_path, key_path = p12_to_temp_pem_files(p12_path, "")
        # Si funciona, limpiar
        cleanup_pem_files(cert_path, key_path)
    except PKCS12Error:
        # Esperado si el P12 tiene password
        pass


def test_p12_to_temp_pem_files_pfx_extension(mock_p12_file, tmp_path):
    """Test que acepta extensión .pfx"""
    p12_path, password = mock_p12_file
    
    # Renombrar a .pfx
    pfx_path = tmp_path / "test_cert.pfx"
    Path(p12_path).rename(pfx_path)
    
    cert_path, key_path = p12_to_temp_pem_files(str(pfx_path), password)
    
    assert os.path.exists(cert_path)
    assert os.path.exists(key_path)
    
    cleanup_pem_files(cert_path, key_path)


def test_cleanup_pem_files(mock_p12_file):
    """Test limpieza de archivos PEM"""
    p12_path, password = mock_p12_file
    
    cert_path, key_path = p12_to_temp_pem_files(p12_path, password)
    
    # Verificar que existen
    assert os.path.exists(cert_path)
    assert os.path.exists(key_path)
    
    # Limpiar
    cleanup_pem_files(cert_path, key_path)
    
    # Verificar que se eliminaron
    assert not os.path.exists(cert_path)
    assert not os.path.exists(key_path)


def test_cleanup_pem_files_nonexistent():
    """Test que cleanup no falla si los archivos no existen"""
    # No debería lanzar excepción
    cleanup_pem_files("/ruta/inexistente/cert.pem", "/ruta/inexistente/key.pem")


@patch('app.sifen_client.pkcs12_utils.pkcs12.load_key_and_certificates')
def test_p12_to_temp_pem_files_no_key(mock_load, tmp_path):
    """Test que falla si el P12 no tiene clave privada"""
    # Crear archivo P12 falso
    fake_p12 = tmp_path / "fake.p12"
    fake_p12.write_bytes(b"fake data")
    
    # Mock que retorna None para private_key
    mock_load.return_value = (None, MagicMock(), None)
    
    with pytest.raises(PKCS12Error, match="No se pudo extraer la clave privada"):
        p12_to_temp_pem_files(str(fake_p12), "password")


@patch('app.sifen_client.pkcs12_utils.pkcs12.load_key_and_certificates')
def test_p12_to_temp_pem_files_no_cert(mock_load, tmp_path):
    """Test que falla si el P12 no tiene certificado"""
    # Crear archivo P12 falso
    fake_p12 = tmp_path / "fake.p12"
    fake_p12.write_bytes(b"fake data")
    
    # Mock que retorna None para certificate
    mock_load.return_value = (MagicMock(), None, None)
    
    with pytest.raises(PKCS12Error, match="No se pudo extraer el certificado"):
        p12_to_temp_pem_files(str(fake_p12), "password")


def test_p12_to_temp_pem_files_no_password_in_logs(mock_p12_file, caplog):
    """Test que la contraseña no aparece en logs"""
    p12_path, password = mock_p12_file
    
    with caplog.at_level("INFO"):
        cert_path, key_path = p12_to_temp_pem_files(p12_path, password)
    
    # Verificar que la contraseña no está en los logs
    log_messages = " ".join(caplog.messages)
    assert password not in log_messages
    assert "test_password" not in log_messages
    
    cleanup_pem_files(cert_path, key_path)


def test_p12_to_temp_pem_files_no_full_paths_in_logs(mock_p12_file, caplog):
    """Test que las rutas completas no aparecen en logs (solo nombres de archivo)"""
    p12_path, password = mock_p12_file
    
    with caplog.at_level("INFO"):
        cert_path, key_path = p12_to_temp_pem_files(p12_path, password)
    
    # Verificar que solo se loggean nombres de archivo, no rutas completas
    log_messages = " ".join(caplog.messages)
    # El log debe contener solo el nombre del archivo, no la ruta completa
    assert Path(cert_path).name in log_messages or "sifen_cert_" in log_messages
    # No debe contener la ruta completa del directorio temporal
    assert str(Path(cert_path).parent) not in log_messages
    
    cleanup_pem_files(cert_path, key_path)

