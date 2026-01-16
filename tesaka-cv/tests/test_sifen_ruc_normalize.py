"""
Tests unitarios para normalización de RUC según especificación SIFEN
"""
import pytest
from app.sifen.ruc import normalize_truc, RucFormatError


class TestNormalizeTruc:
    """Tests para normalize_truc()"""
    
    def test_valid_with_hyphen_7_digits(self):
        """RUC con guión, 7 dígitos totales (BASE 6 + DV 1)"""
        assert normalize_truc("4554737-8") == "45547378"
        assert normalize_truc("123456-7") == "1234567"
    
    def test_valid_with_hyphen_8_digits(self):
        """RUC con guión, 8 dígitos totales (BASE 7 + DV 1)"""
        assert normalize_truc("4554737-8") == "45547378"
        assert normalize_truc("1234567-8") == "12345678"
    
    def test_valid_without_hyphen_7_digits(self):
        """RUC sin guión, 7 dígitos"""
        assert normalize_truc("4554737") == "4554737"
        assert normalize_truc("1234567") == "1234567"
    
    def test_valid_without_hyphen_8_digits(self):
        """RUC sin guión, 8 dígitos"""
        assert normalize_truc("45547378") == "45547378"
        assert normalize_truc("12345678") == "12345678"
    
    def test_strips_whitespace(self):
        """Limpia espacios al inicio y final"""
        assert normalize_truc("  4554737-8  ") == "45547378"
        assert normalize_truc("  45547378  ") == "45547378"
    
    def test_empty_string(self):
        """String vacío debe lanzar error"""
        with pytest.raises(RucFormatError, match="no puede estar vacío"):
            normalize_truc("")
    
    def test_only_spaces(self):
        """Solo espacios debe lanzar error"""
        with pytest.raises(RucFormatError, match="no puede estar vacío"):
            normalize_truc("   ")
    
    def test_too_short(self):
        """RUC demasiado corto (< 7 dígitos)"""
        with pytest.raises(RucFormatError, match="longitud inválida"):
            normalize_truc("12345")
            normalize_truc("123456")
    
    def test_too_long(self):
        """RUC demasiado largo (> 8 dígitos)"""
        with pytest.raises(RucFormatError, match="longitud inválida"):
            normalize_truc("123456789")
            normalize_truc("1234567890")
    
    def test_contains_letters(self):
        """RUC con letras debe lanzar error"""
        with pytest.raises(RucFormatError, match="no numéricos"):
            normalize_truc("ABC12345")
            normalize_truc("12345ABC")
    
    def test_hyphen_no_dv(self):
        """RUC con guión pero sin DV debe lanzar error"""
        with pytest.raises(RucFormatError, match="debe incluir dígito verificador"):
            normalize_truc("4554737-")
            normalize_truc("4554737- ")
    
    def test_base_too_short(self):
        """BASE con guión demasiado corto (< 6 dígitos)"""
        with pytest.raises(RucFormatError, match="longitud inválida"):
            normalize_truc("12345-6")  # BASE 5 dígitos
            normalize_truc("1234-5")   # BASE 4 dígitos
    
    def test_base_too_long(self):
        """BASE con guión demasiado largo (> 7 dígitos)"""
        with pytest.raises(RucFormatError, match="longitud inválida"):
            normalize_truc("12345678-9")  # BASE 8 dígitos
    
    def test_dv_multiple_digits(self):
        """DV con múltiples dígitos, toma solo el primero"""
        # Si viene "4554737-89", debe tomar solo "8" como DV
        # Esto produce BASE 6 + DV 1 = 7 dígitos totales
        assert normalize_truc("4554737-89") == "45547378"
        assert normalize_truc("1234567-89") == "12345678"
