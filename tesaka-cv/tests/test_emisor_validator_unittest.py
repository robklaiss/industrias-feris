#!/usr/bin/env python3
"""
Tests unitarios para validación emisor vs certificado

Casos cubiertos:
1) Payload correcto (RUC y DV coinciden) -> no modifica nada
2) Payload con DV incorrecto -> auto-corrige dDVEmi y marca CDC para regenerar
3) Payload con RUC distinto -> rechaza con error claro
4) Payload sin dRucEm -> rechaza con error
5) Extracción de RUC/DV desde Subject/serialNumber del certificado

Ejecutar:
    python3 -m unittest tests.test_emisor_validator_unittest
    python3 -m unittest tests.test_emisor_validator_unittest -v
"""
import unittest
import sys
from pathlib import Path
from unittest.mock import Mock, patch, MagicMock

# Agregar directorio padre al path
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.sifen_client.emisor_validator import (
    extract_ruc_dv_from_cert,
    ensure_emisor_matches_cert_and_refresh_cdc,
    validate_emisor_in_xml,
    EmisorValidationError
)


class TestExtractRucDvFromCert(unittest.TestCase):
    """Tests para extracción de RUC/DV desde certificado"""
    
    def test_extract_ruc_dv_from_subject_with_dv(self):
        """Test extracción de RUC-DV desde Subject con formato RUC4554737-8"""
        # Mock del certificado
        mock_cert = Mock()
        mock_subject = Mock()
        mock_subject.rfc4514_string.return_value = "CN=Test,serialNumber=RUC4554737-8,O=Test Org"
        mock_cert.subject = mock_subject
        
        # Mock de pkcs12.load_key_and_certificates (importado dentro de la función)
        with patch('cryptography.hazmat.primitives.serialization.pkcs12.load_key_and_certificates') as mock_load:
            mock_load.return_value = (None, mock_cert, None)
            
            # Mock de Path.exists
            with patch('app.sifen_client.emisor_validator.Path.exists', return_value=True):
                # Mock de open
                with patch('builtins.open', create=True) as mock_open:
                    mock_open.return_value.__enter__.return_value.read.return_value = b'fake_p12_data'
                    
                    ruc, dv = extract_ruc_dv_from_cert("/fake/path.p12", "password")
                    
                    self.assertEqual(ruc, "4554737")
                    self.assertEqual(dv, "8")
    
    def test_extract_ruc_dv_from_subject_ci_format(self):
        """Test extracción de RUC-DV desde Subject con formato CI4554737"""
        mock_cert = Mock()
        mock_subject = Mock()
        mock_subject.rfc4514_string.return_value = "CN=Test,serialNumber=CI4554737,O=Test Org"
        mock_cert.subject = mock_subject
        
        with patch('cryptography.hazmat.primitives.serialization.pkcs12.load_key_and_certificates') as mock_load:
            mock_load.return_value = (None, mock_cert, None)
            
            with patch('app.sifen_client.emisor_validator.Path.exists', return_value=True):
                with patch('builtins.open', create=True) as mock_open:
                    mock_open.return_value.__enter__.return_value.read.return_value = b'fake_p12_data'
                    
                    ruc, dv = extract_ruc_dv_from_cert("/fake/path.p12", "password")
                    
                    self.assertEqual(ruc, "4554737")
                    # DV calculado: suma de dígitos % 10 = (4+5+5+4+7+3+7) % 10 = 35 % 10 = 5
                    self.assertEqual(dv, "5")
    
    def test_extract_ruc_dv_cert_not_found(self):
        """Test error cuando certificado no existe"""
        with patch('app.sifen_client.emisor_validator.Path.exists', return_value=False):
            with self.assertRaises(EmisorValidationError) as ctx:
                extract_ruc_dv_from_cert("/fake/path.p12", "password")
            
            self.assertIn("no encontrado", str(ctx.exception))
    
    def test_extract_ruc_dv_no_serial_number(self):
        """Test error cuando Subject no tiene serialNumber"""
        mock_cert = Mock()
        mock_subject = Mock()
        mock_subject.rfc4514_string.return_value = "CN=Test,O=Test Org"
        mock_cert.subject = mock_subject
        
        with patch('cryptography.hazmat.primitives.serialization.pkcs12.load_key_and_certificates') as mock_load:
            mock_load.return_value = (None, mock_cert, None)
            
            with patch('app.sifen_client.emisor_validator.Path.exists', return_value=True):
                with patch('builtins.open', create=True) as mock_open:
                    mock_open.return_value.__enter__.return_value.read.return_value = b'fake_p12_data'
                    
                    with self.assertRaises(EmisorValidationError) as ctx:
                        extract_ruc_dv_from_cert("/fake/path.p12", "password")
                    
                    self.assertIn("serialNumber", str(ctx.exception))


