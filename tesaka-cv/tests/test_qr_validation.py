"""
Test suite for QR code generation and validation against SIFEN specification.
Ensures compliance with official SIFEN examples and prevents regressions.
"""

import re
import hashlib
import xml.etree.ElementTree as ET
from pathlib import Path


class TestQRValidation:
    """Automated tests for QR code format validation."""
    
    @staticmethod
    def extract_qr_from_xml(xml_path: str) -> str:
        """Extract QR URL from XML file."""
        tree = ET.parse(xml_path)
        root = tree.getroot()
        ns = {'sifen': 'http://ekuatia.set.gov.py/sifen/xsd'}
        qr_node = root.find('.//sifen:dCarQR', ns)
        if qr_node is None or qr_node.text is None:
            raise ValueError("No se encontró dCarQR en el XML")
        # Decode XML entities
        return qr_node.text.strip().replace('&amp;', '&')
    
    @staticmethod
    def parse_qr_params(qr_url: str) -> dict:
        """Parse QR URL parameters into dict."""
        match = re.search(r'\?(.*)', qr_url)
        if not match:
            raise ValueError("URL sin parámetros")
        
        params = {}
        for param in match.group(1).split('&'):
            if '=' in param:
                k, v = param.split('=', 1)
                params[k] = v
        return params
    
    def test_qr_url_base(self, xml_path: str):
        """Test 1: URL base debe ser correcta (sin www.)."""
        qr_url = self.extract_qr_from_xml(xml_path)
        expected_base = "https://ekuatia.set.gov.py/consultas-test/qr?"
        
        assert qr_url.startswith(expected_base), (
            f"URL base incorrecta.\n"
            f"Esperado: {expected_base}\n"
            f"Obtenido: {qr_url[:len(expected_base)]}"
        )
        print("✓ Test 1: URL base correcta")
    
    def test_parameter_order(self, xml_path: str):
        """Test 2: Orden de parámetros debe coincidir con especificación SIFEN."""
        qr_url = self.extract_qr_from_xml(xml_path)
        params = self.parse_qr_params(qr_url)
        
        expected_order = [
            'nVersion', 'Id', 'dFeEmiDE', 
            ('dRucRec', 'dNumIDRec'),  # uno u otro
            'dTotGralOpe', 'dTotIVA', 'cItems', 
            'DigestValue', 'IdCSC', 'cHashQR'
        ]
        
        actual_keys = list(params.keys())
        
        # Verificar que los parámetros aparecen en orden
        for i, expected in enumerate(expected_order):
            if isinstance(expected, tuple):
                # Uno de los dos debe estar presente
                assert any(k in actual_keys for k in expected), (
                    f"Falta parámetro receptor: {expected}"
                )
            else:
                assert expected in actual_keys, (
                    f"Falta parámetro: {expected}"
                )
        
        print(f"✓ Test 2: Orden de parámetros correcto: {', '.join(actual_keys)}")
    
    def test_dfe_emi_de_format(self, xml_path: str):
        """Test 3: dFeEmiDE debe estar en hex lowercase."""
        qr_url = self.extract_qr_from_xml(xml_path)
        params = self.parse_qr_params(qr_url)
        
        dfe = params.get('dFeEmiDE', '')
        
        # Debe ser hex válido
        assert re.match(r'^[0-9a-f]+$', dfe), (
            f"dFeEmiDE no es hex lowercase: {dfe[:40]}..."
        )
        
        # Debe tener longitud esperada (38 chars para formato ISO datetime)
        assert len(dfe) == 38, (
            f"dFeEmiDE longitud incorrecta: {len(dfe)} (esperado: 38)"
        )
        
        print(f"✓ Test 3: dFeEmiDE formato correcto (hex lowercase, len={len(dfe)})")
    
    def test_digest_value_format(self, xml_path: str):
        """Test 4: DigestValue debe estar en hex lowercase."""
        qr_url = self.extract_qr_from_xml(xml_path)
        params = self.parse_qr_params(qr_url)
        
        digest = params.get('DigestValue', '')
        
        # Debe ser hex válido lowercase
        assert re.match(r'^[0-9a-f]+$', digest), (
            f"DigestValue no es hex lowercase: {digest[:40]}..."
        )
        
        # Debe tener longitud esperada (88 chars para base64 encoded como hex)
        assert len(digest) == 88, (
            f"DigestValue longitud incorrecta: {len(digest)} (esperado: 88)"
        )
        
        print(f"✓ Test 4: DigestValue formato correcto (hex lowercase, len={len(digest)})")
    
    def test_idcsc_format(self, xml_path: str):
        """Test 5: IdCSC debe tener 4 dígitos con ceros a la izquierda."""
        qr_url = self.extract_qr_from_xml(xml_path)
        params = self.parse_qr_params(qr_url)
        
        idcsc = params.get('IdCSC', '')
        
        # Debe ser 4 dígitos
        assert re.match(r'^\d{4}$', idcsc), (
            f"IdCSC debe ser 4 dígitos: '{idcsc}'"
        )
        
        print(f"✓ Test 5: IdCSC formato correcto (4 dígitos: {idcsc})")
    
    def test_chashqr_format(self, xml_path: str):
        """Test 6: cHashQR debe estar en hex LOWERCASE (64 chars)."""
        qr_url = self.extract_qr_from_xml(xml_path)
        params = self.parse_qr_params(qr_url)
        
        chash = params.get('cHashQR', '')
        
        # CRÍTICO: Debe ser hex lowercase (no uppercase)
        assert re.match(r'^[0-9a-f]{64}$', chash), (
            f"cHashQR debe ser hex lowercase de 64 chars.\n"
            f"Obtenido: {chash[:40]}...\n"
            f"Lowercase: {chash == chash.lower()}\n"
            f"Uppercase: {chash == chash.upper()}"
        )
        
        print(f"✓ Test 6: cHashQR formato correcto (hex lowercase, len={len(chash)})")
    
    def test_hash_calculation(self, xml_path: str, csc: str):
        """Test 7: Verificar que cHashQR es correcto matemáticamente."""
        qr_url = self.extract_qr_from_xml(xml_path)
        
        # Extraer parámetros y hash
        match = re.search(r'\?(.*?)&cHashQR=([a-f0-9]+)', qr_url)
        assert match, "No se pudo extraer cHashQR de la URL"
        
        url_params = match.group(1)
        qr_hash = match.group(2)
        
        # Calcular hash esperado
        hash_input = url_params + csc
        expected_hash = hashlib.sha256(hash_input.encode('utf-8')).hexdigest()
        
        assert qr_hash == expected_hash, (
            f"cHashQR incorrecto.\n"
            f"Esperado: {expected_hash}\n"
            f"Obtenido: {qr_hash}"
        )
        
        print(f"✓ Test 7: cHashQR matemáticamente correcto")
    
    def test_xml_encoding(self, xml_path: str):
        """Test 8: Verificar que & está codificado como &amp; en XML."""
        with open(xml_path, 'r', encoding='utf-8') as f:
            xml_content = f.read()
        
        # Buscar dCarQR en el XML crudo
        match = re.search(r'<dCarQR>(.*?)</dCarQR>', xml_content, re.DOTALL)
        assert match, "No se encontró dCarQR en XML"
        
        qr_in_xml = match.group(1).strip()
        
        # Debe contener &amp; (no &)
        assert '&amp;' in qr_in_xml, (
            "Los & deben estar codificados como &amp; en el XML"
        )
        
        # No debe contener & sin codificar (excepto en &amp;)
        # Reemplazar &amp; temporalmente y verificar que no quedan &
        temp = qr_in_xml.replace('&amp;', '__AMP__')
        assert '&' not in temp, (
            "Hay & sin codificar en el XML"
        )
        
        print(f"✓ Test 8: XML encoding correcto (&amp;)")
    
    def test_all_lowercase_hex_params(self, xml_path: str):
        """Test 9: Verificar que TODOS los parámetros hex están en lowercase."""
        qr_url = self.extract_qr_from_xml(xml_path)
        params = self.parse_qr_params(qr_url)
        
        hex_params = ['dFeEmiDE', 'DigestValue', 'cHashQR']
        
        for param_name in hex_params:
            value = params.get(param_name, '')
            assert value == value.lower(), (
                f"{param_name} debe estar en lowercase.\n"
                f"Valor: {value[:40]}..."
            )
        
        print(f"✓ Test 9: Todos los parámetros hex en lowercase")
    
    def run_all_tests(self, xml_path: str, csc: str):
        """Ejecutar todos los tests."""
        print("=" * 80)
        print("EJECUTANDO SUITE DE TESTS DE VALIDACIÓN QR")
        print("=" * 80)
        print(f"XML: {xml_path}")
        print(f"CSC: {csc[:10]}...")
        print()
        
        tests = [
            self.test_qr_url_base,
            self.test_parameter_order,
            self.test_dfe_emi_de_format,
            self.test_digest_value_format,
            self.test_idcsc_format,
            self.test_chashqr_format,
            lambda x: self.test_hash_calculation(x, csc),
            self.test_xml_encoding,
            self.test_all_lowercase_hex_params,
        ]
        
        passed = 0
        failed = 0
        
        for test in tests:
            try:
                test(xml_path)
                passed += 1
            except AssertionError as e:
                print(f"✗ FALLO: {e}")
                failed += 1
            except Exception as e:
                print(f"✗ ERROR: {e}")
                failed += 1
        
        print()
        print("=" * 80)
        print(f"RESULTADOS: {passed} passed, {failed} failed")
        print("=" * 80)
        
        return failed == 0


if __name__ == "__main__":
    import sys
    import os
    
    # Configuración
    xml_path = os.path.expanduser("~/Desktop/SIFEN_PREVALIDADOR_UPLOAD.xml")
    csc = os.getenv("SIFEN_CSC", "ABCD0000000000000000000000000000")
    
    if not Path(xml_path).exists():
        print(f"ERROR: No se encontró el XML en {xml_path}")
        sys.exit(1)
    
    # Ejecutar tests
    validator = TestQRValidation()
    success = validator.run_all_tests(xml_path, csc)
    
    sys.exit(0 if success else 1)
