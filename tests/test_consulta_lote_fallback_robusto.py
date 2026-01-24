#!/usr/bin/env python3
"""
Test anti-regresión para fallback manual de consulta_lote con RemoteDisconnected.

Este test simula un error RemoteDisconnected en el POST del fallback manual
y verifica que:
1. Se genera JSON con ok:false y fallback_used:true
2. main() no aborta antes de guardar el JSON
3. Se intentan ambos endpoints (con .wsdl y sin .wsdl)
4. Se hacen hasta 3 retries con backoff
"""

import pytest
import json
import tempfile
import unittest.mock as mock
from pathlib import Path
from unittest.mock import patch, MagicMock
import sys

# Agregar el directorio padre al path para imports
sys.path.insert(0, str(Path(__file__).parent.parent / "tesaka-cv"))

from tools.consulta_lote_de import main, _http_consulta_lote_manual


class TestConsultaLoteFallback:
    """Test del fallback manual con errores de conexión."""

    def test_fallback_remote_disconnected_generates_json(self):
        """Test que RemoteDisconnected genera JSON con ok:false."""
        
        # Mock para simular RemoteDisconnected
        def mock_post_remote_disconnected(*args, **kwargs):
            from requests.exceptions import ConnectionError
            raise ConnectionError("RemoteDisconnected('Remote end closed connection without response')")
        
        # Mock para get_mtls_config
        def mock_get_mtls_config():
            return ("/fake/cert.pem", "/fake/key.pem", True)
        
        # Crear directorio temporal para artifacts
        with tempfile.TemporaryDirectory() as tmpdir:
            artifacts_dir = Path(tmpdir) / "artifacts"
            artifacts_dir.mkdir()
            
            # Mockear sys.argv
            test_args = [
                "consulta_lote_de.py",
                "--env", "test",
                "--prot", "123456789",
                "--wsdl-cache-dir", str(artifacts_dir)
            ]
            
            with patch.object(sys, 'argv', test_args):
                with patch('requests.Session.post', side_effect=mock_post_remote_disconnected):
                    with patch('tools.consulta_lote_de.get_mtls_config', side_effect=mock_get_mtls_config):
                        with patch('tools.consulta_lote_de.load_wsdl_source') as mock_load_wsdl:
                            # Hacer que falle la carga del WSDL para forzar fallback
                            mock_load_wsdl.side_effect = Exception("WSDL falló intencionalmente")
                            
                            # Ejecutar main - debería generar JSON aunque todo falle
                            result = main()
                            
                            # Verificar que el exit code no sea 2 (que indicaría aborto antes de guardar JSON)
                            assert result == 0, f"main() retornó {result}, se esperaba 0"
                            
                            # Verificar que se generó el JSON (en el directorio real de artifacts)
                            # El código usa artifacts_dir fijo: tesaka-cv/artifacts
                            real_artifacts_dir = Path(__file__).parent.parent / "tesaka-cv" / "artifacts"
                            json_files = list(real_artifacts_dir.glob("consulta_lote_*.json"))
                            assert len(json_files) > 0, "No se generó archivo JSON"
                            
                            # Leer y verificar contenido del JSON más reciente
                            json_files.sort(key=lambda p: p.stat().st_mtime, reverse=True)
                            json_file = json_files[0]
                            data = json.loads(json_file.read_text(encoding="utf-8"))
                            
                            # Verificar campos esperados
                            assert data["ok"] is False, "ok debe ser False"
                            assert data["fallback_used"] is True, "fallback_used debe ser True"
                            assert "dProtConsLote" in data, "debe contener dProtConsLote"
                            assert data["dProtConsLote"] == "123456789", "dProtConsLote debe coincidir"
                            assert data["rc"] == 2, "rc debe ser 2 para errores de conexión"
    
    def test_fallback_endpoint_fallback_behavior(self):
        """Test que el fallback intenta endpoint sin .wsdl si falla con .wsdl."""
        
        # Llamadas reales para verificar secuencia
        post_calls = []
        
        def mock_post_with_fallback(*args, **kwargs):
            post_calls.append(args[0])  # Guardar URL usada
            
            # Primera llamada (con .wsdl) falla
            if ".wsdl" in args[0] and len(post_calls) <= 3:
                from requests.exceptions import ConnectionError
                raise ConnectionError("RemoteDisconnected")
            
            # Segunda llamada (sin .wsdl) tiene éxito
            return MagicMock(
                status_code=200,
                headers={"Content-Type": "application/soap+xml"},
                content=b'''<?xml version="1.0" encoding="UTF-8"?>
<soap12:Envelope xmlns:soap12="http://www.w3.org/2003/05/soap-envelope">
    <soap12:Body>
        <ns0:rEnviConsLoteDeResponse xmlns:ns0="http://ekuatia.set.gov.py/sifen/xsd">
            <ns0:dCodResLot>0361</ns0:dCodResLot>
            <ns0:dMsgResLot>Lote procesado</ns0:dMsgResLot>
        </ns0:rEnviConsLoteDeResponse>
    </soap12:Body>
</soap12:Envelope>''',
                text='''<?xml version="1.0" encoding="UTF-8"?>
<soap12:Envelope xmlns:soap12="http://www.w3.org/2003/05/soap-envelope">
    <soap12:Body>
        <ns0:rEnviConsLoteDeResponse xmlns:ns0="http://ekuatia.set.gov.py/sifen/xsd">
            <ns0:dCodResLot>0361</ns0:dCodResLot>
            <ns0:dMsgResLot>Lote procesado</ns0:dMsgResLot>
        </ns0:rEnviConsLoteDeResponse>
    </soap12:Body>
</soap12:Envelope>'''
            )
        
        # Mockear get_mtls_config
        def mock_get_mtls_config():
            return ("/fake/cert.pem", "/fake/key.pem", True)
        
        # Probar la función manual directamente
        cert_tuple = ("/fake/cert.pem", "/fake/key.pem")
        
        with patch('requests.Session.post', side_effect=mock_post_with_fallback):
            result = _http_consulta_lote_manual(
                endpoint_url="https://sifen-test.set.gov.py/de/ws/consultas/consulta-lote.wsdl",
                prot="123456789",
                env="test",
                cert_tuple=cert_tuple
            )
            
            # Verificar que se intentó ambos endpoints
            assert len(post_calls) >= 4, f"Se esperaban al menos 4 llamadas (3 con .wsdl, 1 sin), got {len(post_calls)}"
            assert any(".wsdl" not in url for url in post_calls), "Nunca se intentó endpoint sin .wsdl"
            
            # Verificar que la respuesta es exitosa
            assert "0361" in result, "La respuesta debe contener el código 0361"
    
    def test_fallback_retries_with_backoff(self):
        """Test que el fallback hace 3 retries con backoff."""
        
        import time
        call_times = []
        
        def mock_post_with_timing(*args, **kwargs):
            call_times.append(time.time())
            from requests.exceptions import ConnectionError
            raise ConnectionError("RemoteDisconnected")
        
        cert_tuple = ("/fake/cert.pem", "/fake/key.pem")
        
        with patch('requests.Session.post', side_effect=mock_post_with_timing):
            try:
                _http_consulta_lote_manual(
                    endpoint_url="https://sifen-test.set.gov.py/de/ws/consultas/consulta-lote.wsdl",
                    prot="123456789",
                    env="test",
                    cert_tuple=cert_tuple
                )
            except Exception:
                pass  # Se espera que falle después de todos los retries
        
        # Debe haber hecho 6 llamadas (3 a cada endpoint)
        assert len(call_times) == 6, f"Se esperaban 6 llamadas (3 a cada endpoint), got {len(call_times)}"
        
        # Verificar backoff (espera creciente)
        if len(call_times) >= 3:
            gap1 = call_times[1] - call_times[0]
            gap2 = call_times[2] - call_times[1]
            
            # Los gaps deben ser aproximadamente 1s y 2s (con tolerancia)
            assert 0.8 <= gap1 <= 1.2, f"Primer gap debería ser ~1s, fue {gap1}"
            assert 1.8 <= gap2 <= 2.2, f"Segundo gap debería ser ~2s, fue {gap2}"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
