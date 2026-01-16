"""
Tests para detección de ambiente QR y prevención de error 2502.
"""

import pytest
from app.sifen_client.qr_inspector import (
    extract_dcar_qr,
    detect_qr_env,
    extract_qr_params,
)


class TestQREnvDetection:
    """Tests para detección de ambiente del QR."""

    def test_detect_test_env(self):
        """Detecta correctamente ambiente TEST."""
        url = "https://ekuatia.set.gov.py/consultas-test/qr?nVersion=150&Id=123"
        assert detect_qr_env(url) == "TEST"

    def test_detect_prod_env(self):
        """Detecta correctamente ambiente PROD."""
        url = "https://ekuatia.set.gov.py/consultas/qr?nVersion=150&Id=123"
        assert detect_qr_env(url) == "PROD"

    def test_detect_prod_env_explicit(self):
        """Detecta correctamente ambiente PROD con sufijo explícito."""
        url = "https://ekuatia.set.gov.py/consultas-prod/qr?nVersion=150&Id=123"
        assert detect_qr_env(url) == "PROD"

    def test_detect_unknown_env(self):
        """Detecta UNKNOWN para URLs no reconocidas."""
        url = "https://example.com/qr?nVersion=150"
        assert detect_qr_env(url) == "UNKNOWN"

    def test_detect_none_url(self):
        """Maneja correctamente URL None."""
        assert detect_qr_env(None) == "UNKNOWN"

    def test_detect_empty_url(self):
        """Maneja correctamente URL vacía."""
        assert detect_qr_env("") == "UNKNOWN"


class TestQRExtraction:
    """Tests para extracción de QR desde XML."""

    def test_extract_qr_from_simple_xml(self):
        """Extrae QR desde XML simple."""
        xml = """<?xml version="1.0" encoding="UTF-8"?>
<rDE xmlns="http://ekuatia.set.gov.py/sifen/xsd">
    <gCamFuFD>
        <dCarQR>https://ekuatia.set.gov.py/consultas-test/qr?nVersion=150&amp;Id=123</dCarQR>
    </gCamFuFD>
</rDE>"""
        qr_url = extract_dcar_qr(xml)
        assert qr_url is not None
        assert "consultas-test" in qr_url

    def test_extract_qr_from_xml_without_namespace(self):
        """Extrae QR desde XML sin namespace explícito."""
        xml = """<?xml version="1.0" encoding="UTF-8"?>
<rDE>
    <gCamFuFD>
        <dCarQR>https://ekuatia.set.gov.py/consultas/qr?nVersion=150</dCarQR>
    </gCamFuFD>
</rDE>"""
        qr_url = extract_dcar_qr(xml)
        assert qr_url is not None
        assert "consultas/qr" in qr_url

    def test_extract_qr_missing(self):
        """Retorna None si no hay dCarQR."""
        xml = """<?xml version="1.0" encoding="UTF-8"?>
<rDE xmlns="http://ekuatia.set.gov.py/sifen/xsd">
    <DE Id="123"/>
</rDE>"""
        qr_url = extract_dcar_qr(xml)
        assert qr_url is None

    def test_extract_qr_malformed_xml(self):
        """Retorna None si el XML está mal formado."""
        xml = "<rDE><unclosed"
        qr_url = extract_dcar_qr(xml)
        assert qr_url is None


class TestQRParams:
    """Tests para extracción de parámetros del QR."""

    def test_extract_params_with_ampersand_escaped(self):
        """Extrae parámetros con &amp; escapado."""
        url = "https://ekuatia.set.gov.py/consultas-test/qr?nVersion=150&amp;Id=123&amp;cHashQR=abc"
        params, base = extract_qr_params(url)
        assert params["nVersion"] == "150"
        assert params["Id"] == "123"
        assert params["cHashQR"] == "abc"
        assert base == "https://ekuatia.set.gov.py/consultas-test/qr"

    def test_extract_params_without_escape(self):
        """Extrae parámetros sin escape."""
        url = "https://ekuatia.set.gov.py/consultas/qr?nVersion=150&Id=456"
        params, base = extract_qr_params(url)
        assert params["nVersion"] == "150"
        assert params["Id"] == "456"

    def test_extract_params_empty_url(self):
        """Maneja URL vacía."""
        params, base = extract_qr_params("")
        assert params == {}
        assert base is None

    def test_extract_params_none_url(self):
        """Maneja URL None."""
        params, base = extract_qr_params(None)
        assert params == {}
        assert base is None


class TestMismatchDetection:
    """Tests para detección de mismatch modo vs QR env."""

    def test_mismatch_test_qr_prod_mode(self):
        """Detecta mismatch: QR TEST con modo=0 (prod)."""
        xml = """<?xml version="1.0" encoding="UTF-8"?>
<rDE xmlns="http://ekuatia.set.gov.py/sifen/xsd">
    <gCamFuFD>
        <dCarQR>https://ekuatia.set.gov.py/consultas-test/qr?nVersion=150</dCarQR>
    </gCamFuFD>
</rDE>"""
        qr_url = extract_dcar_qr(xml)
        qr_env = detect_qr_env(qr_url)
        modo = 0
        
        # Simular lógica de validación
        has_mismatch = (modo == 0 and qr_env == "TEST") or (modo == 1 and qr_env == "PROD")
        assert has_mismatch is True

    def test_mismatch_prod_qr_test_mode(self):
        """Detecta mismatch: QR PROD con modo=1 (test)."""
        xml = """<?xml version="1.0" encoding="UTF-8"?>
<rDE xmlns="http://ekuatia.set.gov.py/sifen/xsd">
    <gCamFuFD>
        <dCarQR>https://ekuatia.set.gov.py/consultas/qr?nVersion=150</dCarQR>
    </gCamFuFD>
</rDE>"""
        qr_url = extract_dcar_qr(xml)
        qr_env = detect_qr_env(qr_url)
        modo = 1
        
        has_mismatch = (modo == 0 and qr_env == "TEST") or (modo == 1 and qr_env == "PROD")
        assert has_mismatch is True

    def test_no_mismatch_test_qr_test_mode(self):
        """No detecta mismatch: QR TEST con modo=1 (test)."""
        xml = """<?xml version="1.0" encoding="UTF-8"?>
<rDE xmlns="http://ekuatia.set.gov.py/sifen/xsd">
    <gCamFuFD>
        <dCarQR>https://ekuatia.set.gov.py/consultas-test/qr?nVersion=150</dCarQR>
    </gCamFuFD>
</rDE>"""
        qr_url = extract_dcar_qr(xml)
        qr_env = detect_qr_env(qr_url)
        modo = 1
        
        has_mismatch = (modo == 0 and qr_env == "TEST") or (modo == 1 and qr_env == "PROD")
        assert has_mismatch is False

    def test_no_mismatch_prod_qr_prod_mode(self):
        """No detecta mismatch: QR PROD con modo=0 (prod)."""
        xml = """<?xml version="1.0" encoding="UTF-8"?>
<rDE xmlns="http://ekuatia.set.gov.py/sifen/xsd">
    <gCamFuFD>
        <dCarQR>https://ekuatia.set.gov.py/consultas/qr?nVersion=150</dCarQR>
    </gCamFuFD>
</rDE>"""
        qr_url = extract_dcar_qr(xml)
        qr_env = detect_qr_env(qr_url)
        modo = 0
        
        has_mismatch = (modo == 0 and qr_env == "TEST") or (modo == 1 and qr_env == "PROD")
        assert has_mismatch is False
