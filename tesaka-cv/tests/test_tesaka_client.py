"""
Tests para el cliente HTTP de Tesaka
"""
import json
import pytest
from unittest.mock import Mock, patch
import httpx

# Importar el cliente
import sys
from pathlib import Path
# Ajustar path según estructura del proyecto
project_root = Path(__file__).parent.parent
app_path = project_root / "tesaka-cv" / "app"
if not app_path.exists():
    app_path = project_root / "app"
sys.path.insert(0, str(app_path))
from tesaka_client import TesakaClient, TesakaClientError


class TestTesakaClient:
    """Tests para TesakaClient"""
    
    def test_init_valid_env(self):
        """Test que el cliente se inicializa correctamente con entorno válido"""
        client = TesakaClient(env='homo', user='test', password='test')
        assert client.env == 'homo'
        assert client.base_url == 'https://m2hom.set.gov.py/servicios-retenciones'
        assert client.user == 'test'
        assert client.password == 'test'
        client.close()
    
    def test_init_invalid_env(self):
        """Test que el cliente lanza error con entorno inválido"""
        with pytest.raises(ValueError, match="Entorno inválido"):
            TesakaClient(env='invalid')
    
    def test_enviar_facturas_success(self):
        """Test envío exitoso de facturas (200)"""
        payload = [{"atributos": {"fechaCreacion": "2025-01-01"}}]
        
        # Mock response
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"success": True, "message": "Factura recibida"}
        mock_response.text = ""
        
        # Mock client
        with patch('httpx.Client') as mock_client_class:
            mock_client = Mock()
            mock_client.request.return_value = mock_response
            mock_client_class.return_value = mock_client
            
            client = TesakaClient(env='homo', user='test', password='test')
            response = client.enviar_facturas(payload)
            
            assert response["success"] is True
            mock_client.request.assert_called_once()
            client.close()
    
    def test_enviar_facturas_401(self):
        """Test error de autenticación (401)"""
        payload = [{"atributos": {"fechaCreacion": "2025-01-01"}}]
        
        mock_response = Mock()
        mock_response.status_code = 401
        mock_response.text = "Unauthorized"
        
        with patch('httpx.Client') as mock_client_class:
            mock_client = Mock()
            mock_client.request.return_value = mock_response
            mock_client_class.return_value = mock_client
            
            client = TesakaClient(env='homo', user='test', password='test')
            
            with pytest.raises(TesakaClientError, match="autenticación"):
                client.enviar_facturas(payload)
            
            client.close()
    
    def test_enviar_facturas_500(self):
        """Test error del servidor (500)"""
        payload = [{"atributos": {"fechaCreacion": "2025-01-01"}}]
        
        mock_response = Mock()
        mock_response.status_code = 500
        mock_response.text = "Internal Server Error"
        
        with patch('httpx.Client') as mock_client_class:
            mock_client = Mock()
            mock_client.request.return_value = mock_response
            mock_client_class.return_value = mock_client
            
            client = TesakaClient(env='homo', user='test', password='test')
            
            with pytest.raises(TesakaClientError, match="Error del servidor"):
                client.enviar_facturas(payload)
            
            client.close()
    
    def test_enviar_facturas_timeout(self):
        """Test timeout en petición"""
        payload = [{"atributos": {"fechaCreacion": "2025-01-01"}}]
        
        with patch('httpx.Client') as mock_client_class:
            mock_client = Mock()
            mock_client.request.side_effect = httpx.TimeoutException("Timeout")
            mock_client_class.return_value = mock_client
            
            client = TesakaClient(env='homo', user='test', password='test', timeout=5)
            
            with pytest.raises(TesakaClientError, match="Timeout"):
                client.enviar_facturas(payload)
            
            client.close()
    
    def test_enviar_retenciones(self):
        """Test envío de retenciones"""
        payload = [{"atributos": {"fechaCreacion": "2025-01-01"}}]
        
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"success": True}
        mock_response.text = ""
        
        with patch('httpx.Client') as mock_client_class:
            mock_client = Mock()
            mock_client.request.return_value = mock_response
            mock_client_class.return_value = mock_client
            
            client = TesakaClient(env='homo', user='test', password='test')
            response = client.enviar_retenciones(payload)
            
            assert response["success"] is True
            # Verificar que se llamó al endpoint correcto
            call_args = mock_client.request.call_args
            # call_args[0] contiene los argumentos posicionales: (method, url)
            assert len(call_args[0]) >= 2  # Al menos method y url
            url_called = call_args[0][1]  # El segundo argumento posicional es la URL
            assert 'retenciones/guardar' in url_called
            client.close()
    
    def test_consultar_contribuyente(self):
        """Test consulta de contribuyente"""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"ruc": "1234567", "razonSocial": "Test SA"}
        mock_response.text = ""
        
        with patch('httpx.Client') as mock_client_class:
            mock_client = Mock()
            mock_client.request.return_value = mock_response
            mock_client_class.return_value = mock_client
            
            client = TesakaClient(env='homo', user='test', password='test')
            response = client.consultar_contribuyente("1234567")
            
            assert response["ruc"] == "1234567"
            client.close()
    
    def test_context_manager(self):
        """Test que el cliente funciona como context manager"""
        with TesakaClient(env='homo', user='test', password='test') as client:
            assert client.env == 'homo'
        # Al salir del contexto, close() debería haberse llamado
        # (no podemos verificar esto directamente sin mock, pero al menos no debería fallar)

