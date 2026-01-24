#!/usr/bin/env python3
"""
Test de regresión para asegurar que follow_lote respeta el modo PEM y nunca
intenta convertir archivos .pem a P12.
"""
import os
import pytest
from unittest.mock import patch, MagicMock
from pathlib import Path

# Agregar el directorio tesaka-cv al path
import sys
sys.path.insert(0, str(Path(__file__).parents[1] / "tesaka-cv"))

from tools.consulta_lote_de import create_zeep_transport, _http_consulta_lote_manual, _resolve_mtls
from app.sifen_client.exceptions import SifenClientError


class TestFollowLoteMTLSRegression:
    """Test que asegura que follow_lote no intente convertir PEM a P12."""
    
    def test_create_zeep_transport_respects_pem_mode(self):
        """Verifica que create_zeep_transport no llame p12_to_temp_pem_files en modo PEM."""
        # Setup de ambiente en modo PEM
        with patch.dict(os.environ, {
            "SIFEN_CERT_PATH": "/path/to/cert.pem",
            "SIFEN_KEY_PATH": "/path/to/key.pem"
        }):
            # Mockear p12_to_temp_pem_files para detectar si se llama
            with patch('tools.consulta_lote_de.p12_to_temp_pem_files') as mock_p12:
                mock_p12.side_effect = Exception("No debería llamarse con archivos PEM")
                
                # Mockear Session para evitar conexión real
                with patch('tools.consulta_lote_de.Session') as mock_session:
                    mock_session_instance = MagicMock()
                    mock_session.return_value = mock_session_instance
                    
                    # Llamar a la función
                    try:
                        transport = create_zeep_transport(
                            "/path/to/cert.pem", 
                            "/path/to/key.pem", 
                            is_pem_mode=True
                        )
                    except Exception as e:
                        if "No debería llamarse" in str(e):
                            pytest.fail("create_zeep_transport intentó convertir PEM a P12")
                    
                    # Verificar que p12_to_temp_pem_files NO fue llamado
                    mock_p12.assert_not_called()
                    
                    # Verificar que session.cert se configuró con los archivos PEM directamente
                    assert mock_session_instance.cert == ("/path/to/cert.pem", "/path/to/key.pem")
    
    def test_http_consulta_lote_manual_uses_cert_tuple(self):
        """Verifica que _http_consulta_lote_manual use cert_tuple directamente."""
        # Mockear Session para evitar conexión real
        with patch('tools.consulta_lote_de.Session') as mock_session:
            mock_session_instance = MagicMock()
            mock_session.return_value = mock_session_instance
            mock_session_instance.post.return_value.content = b"<xml>test</xml>"
            mock_session_instance.post.return_value.text = "<xml>test</xml>"
            
            # Llamar a la función con cert_tuple PEM
            result = _http_consulta_lote_manual(
                endpoint_url="https://test.com",
                prot="123456789",
                env="test",
                cert_tuple=("/path/to/cert.pem", "/path/to/key.pem")
            )
            
            # Verificar que session.cert se configuró con cert_tuple
            assert mock_session_instance.cert == ("/path/to/cert.pem", "/path/to/key.pem")
    
    def test_resolve_mtls_helper_returns_pem_directly(self):
        """Verifica que _resolve_mtls retorne archivos PEM directamente en modo PEM."""
        # Mockear get_mtls_config para evitar verificar existencia de archivos
        with patch('tools.consulta_lote_de.get_mtls_config') as mock_config:
            mock_config.return_value = ("/path/to/cert.pem", "/path/to/key.pem", True)
            
            # Mockear p12_to_temp_pem_files
            with patch('tools.consulta_lote_de.p12_to_temp_pem_files') as mock_p12:
                mock_p12.side_effect = Exception("No debería llamarse en modo PEM")
                
                # Llamar al helper
                try:
                    cert_tuple, temp_files, mode = _resolve_mtls()
                except Exception as e:
                    if "No debería llamarse" in str(e):
                        pytest.fail("_resolve_mtls intentó convertir PEM a P12")
                
                # Verificaciones
                assert mode == "PEM"
                assert cert_tuple == ("/path/to/cert.pem", "/path/to/key.pem")
                assert temp_files is None
                mock_p12.assert_not_called()
    
    def test_resolve_mtls_helper_converts_p12(self):
        """Verifica que _resolve_mtls convierta P12 a PEM cuando corresponde."""
        # Mockear get_mtls_config para evitar verificar existencia de archivos
        with patch('tools.consulta_lote_de.get_mtls_config') as mock_config:
            mock_config.return_value = ("/path/to/cert.p12", "password123", False)
            
            # Mockear p12_to_temp_pem_files
            with patch('tools.consulta_lote_de.p12_to_temp_pem_files') as mock_p12:
                mock_p12.return_value = ("/tmp/cert.pem", "/tmp/key.pem")
                
                # Llamar al helper
                cert_tuple, temp_files, mode = _resolve_mtls()
                
                # Verificaciones
                assert mode == "P12"
                assert cert_tuple == ("/tmp/cert.pem", "/tmp/key.pem")
                assert temp_files == ("/tmp/cert.pem", "/tmp/key.pem")
                mock_p12.assert_called_once_with("/path/to/cert.p12", "password123")
    
    def test_integration_follow_lote_with_pem_env(self):
        """Test de integración simulando el flujo completo con variables PEM."""
        # Setup de ambiente en modo PEM
        with patch.dict(os.environ, {
            "SIFEN_CERT_PATH": "/path/to/cert.pem",
            "SIFEN_KEY_PATH": "/path/to/key.pem"
        }):
            # Mockear todas las dependencias externas
            with patch('tools.consulta_lote_de.p12_to_temp_pem_files') as mock_p12, \
                 patch('tools.consulta_lote_de.Session') as mock_session, \
                 patch('tools.consulta_lote_de.Client') as mock_client, \
                 patch('tools.consulta_lote_de.load_wsdl_source') as mock_wsdl:
                
                mock_p12.side_effect = Exception("No debería llamarse")
                mock_session_instance = MagicMock()
                mock_session.return_value = mock_session_instance
                mock_client_instance = MagicMock()
                mock_client.return_value = mock_client_instance
                
                # Simular llamada principal
                from tools.consulta_lote_de import main
                with patch('sys.argv', ['consulta_lote_de.py', '--env', 'test', '--prot', '123456789']):
                    try:
                        # Esto no debe lanzar excepción de conversión P12
                        # El test fallará si p12_to_temp_pem_files es llamado
                        main()
                    except SystemExit:
                        pass  # main() llama a sys.exit
                    except Exception as e:
                        if "No debería llamarse" in str(e):
                            pytest.fail("El flujo principal intentó convertir PEM a P12")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
