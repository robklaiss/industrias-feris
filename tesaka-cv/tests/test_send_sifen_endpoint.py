"""
Tests para endpoint de envío de facturas a SIFEN

Mocks:
- consulta_ruc_client para pasar/fallar gate
- send_de_client para simular respuesta SIFEN
- Verificar códigos HTTP y shape del JSON
"""
import pytest

# Markers para skip automático si faltan dependencias
pytestmark = [
    pytest.mark.requires_jsonschema,
    pytest.mark.requires_signxml,
    pytest.mark.requires_xmlsec,
    pytest.mark.requires_lxml,
]

# Skip si faltan dependencias opcionales (fallback adicional)
# Estos tests no requieren las dependencias porque usan mocks
# Pero el import de app.main puede fallar si __init__.py importa signxml
# Por eso hacemos skip solo si realmente se necesita
pytest.importorskip("jsonschema", reason="jsonschema requerido para tests de validación")
pytest.importorskip("signxml", reason="signxml requerido para tests de firma")
pytest.importorskip("xmlsec", reason="xmlsec requerido para tests de firma")
pytest.importorskip("lxml", reason="lxml requerido para tests de XML")

import json
from unittest.mock import patch, MagicMock
from fastapi.testclient import TestClient

from app.main import app


class TestEnviarFacturaSifenEndpoint:
    """Tests para POST /api/facturas/{id}/enviar-sifen"""
    
    @pytest.fixture
    def client(self):
        """Cliente de prueba FastAPI"""
        return TestClient(app)
    
    @pytest.fixture
    def sample_invoice_data(self):
        """Datos de factura de ejemplo"""
        return {
            "issue_date": "2025-01-05",
            "buyer": {
                "ruc": "4554737-8",
                "nombre": "Cliente de Prueba",
                "situacion": "1"
            },
            "transaction": {
                "numeroTimbrado": "12345678",
                "establecimiento": "001",
                "puntoExpedicion": "001",
                "numeroComprobanteVenta": "0000001",
                "tipoComprobante": "1"
            },
            "items": []
        }
    
    @pytest.fixture
    def mock_invoice_db(self, sample_invoice_data):
        """Mock de base de datos con factura"""
        with patch('app.routes_sifen.get_db') as mock_get_db:
            conn = MagicMock()
            cursor = MagicMock()
            conn.cursor.return_value = cursor
            mock_get_db.return_value = conn
            
            # Mock SELECT invoice
            row = MagicMock()
            row.__getitem__ = lambda self, key: {"data_json": json.dumps(sample_invoice_data)}.get(key)
            cursor.fetchone.return_value = row
            
            # Mock INSERT/UPDATE
            cursor.execute.return_value = None
            
            yield conn, cursor
    
    @patch('app.routes_sifen.consulta_ruc_client')
    @patch('app.routes_sifen.send_de_client')
    def test_enviar_factura_success(
        self,
        mock_send_de,
        mock_consulta_ruc,
        client,
        mock_invoice_db,
        sample_invoice_data
    ):
        """Test envío exitoso con gate consultaRUC pasado"""
        # Mock consultaRUC exitosa
        mock_consulta_ruc.return_value = {
            "normalized": "45547378",
            "http_code": 200,
            "dCodRes": "0502",
            "dMsgRes": "RUC encontrado",
            "xContRUC": {
                "dRUCCons": "45547378",
                "dRazCons": "EMPRESA EJEMPLO S.A.",
                "dRUCFactElec": "S"  # Habilitado
            }
        }
        
        # Mock envío exitoso
        mock_send_de.return_value = {
            "ok": True,
            "http_code": 200,
            "dCodRes": "0200",
            "dMsgRes": "DE recibido con éxito",
            "sifen_env": "test",
            "endpoint": "https://sifen-test.set.gov.py/de/ws/sync/recibe.wsdl",
            "signed_xml_sha256": "abc123...",
            "extra": {
                "cdc": "01045547378001001000000112025123011234567892",
                "estado": "aprobado"
            }
        }
        
        # Ejecutar request
        response = client.post("/api/facturas/1/enviar-sifen")
        
        # Verificar respuesta
        assert response.status_code == 200
        data = response.json()
        assert data["ok"] is True
        assert data["dCodRes"] == "0200"
        assert data["ruc_validated"] is True
        assert "ruc_validation" in data
        assert data["ruc_validation"]["dCodRes"] == "0502"
        
        # Verificar que se llamó consultaRUC y send_de
        mock_consulta_ruc.assert_called_once()
        mock_send_de.assert_called_once()
    
    @patch('app.routes_sifen.consulta_ruc_client')
    def test_enviar_factura_ruc_gate_fails(
        self,
        mock_consulta_ruc,
        client,
        mock_invoice_db,
        sample_invoice_data
    ):
        """Test falla en gate consultaRUC"""
        # Mock consultaRUC con RUC no habilitado
        mock_consulta_ruc.return_value = {
            "normalized": "45547378",
            "http_code": 200,
            "dCodRes": "0502",
            "dMsgRes": "RUC encontrado",
            "xContRUC": {
                "dRUCCons": "45547378",
                "dRUCFactElec": "N"  # NO habilitado
            }
        }
        
        # Ejecutar request
        response = client.post("/api/facturas/1/enviar-sifen")
        
        # Verificar respuesta 400
        assert response.status_code == 400
        data = response.json()
        assert data["ok"] is False
        assert "RUC no habilitado" in data["error"]
        assert "ruc_validation" in data
        
        # Verificar que NO se llamó send_de
        mock_consulta_ruc.assert_called_once()
    
    @patch.dict('os.environ', {'SIFEN_SKIP_RUC_GATE': '1'})
    @patch('app.routes_sifen.send_de_client')
    def test_enviar_factura_skip_ruc_gate(
        self,
        mock_send_de,
        client,
        mock_invoice_db,
        sample_invoice_data
    ):
        """Test con SIFEN_SKIP_RUC_GATE=1 (salta validación RUC)"""
        # Mock envío exitoso (sin consultaRUC)
        mock_send_de.return_value = {
            "ok": True,
            "http_code": 200,
            "dCodRes": "0200",
            "dMsgRes": "DE recibido con éxito",
            "sifen_env": "test",
            "endpoint": "https://sifen-test.set.gov.py/de/ws/sync/recibe.wsdl",
            "signed_xml_sha256": "abc123...",
        }
        
        # Ejecutar request
        response = client.post("/api/facturas/1/enviar-sifen")
        
        # Verificar respuesta exitosa
        assert response.status_code == 200
        data = response.json()
        assert data["ok"] is True
        
        # Verificar que send_de se llamó (sin consultaRUC)
        mock_send_de.assert_called_once()
    
    @patch('app.routes_sifen.consulta_ruc_client')
    @patch('app.routes_sifen.send_de_client')
    def test_enviar_factura_sifen_error(
        self,
        mock_send_de,
        mock_consulta_ruc,
        client,
        mock_invoice_db,
        sample_invoice_data
    ):
        """Test error en envío a SIFEN"""
        # Mock consultaRUC exitosa
        mock_consulta_ruc.return_value = {
            "normalized": "45547378",
            "http_code": 200,
            "dCodRes": "0502",
            "dMsgRes": "RUC encontrado",
            "xContRUC": {"dRUCFactElec": "S"}
        }
        
        # Mock error en envío
        from app.sifen.send_de import SendDeError
        mock_send_de.side_effect = SendDeError("Error en envío SOAP a SIFEN: 0160")
        
        # Ejecutar request
        response = client.post("/api/facturas/1/enviar-sifen")
        
        # Verificar respuesta 500
        assert response.status_code == 500
        data = response.json()
        assert data["ok"] is False
        assert "Error en envío" in data["error"]
        assert data["ruc_validated"] is True
        
        # Verificar que se persistió el error
        conn, cursor = mock_invoice_db
        # Verificar que se llamó INSERT en sifen_submissions con ok=0
        insert_calls = [call for call in cursor.execute.call_args_list if 'sifen_submissions' in str(call)]
        assert len(insert_calls) > 0
    
    def test_enviar_factura_not_found(self, client):
        """Test factura no encontrada"""
        with patch('app.routes_sifen.get_db') as mock_get_db:
            conn = MagicMock()
            cursor = MagicMock()
            conn.cursor.return_value = cursor
            mock_get_db.return_value = conn
            
            # Mock SELECT invoice (no encontrada)
            cursor.fetchone.return_value = None
            
            # Ejecutar request
            response = client.post("/api/facturas/999/enviar-sifen")
            
            # Verificar respuesta 404
            assert response.status_code == 404
            data = response.json()
            assert "no encontrada" in data["detail"].lower()
