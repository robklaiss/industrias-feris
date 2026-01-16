"""
Tests para validación de coherencia de ambiente SIFEN.
"""

import os
import pytest
from app.sifen_client.env_validator import (
    get_current_env,
    env_to_modo,
    modo_to_env,
    get_expected_qr_base,
    assert_test_env,
    validate_qr_base_url,
)


class TestEnvDetection:
    """Tests para detección de ambiente actual."""

    def test_get_current_env_test(self, monkeypatch):
        """Detecta ambiente TEST."""
        monkeypatch.setenv("SIFEN_ENV", "test")
        assert get_current_env() == "test"

    def test_get_current_env_prod(self, monkeypatch):
        """Detecta ambiente PROD."""
        monkeypatch.setenv("SIFEN_ENV", "prod")
        assert get_current_env() == "prod"

    def test_get_current_env_default(self, monkeypatch):
        """Default a TEST si no está configurado."""
        monkeypatch.delenv("SIFEN_ENV", raising=False)
        assert get_current_env() == "test"


class TestModoConversion:
    """Tests para conversión entre ambiente y modo."""

    def test_env_to_modo_test(self):
        """TEST = modo 1."""
        assert env_to_modo("test") == 1

    def test_env_to_modo_prod(self):
        """PROD = modo 0."""
        assert env_to_modo("prod") == 0

    def test_modo_to_env_test(self):
        """modo 1 = TEST."""
        assert modo_to_env(1) == "test"

    def test_modo_to_env_prod(self):
        """modo 0 = PROD."""
        assert modo_to_env(0) == "prod"


class TestQRBaseURL:
    """Tests para URL base del QR según ambiente."""

    def test_qr_base_test(self):
        """URL base TEST correcta."""
        base = get_expected_qr_base("test")
        assert base == "https://ekuatia.set.gov.py/consultas-test/qr"

    def test_qr_base_prod(self):
        """URL base PROD correcta."""
        base = get_expected_qr_base("prod")
        assert base == "https://ekuatia.set.gov.py/consultas/qr"


class TestQRBaseValidation:
    """Tests para validación de QR base URL."""

    def test_validate_qr_base_test_ok(self, monkeypatch):
        """QR base TEST válido cuando SIFEN_ENV=test."""
        monkeypatch.setenv("SIFEN_ENV", "test")
        result = validate_qr_base_url("https://ekuatia.set.gov.py/consultas-test/qr")
        assert result["valid"] is True
        assert result["error"] is None

    def test_validate_qr_base_prod_ok(self, monkeypatch):
        """QR base PROD válido cuando SIFEN_ENV=prod."""
        monkeypatch.setenv("SIFEN_ENV", "prod")
        result = validate_qr_base_url("https://ekuatia.set.gov.py/consultas/qr")
        assert result["valid"] is True
        assert result["error"] is None

    def test_validate_qr_base_test_with_prod_url(self, monkeypatch):
        """Error: SIFEN_ENV=test pero QR base es PROD."""
        monkeypatch.setenv("SIFEN_ENV", "test")
        result = validate_qr_base_url("https://ekuatia.set.gov.py/consultas/qr")
        assert result["valid"] is False
        assert "SIFEN_ENV=test" in result["error"]
        assert "PROD" in result["error"]

    def test_validate_qr_base_prod_with_test_url(self, monkeypatch):
        """Error: SIFEN_ENV=prod pero QR base es TEST."""
        monkeypatch.setenv("SIFEN_ENV", "prod")
        result = validate_qr_base_url("https://ekuatia.set.gov.py/consultas-test/qr")
        assert result["valid"] is False
        assert "SIFEN_ENV=prod" in result["error"]
        assert "TEST" in result["error"]


class TestAssertTestEnv:
    """Tests para assert_test_env() - validación completa."""

    def test_assert_test_env_ok(self, monkeypatch):
        """XML TEST + modo=1 + SIFEN_ENV=test = OK."""
        monkeypatch.setenv("SIFEN_ENV", "test")
        xml = """<?xml version="1.0" encoding="UTF-8"?>
<rDE xmlns="http://ekuatia.set.gov.py/sifen/xsd">
    <gCamFuFD>
        <dCarQR>https://ekuatia.set.gov.py/consultas-test/qr?nVersion=150</dCarQR>
    </gCamFuFD>
</rDE>"""
        result = assert_test_env(xml, modo=1)
        assert result["valid"] is True
        assert len(result["errors"]) == 0

    def test_assert_test_env_qr_mismatch(self, monkeypatch):
        """Error: SIFEN_ENV=test pero QR es PROD."""
        monkeypatch.setenv("SIFEN_ENV", "test")
        xml = """<?xml version="1.0" encoding="UTF-8"?>
<rDE xmlns="http://ekuatia.set.gov.py/sifen/xsd">
    <gCamFuFD>
        <dCarQR>https://ekuatia.set.gov.py/consultas/qr?nVersion=150</dCarQR>
    </gCamFuFD>
</rDE>"""
        result = assert_test_env(xml, modo=1)
        assert result["valid"] is False
        assert any("SIFEN_ENV=test" in err and "PROD" in err for err in result["errors"])

    def test_assert_test_env_modo_mismatch(self, monkeypatch):
        """Error: SIFEN_ENV=test pero modo=0."""
        monkeypatch.setenv("SIFEN_ENV", "test")
        xml = """<?xml version="1.0" encoding="UTF-8"?>
<rDE xmlns="http://ekuatia.set.gov.py/sifen/xsd">
    <gCamFuFD>
        <dCarQR>https://ekuatia.set.gov.py/consultas-test/qr?nVersion=150</dCarQR>
    </gCamFuFD>
</rDE>"""
        result = assert_test_env(xml, modo=0)
        assert result["valid"] is False
        assert any("modo=0" in err for err in result["errors"])

    def test_assert_test_env_2502_prevention(self, monkeypatch):
        """Error 2502: QR TEST + modo=0."""
        monkeypatch.setenv("SIFEN_ENV", "test")
        xml = """<?xml version="1.0" encoding="UTF-8"?>
<rDE xmlns="http://ekuatia.set.gov.py/sifen/xsd">
    <gCamFuFD>
        <dCarQR>https://ekuatia.set.gov.py/consultas-test/qr?nVersion=150</dCarQR>
    </gCamFuFD>
</rDE>"""
        result = assert_test_env(xml, modo=0)
        assert result["valid"] is False
        assert any("2502" in err for err in result["errors"])

    def test_assert_test_env_prod_ok(self, monkeypatch):
        """XML PROD + modo=0 + SIFEN_ENV=prod = OK."""
        monkeypatch.setenv("SIFEN_ENV", "prod")
        xml = """<?xml version="1.0" encoding="UTF-8"?>
<rDE xmlns="http://ekuatia.set.gov.py/sifen/xsd">
    <gCamFuFD>
        <dCarQR>https://ekuatia.set.gov.py/consultas/qr?nVersion=150</dCarQR>
    </gCamFuFD>
</rDE>"""
        result = assert_test_env(xml, modo=0)
        assert result["valid"] is True
        assert len(result["errors"]) == 0

    def test_assert_test_env_no_qr(self, monkeypatch):
        """Warning si no hay QR en el XML."""
        monkeypatch.setenv("SIFEN_ENV", "test")
        xml = """<?xml version="1.0" encoding="UTF-8"?>
<rDE xmlns="http://ekuatia.set.gov.py/sifen/xsd">
    <DE Id="123"/>
</rDE>"""
        result = assert_test_env(xml, modo=1)
        assert len(result["warnings"]) > 0
        assert any("dCarQR" in warn for warn in result["warnings"])
