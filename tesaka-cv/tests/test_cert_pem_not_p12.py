#!/usr/bin/env python3
"""
Test anti-regresión para verificar que los certificados .pem no se traten como P12
"""
import os
import pytest
from unittest.mock import patch, MagicMock
from app.sifen_client.config import get_mtls_config


def test_pem_files_not_treated_as_p12():
    """Test que .pem/.crt/.key no se traten como P12 cuando falta SIFEN_KEY_PATH"""
    
    # Caso 1: SIFEN_CERT_PATH apunta a .pem sin SIFEN_KEY_PATH
    with patch.dict(os.environ, {
        'SIFEN_CERT_PATH': '/path/to/cert.pem',
        'SIFEN_CERT_PASSWORD': 'password'
    }, clear=True):
        with pytest.raises(RuntimeError) as exc_info:
            get_mtls_config()
        
        # Mensaje debe indicar que falta SIFEN_KEY_PATH
        assert "SIFEN_CERT_PATH" in str(exc_info.value)
        assert "SIFEN_KEY_PATH" in str(exc_info.value)
    
    # Caso 2: SIFEN_CERT_PATH apunta a .p12 sin SIFEN_KEY_PATH (debe funcionar)
    with patch.dict(os.environ, {
        'SIFEN_CERT_PATH': '/path/to/cert.p12',
        'SIFEN_CERT_PASSWORD': 'password'
    }, clear=True), patch('os.path.exists') as mock_exists:
        mock_exists.return_value = True
        cert_path, password, is_pem = get_mtls_config()
        assert cert_path == '/path/to/cert.p12'
        assert password == 'password'
        assert is_pem == False  # Modo P12
    
    # Caso 3: SIFEN_CERT_PATH apunta a .pfx sin SIFEN_KEY_PATH (debe funcionar)
    with patch.dict(os.environ, {
        'SIFEN_CERT_PATH': '/path/to/cert.pfx',
        'SIFEN_CERT_PASSWORD': 'password'
    }, clear=True), patch('os.path.exists') as mock_exists:
        mock_exists.return_value = True
        cert_path, password, is_pem = get_mtls_config()
        assert cert_path == '/path/to/cert.pfx'
        assert password == 'password'
        assert is_pem == False  # Modo P12
    
    # Caso 4: SIFEN_CERT_PATH apunta a .crt sin SIFEN_KEY_PATH
    with patch.dict(os.environ, {
        'SIFEN_CERT_PATH': '/path/to/cert.crt',
        'SIFEN_CERT_PASSWORD': 'password'
    }, clear=True):
        with pytest.raises(RuntimeError) as exc_info:
            get_mtls_config()
        
        assert "SIFEN_CERT_PATH" in str(exc_info.value)
        assert "SIFEN_KEY_PATH" in str(exc_info.value)
    
    # Caso 5: Configuración PEM completa (debe funcionar)
    with patch.dict(os.environ, {
        'SIFEN_CERT_PATH': '/path/to/cert.pem',
        'SIFEN_KEY_PATH': '/path/to/key.pem'
    }, clear=True), patch('os.path.exists') as mock_exists:
        mock_exists.return_value = True
        cert_path, key_path, is_pem = get_mtls_config()
        assert cert_path == '/path/to/cert.pem'
        assert key_path == '/path/to/key.pem'
        assert is_pem == True  # Modo PEM


def test_mtls_p12_priority():
    """Test que SIFEN_MTLS_P12_PATH tiene prioridad sobre SIFEN_CERT_PATH"""
    
    with patch.dict(os.environ, {
        'SIFEN_MTLS_P12_PATH': '/path/to/mtls.p12',
        'SIFEN_MTLS_P12_PASSWORD': 'mtls_pass',
        'SIFEN_CERT_PATH': '/path/to/cert.pem',  # No debe usarse
        'SIFEN_CERT_PASSWORD': 'cert_pass'
    }, clear=True), patch('os.path.exists') as mock_exists:
        mock_exists.return_value = True
        cert_path, password, is_pem = get_mtls_config()
        assert cert_path == '/path/to/mtls.p12'
        assert password == 'mtls_pass'
        assert is_pem == False  # Modo P12


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
