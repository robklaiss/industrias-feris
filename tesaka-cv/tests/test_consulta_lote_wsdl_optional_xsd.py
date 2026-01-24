#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Test anti-regresión: verifica que consulta_lote_de.py funcione aunque los XSDs no se puedan descargar.
"""

import os
import sys
import tempfile
import unittest
import unittest.mock as mock
from pathlib import Path
from unittest.mock import MagicMock, patch

# Agregar el directorio parent al path para imports
sys.path.insert(0, str(Path(__file__).parent))

from tools.consulta_lote_de import resolve_xsd_imports, load_wsdl_source, mtls_download


class TestConsultaLoteOptionalXSD(unittest.TestCase):
    """Test que el WSDL loading funciona aunque los XSDs fallen."""

    def setUp(self):
        """Crear directorio temporal para pruebas."""
        self.tmp_dir = Path(tempfile.mkdtemp(prefix="test_consulta_lote_"))
        self.cache_dir = self.tmp_dir / "cache"
        self.cache_dir.mkdir()
        
        # Crear un WSDL falso que contiene un import XSD
        self.wsdl_content = b"""<?xml version="1.0" encoding="UTF-8"?>
<wsdl:definitions xmlns:wsdl="http://schemas.xmlsoap.org/wsdl/"
                  xmlns:xsd="http://www.w3.org/2001/XMLSchema"
                  xmlns:soap="http://schemas.xmlsoap.org/wsdl/soap/"
                  targetNamespace="http://test.com">
    <wsdl:types>
        <xsd:schema>
            <xsd:import schemaLocation="consulta-lote.wsdl.xsd1.xsd"/>
        </xsd:schema>
    </wsdl:types>
</wsdl:definitions>"""
        
        self.wsdl_file = self.tmp_dir / "test.wsdl"
        self.wsdl_file.write_bytes(self.wsdl_content)
        
        # Certificados falsos
        self.cert_path = "/fake/cert.p12"
        self.key_or_password = "fake_password"
        self.is_pem_mode = False

    def tearDown(self):
        """Limpiar directorio temporal."""
        import shutil
        shutil.rmtree(self.tmp_dir)

    def test_resolve_xsd_imports_continues_on_download_failure(self):
        """Verificar que resolve_xsd_imports continúa aunque mtls_download falle."""
        
        # Mock de mtls_download para que siempre falle
        with patch('tools.consulta_lote_de.mtls_download') as mock_download:
            mock_download.side_effect = RuntimeError("Connection reset by peer")
            
            # Esto no debe lanzar excepción
            try:
                resolve_xsd_imports(
                    wsdl_path=self.wsdl_file,
                    wsdl_url="https://sifen-test.set.gov.py/de/ws/consultas/consulta-lote.wsdl?wsdl",
                    cache_dir=self.cache_dir,
                    cert_path=self.cert_path,
                    key_or_password=self.key_or_password,
                    is_pem_mode=self.is_pem_mode,
                    debug=True
                )
                # Si llegamos aquí, el test pasa
                success = True
            except Exception as e:
                success = False
                self.fail(f"resolve_xsd_imports no debería fallar: {e}")
        
        self.assertTrue(success, "resolve_xsd_imports debe continuar aunque falle la descarga")
        
        # Verificar que se intentó descargar el XSD
        mock_download.assert_called_once()
        
        # Verificar que el archivo XSD no existe (porque la descarga falló)
        xsd_file = self.cache_dir / "consulta-lote.wsdl.consulta-lote.wsdl.xsd1.xsd"
        self.assertFalse(xsd_file.exists(), "El XSD no debería existir si la descarga falló")

    def test_load_wsdl_source_works_without_xsd(self):
        """Verificar que load_wsdl_source funciona aunque no se puedan descargar los XSDs."""
        
        # Mock de mtls_download: el WSDL principal funciona, pero el XSD falla
        def mock_download(url, out_path, *args, **kwargs):
            if "consulta-lote.wsdl.xsd1.xsd" in url:
                # Fallar para el XSD
                raise RuntimeError("Connection reset by peer")
            else:
                # Funciona para el WSDL principal
                out_path.write_bytes(self.wsdl_content)
        
        with patch('tools.consulta_lote_de.mtls_download', side_effect=mock_download):
            # Esto debe retornar el path al WSDL aunque el XSD falle
            try:
                result_path = load_wsdl_source(
                    wsdl_url="https://sifen-test.set.gov.py/de/ws/consultas/consulta-lote.wsdl?wsdl",
                    cache_dir=self.cache_dir,
                    wsdl_file=None,
                    cert_path=self.cert_path,
                    key_or_password=self.key_or_password,
                    is_pem_mode=self.is_pem_mode,
                    debug=True
                )
                success = True
            except Exception as e:
                success = False
                self.fail(f"load_wsdl_source no debería fallar: {e}")
        
        self.assertTrue(success, "load_wsdl_source debe funcionar aunque el XSD falle")
        self.assertTrue(result_path.exists(), "El WSDL debe existir")
        self.assertEqual(result_path.name, "consulta-lote.wsdl.xml", "Debe retornar el WSDL cacheado")

    def test_load_wsdl_source_with_provided_file_ignores_xsd(self):
        """Verificar que con un WSDL provisto, los XSDs opcionales no afectan."""
        
        # Mock de mtls_download para que siempre falle
        with patch('tools.consulta_lote_de.mtls_download') as mock_download:
            mock_download.side_effect = RuntimeError("Connection reset by peer")
            
            # Usar un WSDL provisto (no descargar)
            try:
                result_path = load_wsdl_source(
                    wsdl_url="https://sifen-test.set.gov.py/de/ws/consultas/consulta-lote.wsdl?wsdl",
                    cache_dir=self.cache_dir,
                    wsdl_file=self.wsdl_file,
                    cert_path=self.cert_path,
                    key_or_password=self.key_or_password,
                    is_pem_mode=self.is_pem_mode,
                    debug=True
                )
                success = True
            except Exception as e:
                success = False
                self.fail(f"load_wsdl_source con archivo provisto no debería fallar: {e}")
        
        self.assertTrue(success, "load_wsdl_source con archivo provisto debe funcionar")
        self.assertEqual(result_path, self.wsdl_file, "Debe retornar el archivo provisto")
        
        # No debe intentar descargar nada cuando se provee un archivo
        mock_download.assert_not_called()

    def test_multiple_xsd_imports_some_fail(self):
        """Verificar el caso donde algunos XSDs descargan y otros fallan."""
        
        # Crear WSDL con múltiples imports
        wsdl_multiple = self.tmp_dir / "multiple.wsdl"
        wsdl_multiple.write_bytes(b"""<?xml version="1.0" encoding="UTF-8"?>