class TestEnsureEmisorMatchesCert(unittest.TestCase):
    """Tests para validación y corrección de emisor vs certificado"""
    
    def setUp(self):
        """Setup común para todos los tests"""
        # Mock de extract_ruc_dv_from_cert para devolver RUC 4554737-8
        self.patcher = patch(
            'app.sifen_client.emisor_validator.extract_ruc_dv_from_cert',
            return_value=("4554737", "8")
        )
        self.mock_extract = self.patcher.start()
    
    def tearDown(self):
        """Cleanup después de cada test"""
        self.patcher.stop()
    
    def test_payload_correcto_no_modifica(self):
        """Test 1: Payload con RUC y DV correctos -> no modifica nada"""
        payload = {
            "emisor": {
                "dRucEm": "4554737",
                "dDVEmi": "8"
            }
        }
        
        result = ensure_emisor_matches_cert_and_refresh_cdc(
            payload, "/fake/cert.p12", "password"
        )
        
        # No debe modificar nada
        self.assertEqual(result["emisor"]["dRucEm"], "4554737")
        self.assertEqual(result["emisor"]["dDVEmi"], "8")
        self.assertNotIn("_cdc_needs_refresh", result)
    
    def test_payload_dv_incorrecto_autocorrige(self):
        """Test 2: Payload con DV incorrecto -> auto-corrige y marca CDC para regenerar"""
        payload = {
            "emisor": {
                "dRucEm": "4554737",
                "dDVEmi": "5"  # Incorrecto, debería ser 8
            }
        }
        
        with self.assertLogs('app.sifen_client.emisor_validator', level='WARNING') as log:
            result = ensure_emisor_matches_cert_and_refresh_cdc(
                payload, "/fake/cert.p12", "password"
            )
            
            # Debe auto-corregir el DV
            self.assertEqual(result["emisor"]["dDVEmi"], "8")
            
            # Debe marcar CDC para regenerar
            self.assertTrue(result.get("_cdc_needs_refresh"))
            
            # Debe loggear WARNING
            self.assertTrue(any("AUTO-FIX" in msg for msg in log.output))
    
    def test_payload_ruc_distinto_rechaza(self):
        """Test 3: Payload con RUC distinto -> rechaza con error claro"""
        payload = {
            "emisor": {
                "dRucEm": "80012345",  # RUC distinto al del certificado
                "dDVEmi": "0"
            }
        }
        
        with self.assertRaises(EmisorValidationError) as ctx:
            ensure_emisor_matches_cert_and_refresh_cdc(
                payload, "/fake/cert.p12", "password"
            )
        
        # Debe mencionar ambos RUCs en el error
        error_msg = str(ctx.exception)
        self.assertIn("4554737", error_msg)  # RUC del certificado
        self.assertIn("80012345", error_msg)  # RUC del payload
        self.assertIn("no coincide", error_msg.lower())
    
    def test_payload_sin_druc_em_rechaza(self):
        """Test 4: Payload sin dRucEm -> rechaza con error"""
        payload = {
            "emisor": {
                "dDVEmi": "8"
            }
        }
        
        with self.assertRaises(EmisorValidationError) as ctx:
            ensure_emisor_matches_cert_and_refresh_cdc(
                payload, "/fake/cert.p12", "password"
            )
        
        self.assertIn("dRucEm", str(ctx.exception))
    
    def test_payload_sin_estructura_emisor_rechaza(self):
        """Test: Payload sin estructura 'emisor' -> rechaza con error"""
        payload = {
            "documento": {
                "numero": "123"
            }
        }
        
        with self.assertRaises(EmisorValidationError) as ctx:
            ensure_emisor_matches_cert_and_refresh_cdc(
                payload, "/fake/cert.p12", "password"
            )
        
        self.assertIn("emisor", str(ctx.exception).lower())
    
    def test_payload_dv_vacio_autocorrige(self):
        """Test: Payload con dDVEmi vacío -> auto-corrige"""
        payload = {
            "emisor": {
                "dRucEm": "4554737",
                "dDVEmi": ""  # Vacío
            }
        }
        
        with self.assertLogs('app.sifen_client.emisor_validator', level='WARNING'):
            result = ensure_emisor_matches_cert_and_refresh_cdc(
                payload, "/fake/cert.p12", "password"
            )
            
            # Debe auto-corregir el DV
            self.assertEqual(result["emisor"]["dDVEmi"], "8")
            self.assertTrue(result.get("_cdc_needs_refresh"))


