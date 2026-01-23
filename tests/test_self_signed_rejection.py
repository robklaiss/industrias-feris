#!/usr/bin/env python3
"""
Tests para validar que los certificados self-signed NUNCA se usen en runtime.

Estos tests verifican:
1. Que cert_resolver detecte y rechace self-signed
2. Que soap_client aborte si se intenta usar self-signed para mTLS
3. Que send_sirecepde aborte si se intenta usar self-signed para firma
"""
import os
import sys
import tempfile
import pytest
from pathlib import Path
from unittest.mock import patch

# Agregar project root al path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))
sys.path.insert(0, str(project_root / "tesaka-cv"))

from tools.cert_resolver import (
    validate_no_self_signed,
    resolve_signing_cert,
    resolve_mtls_cert,
    save_resolved_certs_artifact
)


class TestSelfSignedValidation:
    """Tests para validar rechazo de certificados self-signed"""
    
    def test_validate_no_self_signed_by_filename(self):
        """Detecta self-signed por nombre de archivo"""
        # Casos que deben fallar
        with pytest.raises(RuntimeError, match="self-signed"):
            validate_no_self_signed("/path/to/cert_selfsigned.p12", "firma")
        
        with pytest.raises(RuntimeError, match="self-signed"):
            validate_no_self_signed("certs/test_selfsigned.p12", "mTLS")
        
        with pytest.raises(RuntimeError, match="self-signed"):
            validate_no_self_signed("./self_signed_cert.p12", "firma")
        
        # Casos que deben pasar
        # No debe lanzar excepción
        validate_no_self_signed("/path/to/normal_cert.p12", "firma")
        validate_no_self_signed("certs/ekuatia_test.p12", "mTLS")
    
    def test_validate_no_self_signed_by_directory(self):
        """Detecta self-signed si está en directorio certs/"""
        with pytest.raises(RuntimeError, match="self-signed"):
            validate_no_self_signed("certs/mi_selfsigned.p12", "mTLS")
    
    @patch.dict(os.environ, {
        'SIFEN_SIGN_P12_PATH': 'certs/test_selfsigned.p12',
        'SIFEN_SIGN_P12_PASSWORD': 'password123'
    })
    def test_resolve_signing_cert_rejects_self_signed(self):
        """resolve_signing_cert debe rechazar self-signed"""
        # Mockear que el archivo existe
        with patch('pathlib.Path.exists', return_value=True):
            with pytest.raises(RuntimeError, match="self-signed"):
                resolve_signing_cert()
    
    @patch.dict(os.environ, {
        'SIFEN_CERT_PATH': 'certs/test_selfsigned.p12',
        'SIFEN_CERT_PASSWORD': 'password123'
    })
    def test_resolve_mtls_cert_rejects_self_signed(self):
        """resolve_mtls_cert debe rechazar self-signed"""
        with patch('pathlib.Path.exists', return_value=True):
            with pytest.raises(RuntimeError, match="self-signed"):
                resolve_mtls_cert()
    
    @patch.dict(os.environ, {
        'SIFEN_CERT_PATH': '/path/to/normal_cert.p12',
        'SIFEN_KEY_PATH': '/path/to/normal_key.pem'
    })
    def test_resolve_mtls_cert_pem_allows_normal(self):
        """resolve_mtls_cert permite certificados normales en modo PEM"""
        with patch('pathlib.Path.exists', return_value=True):
            cert_path, key_path, is_pem = resolve_mtls_cert()
            assert is_pem is True
            assert cert_path == '/path/to/normal_cert.p12'
            assert key_path == '/path/to/normal_key.pem'
    
    def test_save_resolved_certs_artifact(self):
        """Guarda artifact con info de certificados resueltos"""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Cambiar directorio de artifacts
            with patch('pathlib.Path.mkdir'):
                with patch('pathlib.Path.write_text') as mock_write:
                    artifact_path = save_resolved_certs_artifact(
                        signing_cert="/path/to/sign.p12",
                        mtls_cert="/path/to/mtls.p12",
                        mtls_mode="P12"
                    )
                    # Verificar que se llamó a write_text
                    assert mock_write.called
                    assert artifact_path.endswith('.json')


class TestSoapClientRejectsSelfSigned:
    """Tests para validar que soap_client rechaza self-signed"""
    
    @patch.dict(os.environ, {
        'SIFEN_CERT_PATH': 'certs/test_selfsigned.p12',
        'SIFEN_CERT_PASSWORD': 'password123'
    })
    def test_soap_client_create_transport_rejects_self_signed(self):
        """SoapClient._create_transport debe abortar con self-signed"""
        from app.sifen_client.soap_client import SoapClient
        from app.sifen_client.config import get_sifen_config
        
        # Mockear Path.exists para que no falle por archivo inexistente
        with patch('pathlib.Path.exists', return_value=True):
            config = get_sifen_config(env="test")
            client = SoapClient(config)
            
            with pytest.raises(RuntimeError, match="self-signed"):
                client._create_transport()


class TestSendSirecepdeRejectsSelfSigned:
    """Tests para validar que send_sirecepde rechaza self-signed"""
    
    def test_build_and_sign_lote_rejects_self_signed(self):
        """build_and_sign_lote_from_xml debe abortar con self-signed"""
        from tools.send_sirecepde import build_and_sign_lote_from_xml
        
        # XML mínimo válido
        xml_bytes = b'<rDE xmlns="http://ekuatia.set.gov.py/sifen/xsd"><DE Id="DE1"></DE></rDE>'
        
        with pytest.raises(RuntimeError, match="self-signed"):
            build_and_sign_lote_from_xml(
                xml_bytes=xml_bytes,
                cert_path="certs/test_selfsigned.p12",
                cert_password="password123"
            )


if __name__ == "__main__":
    # Ejecutar tests
    pytest.main([__file__, "-v"])
