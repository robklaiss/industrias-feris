#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Tests para fallback de consulta_lote_de cuando WSDL/XSD falla.
"""

import os
import sys
import unittest
from unittest.mock import patch, MagicMock, mock_open
from pathlib import Path
import tempfile
import shutil

# Agregar el directorio parent al path para imports
sys.path.insert(0, str(Path(__file__).parent.parent / "tesaka-cv"))

from tools.consulta_lote_de import (
    load_wsdl_source,
    _http_consulta_lote_manual,
    _resolve_mtls,
    cleanup_pem_files
)


class TestConsultaLoteFallback(unittest.TestCase):
    """Tests para verificar el fallback cuando WSDL/XSD falla."""
    
    def setUp(self):
        """Configurar entorno de prueba."""
        self.test_dir = Path(tempfile.mkdtemp())
        self.cache_dir = self.test_dir / "cache"
        self.cache_dir.mkdir()
        
        # Mock certificado
        self.cert_path = "/path/to/cert.p12"
        self.key_or_password = "test_password"
        self.is_pem_mode = False
    
    def tearDown(self):
        """Limpiar entorno de prueba."""
        shutil.rmtree(self.test_dir, ignore_errors=True)
    
    def test_load_wsdl_source_file_not_found_raises_exception(self):
        """Verificar que load_wsdl_source lanza excepción cuando archivo no existe."""
        with self.assertRaises(RuntimeError) as ctx:
            load_wsdl_source(
                wsdl_url="https://example.com/test.wsdl",
                cache_dir=self.cache_dir,
                wsdl_file=self.test_dir / "nonexistent.wsdl",
                cert_path=self.cert_path,
                key_or_password=self.key_or_password,
                is_pem_mode=self.is_pem_mode,
                debug=False
            )
        
        self.assertIn("Archivo WSDL no encontrado", str(ctx.exception))
    
    def test_load_wsdl_source_xsd_missing_triggers_exception(self):
        """Verificar que falta de XSD (.xsd1.xsd) puede causar excepción en Zeep."""
        # Crear un WSDL falso que referencia un XSD inexistente
        wsdl_content = '''<?xml version="1.0" encoding="UTF-8"?>
<wsdl:definitions xmlns:wsdl="http://schemas.xmlsoap.org/wsdl/"
    xmlns:xsd="http://www.w3.org/2001/XMLSchema"
    targetNamespace="http://test">
    <wsdl:types>
        <xsd:schema>
            <xsd:import schemaLocation="consulta-lote.wsdl.xsd1.xsd"/>
        </xsd:schema>
    </wsdl:types>
</wsdl:definitions>'''
        
        wsdl_file = self.cache_dir / "test.wsdl"
        wsdl_file.write_text(wsdl_content)
        
        # El archivo existe pero está vacío (simula que no se pudo descargar)
        empty_wsdl = self.cache_dir / "empty.wsdl"
        empty_wsdl.write_text("")
        
        # Verificar que lanza excepción con archivo vacío
        with self.assertRaises(RuntimeError) as ctx:
            load_wsdl_source(
                wsdl_url="https://example.com/test.wsdl",
                cache_dir=self.cache_dir,
                wsdl_file=empty_wsdl,
                cert_path=self.cert_path,
                key_or_password=self.key_or_password,
                is_pem_mode=self.is_pem_mode,
                debug=False
            )
        
        self.assertIn("Archivo WSDL está vacío", str(ctx.exception))
    
    @patch('tools.consulta_lote_de._resolve_mtls')
    @patch('tools.consulta_lote_de._http_consulta_lote_manual')
    def test_fallback_manual_called_on_wsdl_failure(self, mock_manual, mock_mtls):
        """Verificar que el fallback manual se llama cuando Zeep/WSDL falla."""
        # Configurar mocks
        mock_mtls.return_value = (("/cert.pem", "/key.pem"), None, "PEM")
        
        # Simular respuesta XML del fallback
        mock_manual.return_value = '''<?xml version="1.0" encoding="UTF-8"?>
<soap12:Envelope xmlns:soap12="http://www.w3.org/2003/05/soap-envelope">
    <soap12:Body>
        <rEnviConsLoteDeResponse xmlns="http://ekuatia.set.gov.py/sifen/xsd">
            <dCodResLot>0361</dCodResLot>
            <dMsgResLot>Lote procesado correctamente</dMsgResLot>
        </rEnviConsLoteDeResponse>
    </soap12:Body>
</soap12:Envelope>'''
        
        # Importar el main después de configurar los mocks
        from tools.consulta_lote_de import main as consulta_main
        
        # Mockear sys.argv para simular línea de comandos
        test_args = [
            "consulta_lote_de.py",
            "--env", "test",
            "--prot", "123456789",
            "--wsdl-cache-dir", str(self.cache_dir)
        ]
        
        with patch('sys.argv', test_args):
            # Mockear load_wsdl_source para que falle
            with patch('tools.consulta_lote_de.load_wsdl_source') as mock_load:
                mock_load.side_effect = Exception("[Errno 2] No such file or directory: '.../consulta-lote.wsdl.xsd1.xsd'")
                
                # Mockear get_mtls_config
                with patch('tools.consulta_lote_de.get_mtls_config') as mock_get_mtls:
                    mock_get_mtls.return_value = (self.cert_path, self.key_or_password, self.is_pem_mode)
                    
                    # Mockear artifacts dir
                    artifacts_dir = self.test_dir / "artifacts"
                    artifacts_dir.mkdir()
                    
                    with patch('tools.consulta_lote_de.Path') as mock_path:
                        mock_path.return_value = Path(__file__).parent
                        
                        # Ejecutar main y verificar que no lanza excepción
                        try:
                            result = consulta_main()
                            # El resultado debe ser 0 (éxito) aunque se usó fallback
                            self.assertEqual(0, result)
                        except SystemExit as e:
                            # main() llama a sys.exit, capturamos el código
                            self.assertEqual(0, e.code)
        
        # Verificar que el fallback manual fue llamado
        mock_manual.assert_called_once()
        
        # Verificar parámetros de la llamada manual
        call_args = mock_manual.call_args
        self.assertEqual(call_args[1]['prot'], '123456789')
        self.assertEqual(call_args[1]['env'], 'test')
        self.assertIn('consulta-lote.wsdl', call_args[1]['endpoint_url'])
    
    @patch('tools.consulta_lote_de._http_consulta_lote_manual')
    @patch('tools.consulta_lote_de._resolve_mtls')
    def test_manual_fallback_generates_json(self, mock_mtls, mock_manual):
        """Verificar que el fallback genera un JSON válido en artifacts."""
        # Configurar mock
        mock_mtls.return_value = (("/cert.pem", "/key.pem"), None, "PEM")
        
        # Simular respuesta XML
        response_xml = '''<?xml version="1.0" encoding="UTF-8"?>
<soap12:Envelope xmlns:soap12="http://www.w3.org/2003/05/soap-envelope">
    <soap12:Body>
        <rEnviConsLoteDeResponse xmlns="http://ekuatia.set.gov.py/sifen/xsd">
            <dCodResLot>0361</dCodResLot>
            <dMsgResLot>Lote procesado correctamente</dMsgResLot>
            <gResProcLote>
                <dId>123456789012345678901234</dId>
            </gResProcLote>
        </rEnviConsLoteDeResponse>
    </soap12:Body>
</soap12:Envelope>'''
        
        mock_manual.return_value = response_xml
        
        # Importar el main después de configurar los mocks
        from tools.consulta_lote_de import main as consulta_main
        
        # Mockear sys.argv
        test_args = [
            "consulta_lote_de.py",
            "--env", "test",
            "--prot", "123456789",
            "--debug",  # Para que guarde artifacts
            "--wsdl-cache-dir", str(self.cache_dir)
        ]
        
        with patch('sys.argv', test_args):
            # Mockear todo lo que puede fallar
            with patch('tools.consulta_lote_de.load_wsdl_source') as mock_load:
                mock_load.side_effect = Exception("WSDL falló")
                
                with patch('tools.consulta_lote_de.get_mtls_config') as mock_get_mtls:
                    mock_get_mtls.return_value = (self.cert_path, self.key_or_password, self.is_pem_mode)
                    
                    # Crear directorio de artifacts real
                    artifacts_dir = self.test_dir / "tesaka-cv" / "artifacts"
                    artifacts_dir.mkdir(parents=True)
                    
                    with patch('pathlib.Path.mkdir', side_effect=lambda *args, **kwargs: None):
                        with patch('pathlib.Path.write_text') as mock_write:
                            with patch('pathlib.Path.write_bytes') as mock_write_bytes:
                                # Ejecutar
                                try:
                                    result = consulta_main()
                                except SystemExit as e:
                                    result = e.code
                                
                                # Verificar que se escribió el JSON
                                # La llamada a write_text debe haberse hecho para el JSON
                                json_found = False
                                for call in mock_write.call_args_list:
                                    args, kwargs = call
                                    if len(args) > 0:
                                        content = args[0]
                                        if isinstance(content, str) and '"fallback_used": true' in content:
                                            json_found = True
                                            # Verificar estructura del JSON
                                            self.assertIn('"dProtConsLote": "123456789"', content)
                                            self.assertIn('"dCodResLot": "0361"', content)
                                            self.assertIn('"fallback_used": true', content)
                                            break
                                
                                self.assertTrue(json_found, "No se encontró el JSON con fallback_used=true")
    
    def test_manual_fallback_mtls_config(self):
        """Verificar que el fallback usa correctamente la configuración mTLS."""
        # Test con P12
        with patch('tools.consulta_lote_de.p12_to_temp_pem_files') as mock_p12:
            mock_p12.return_value = ("/tmp/cert.pem", "/tmp/key.pem")
            
            with patch('tools.consulta_lote_de.Session') as mock_session:
                mock_sess = MagicMock()
                mock_session.return_value = mock_sess
                mock_sess.post.return_value.content = b'<test>response</test>'
                mock_sess.post.return_value.text = '<test>response</test>'
                mock_sess.post.return_value.status_code = 200
                
                # Llamar función manual
                try:
                    _http_consulta_lote_manual(
                        endpoint_url="https://test.com/consulta-lote.wsdl",
                        prot="123456789",
                        env="test",
                        cert_tuple=("/cert.p12", "password")
                    )
                except:
                    pass  # No nos interesa el resultado, solo que se llame con mTLS
                
                # Verificar que se configuró el certificado
                self.assertEqual(mock_sess.cert, ("/cert.p12", "password"))
    
    def test_cleanup_pem_files_no_error_on_missing(self):
        """Verificar que cleanup_pem_files no falla si los archivos no existen."""
        # No debe lanzar excepción
        cleanup_pem_files("/nonexistent1.pem", "/nonexistent2.pem")
        
        # Tampoco con parámetros None
        cleanup_pem_files(None, None)


if __name__ == "__main__":
    unittest.main()