class TestValidateEmisorInXml(unittest.TestCase):
    """Tests para validación de emisor en XML final"""
    
    def setUp(self):
        """Setup común para todos los tests"""
        # Mock de extract_ruc_dv_from_cert
        self.patcher = patch(
            'app.sifen_client.emisor_validator.extract_ruc_dv_from_cert',
            return_value=("4554737", "8")
        )
        self.mock_extract = self.patcher.start()
    
    def tearDown(self):
        """Cleanup después de cada test"""
        self.patcher.stop()
    
    def test_xml_correcto_valida_ok(self):
        """Test: XML con dRucEm/dDVEmi correctos -> valida OK"""
        xml_str = """<?xml version="1.0" encoding="UTF-8"?>
<rDE xmlns="http://ekuatia.set.gov.py/sifen/xsd">
    <DE Id="01045547378001001000000112025011234567890">
        <gDatGralOpe>
            <gEmis>
                <dRucEm>4554737</dRucEm>
                <dDVEmi>8</dDVEmi>
            </gEmis>
        </gDatGralOpe>
    </DE>
</rDE>"""
        
        # No debe lanzar excepción
        validate_emisor_in_xml(xml_str, "/fake/cert.p12", "password")
    
    def test_xml_dv_incorrecto_rechaza(self):
        """Test: XML con dDVEmi incorrecto -> rechaza"""
        xml_str = """<?xml version="1.0" encoding="UTF-8"?>
<rDE xmlns="http://ekuatia.set.gov.py/sifen/xsd">
    <DE Id="01045547378001001000000112025011234567890">
        <gDatGralOpe>
            <gEmis>
                <dRucEm>4554737</dRucEm>
                <dDVEmi>5</dDVEmi>
            </gEmis>
        </gDatGralOpe>
    </DE>
</rDE>"""
        
        with self.assertRaises(EmisorValidationError) as ctx:
            validate_emisor_in_xml(xml_str, "/fake/cert.p12", "password")
        
        error_msg = str(ctx.exception)
        self.assertIn("DV", error_msg)
        self.assertIn("no coincide", error_msg.lower())
    
    def test_xml_ruc_incorrecto_rechaza(self):
        """Test: XML con dRucEm incorrecto -> rechaza"""
        xml_str = """<?xml version="1.0" encoding="UTF-8"?>
<rDE xmlns="http://ekuatia.set.gov.py/sifen/xsd">
    <DE Id="01045547378001001000000112025011234567890">
        <gDatGralOpe>
            <gEmis>
                <dRucEm>80012345</dRucEm>
                <dDVEmi>0</dDVEmi>
            </gEmis>
        </gDatGralOpe>
    </DE>
</rDE>"""
        
        with self.assertRaises(EmisorValidationError) as ctx:
            validate_emisor_in_xml(xml_str, "/fake/cert.p12", "password")
        
        error_msg = str(ctx.exception)
        self.assertIn("RUC", error_msg)
        self.assertIn("no coincide", error_msg.lower())
    
    def test_xml_sin_druc_em_rechaza(self):
        """Test: XML sin dRucEm -> rechaza"""
        xml_str = """<?xml version="1.0" encoding="UTF-8"?>
<rDE xmlns="http://ekuatia.set.gov.py/sifen/xsd">
    <DE Id="01045547378001001000000112025011234567890">
        <gDatGralOpe>
            <gEmis>
                <dDVEmi>8</dDVEmi>
            </gEmis>
        </gDatGralOpe>
    </DE>
</rDE>"""
        
        with self.assertRaises(EmisorValidationError) as ctx:
            validate_emisor_in_xml(xml_str, "/fake/cert.p12", "password")
        
        self.assertIn("dRucEm", str(ctx.exception))


if __name__ == "__main__":
    unittest.main()
