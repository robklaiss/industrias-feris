"""
Tests unitarios para verificar fallback a variables de entorno en mTLS
"""
import pytest
import os
from unittest.mock import patch, MagicMock
from pathlib import Path

from app.sifen_client.soap_client import SoapClient
from app.sifen_client.config import SifenConfig
from app.sifen_client.exceptions import SifenClientError


@pytest.fixture
def mock_config():
    """Configuración mock sin cert_path/cert_password"""
    config = MagicMock(spec=SifenConfig)
    config.use_mtls = True
    config.cert_path = None
    config.cert_password = None
    config.ca_bundle_path = None
    config.get_soap_service_url = MagicMock(return_value="https://test.wsdl")
    return config


@pytest.fixture
def mock_cert_file(tmp_path):
    """Crea un archivo de certificado mock"""
    cert_file = tmp_path / "test_cert.p12"
    cert_file.write_bytes(b"fake cert data")
    return str(cert_file)


def test_create_transport_fallback_to_env_vars(mock_config, mock_cert_file):
    """Test que _create_transport() usa variables de entorno cuando config no tiene cert_path"""
    with patch.dict(os.environ, {
        "SIFEN_CERT_PATH": mock_cert_file,
        "SIFEN_CERT_PASSWORD": "test_password"
    }):
        with patch('app.sifen_client.soap_client.get_mtls_config') as mock_get_mtls:
            mock_get_mtls.return_value = (mock_cert_file, "test_password", False)
            with patch('app.sifen_client.soap_client.p12_to_temp_pem_files') as mock_p12_to_pem:
                mock_p12_to_pem.return_value = ("/tmp/cert.pem", "/tmp/key.pem")
                
                client = SoapClient(mock_config)
                
                # Verificar que se llamó a p12_to_temp_pem_files con los valores de env
                mock_p12_to_pem.assert_called_once()
                call_args = mock_p12_to_pem.call_args[0]
                assert call_args[0] == mock_cert_file
                assert call_args[1] == "test_password"


def test_create_transport_uses_config_values(mock_config, mock_cert_file):
    """Test que _create_transport() usa valores de config si están disponibles"""
    mock_config.cert_path = mock_cert_file
    mock_config.cert_password = "config_password"
    
    with patch.dict(os.environ, {
        "SIFEN_CERT_PATH": "/other/path.p12",
        "SIFEN_CERT_PASSWORD": "env_password"
    }, clear=False):
        with patch('app.sifen_client.soap_client.get_mtls_config') as mock_get_mtls:
            mock_get_mtls.return_value = (mock_cert_file, "config_password", False)
            with patch('app.sifen_client.soap_client.p12_to_temp_pem_files') as mock_p12_to_pem:
                mock_p12_to_pem.return_value = ("/tmp/cert.pem", "/tmp/key.pem")
                
                client = SoapClient(mock_config)
                
                # Verificar que se usaron los valores de config, no de env
                mock_p12_to_pem.assert_called_once()
                call_args = mock_p12_to_pem.call_args[0]
                assert call_args[0] == mock_cert_file
                assert call_args[1] == "config_password"


def test_create_transport_missing_cert_path(mock_config):
    """Test que _create_transport() lanza error si falta cert_path"""
    with patch.dict(os.environ, {}, clear=True):
        with patch('app.sifen_client.soap_client.get_mtls_config') as mock_get_mtls:
            mock_get_mtls.side_effect = RuntimeError("ERROR: No se encontró configuración mTLS")
            with pytest.raises(RuntimeError) as exc_info:
                client = SoapClient(mock_config)
        
        assert "configuración mTLS" in str(exc_info.value)


def test_create_transport_missing_cert_password(mock_config, mock_cert_file):
    """Test que _create_transport() lanza error si falta cert_password"""
    with patch.dict(os.environ, {
        "SIFEN_CERT_PATH": mock_cert_file
        # SIFEN_CERT_PASSWORD no está
    }):
        with patch('app.sifen_client.soap_client.get_mtls_config') as mock_get_mtls:
            mock_get_mtls.side_effect = RuntimeError("ERROR: No se encontró configuración mTLS")
            with pytest.raises(RuntimeError) as exc_info:
                client = SoapClient(mock_config)
        
        assert "configuración mTLS" in str(exc_info.value)