<wsdl:definitions xmlns:wsdl="http://schemas.xmlsoap.org/wsdl/"
                  xmlns:xsd="http://www.w3.org/2001/XMLSchema">
    <wsdl:types>
        <xsd:schema>
            <xsd:import schemaLocation="types1.xsd"/>
            <xsd:import schemaLocation="types2.xsd"/>
            <xsd:import schemaLocation="types3.xsd"/>
        </xsd:schema>
    </wsdl:types>
</wsdl:definitions>""")
        
        # Mock de mtls_download: types1 y types3 funcionan, types2 falla
        def mock_download(url, out_path, *args, **kwargs):
            if "types2.xsd" in url:
                raise RuntimeError("Connection reset by peer")
            else:
                out_path.write_bytes(b"<xsd:schema/>")
        
        with patch('tools.consulta_lote_de.mtls_download', side_effect=mock_download):
            # No debe fallar aunque types2.xsd no se pueda descargar
            try:
                resolve_xsd_imports(
                    wsdl_path=wsdl_multiple,
                    wsdl_url="https://test.com/test.wsdl",
                    cache_dir=self.cache_dir,
                    cert_path=self.cert_path,
                    key_or_password=self.key_or_password,
                    is_pem_mode=self.is_pem_mode,
                    debug=True
                )
                success = True
            except Exception as e:
                success = False
                self.fail(f"resolve_xsd_imports no debería fallar: {e}")
        
        self.assertTrue(success, "Debe continuar aunque algunos XSDs fallen")
        
        # Verificar que los XSDs que funcionaron sí existen
        self.assertTrue((self.cache_dir / "consulta-lote.wsdl.types1.xsd").exists())
        self.assertTrue((self.cache_dir / "consulta-lote.wsdl.types3.xsd").exists())
        
        # El que falló no debe existir
        self.assertFalse((self.cache_dir / "consulta-lote.wsdl.types2.xsd").exists())


if __name__ == "__main__":
    import unittest
    unittest.main(verbosity=2)
