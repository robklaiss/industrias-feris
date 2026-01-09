"""
Tests unitarios para normalización de RUC según especificación SIFEN

Reglas confirmadas:
- RUC paraguayo NUNCA tiene letras
- Siempre tiene 7-8 dígitos totales (incluyendo DV)
- Input puede venir con o sin guión
"""
import unittest
import sys
import importlib.util
from pathlib import Path

# Importar directamente sin pasar por __init__.py (evita dependencias de signxml)
TESAKA_CV_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(TESAKA_CV_ROOT))

# Importar módulo directamente
ruc_format_path = TESAKA_CV_ROOT / "app" / "sifen_client" / "ruc_format.py"
spec = importlib.util.spec_from_file_location("ruc_format", ruc_format_path)
ruc_format = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ruc_format)

normalize_sifen_truc = ruc_format.normalize_sifen_truc
RucFormatError = ruc_format.RucFormatError


class TestRucFormat(unittest.TestCase):
    """Tests para normalize_sifen_truc según especificación SIFEN"""
    
    def test_normalize_with_hyphen_base_7_digits(self):
        """Test: '4554737-8' => '45547378' (7 dígitos base + 1 DV = 8 total)"""
        result = normalize_sifen_truc("4554737-8")
        self.assertEqual(result, "45547378")
        self.assertEqual(len(result), 8)
        self.assertTrue(result.isdigit())
    
    def test_normalize_with_hyphen_base_6_digits(self):
        """Test: '455473-7' => '4554737' (6 dígitos base + 1 DV = 7 total)"""
        result = normalize_sifen_truc("455473-7")
        self.assertEqual(result, "4554737")
        self.assertEqual(len(result), 7)
        self.assertTrue(result.isdigit())
    
    def test_normalize_without_hyphen_8_digits(self):
        """Test: '45547378' => '45547378' (sin guión, 8 dígitos, válido)"""
        result = normalize_sifen_truc("45547378")
        self.assertEqual(result, "45547378")
        self.assertEqual(len(result), 8)
        self.assertTrue(result.isdigit())
    
    def test_normalize_without_hyphen_7_digits(self):
        """Test: '4554737' => '4554737' (sin guión, 7 dígitos, válido)"""
        result = normalize_sifen_truc("4554737")
        self.assertEqual(result, "4554737")
        self.assertEqual(len(result), 7)
        self.assertTrue(result.isdigit())
    
    def test_normalize_with_spaces(self):
        """Test: RUC con espacios (debe limpiarlos)"""
        result = normalize_sifen_truc("  4554737-8  ")
        self.assertEqual(result, "45547378")
        self.assertEqual(len(result), 8)
        self.assertTrue(result.isdigit())
    
    def test_normalize_8_digits_with_hyphen(self):
        """Test: '80012345-7' => '800123457' (8 dígitos base sería inválido, pero si viene así se concatena)"""
        # Nota: Este caso es técnicamente inválido porque base de 8 dígitos no existe,
        # pero si viene como input, lo procesamos y validamos el resultado final
        with self.assertRaises(RucFormatError) as ctx:
            normalize_sifen_truc("80012345-7")
        self.assertIn("longitud inválida", str(ctx.exception))
        self.assertIn("6 o 7 dígitos", str(ctx.exception))
    
    def test_error_6_digits_no_hyphen(self):
        """Test: '455473' => error (6 dígitos sin guión es inválido)"""
        with self.assertRaises(RucFormatError) as ctx:
            normalize_sifen_truc("455473")
        self.assertIn("longitud inválida", str(ctx.exception))
        self.assertIn("7 u 8 dígitos", str(ctx.exception))
    
    def test_error_9_digits(self):
        """Test: RUC muy largo (> 8) => error"""
        with self.assertRaises(RucFormatError) as ctx:
            normalize_sifen_truc("123456789")
        self.assertIn("longitud inválida", str(ctx.exception))
        self.assertIn("7 u 8 dígitos", str(ctx.exception))
    
    def test_error_empty_string(self):
        """Test: RUC vacío => error"""
        with self.assertRaises(RucFormatError) as ctx:
            normalize_sifen_truc("")
        self.assertIn("no puede estar vacío", str(ctx.exception))
    
    def test_error_only_spaces(self):
        """Test: Solo espacios => error"""
        with self.assertRaises(RucFormatError) as ctx:
            normalize_sifen_truc("   ")
        self.assertIn("no puede estar vacío", str(ctx.exception))
    
    def test_error_contains_letters(self):
        """Test: RUC con letras => error (RUC paraguayo NUNCA tiene letras)"""
        with self.assertRaises(RucFormatError) as ctx:
            normalize_sifen_truc("4554737-A")
        error_msg = str(ctx.exception).lower()
        self.assertTrue(
            "no numéricos" in error_msg or "dígitos" in error_msg,
            f"Error message should mention non-numeric, got: {ctx.exception}"
        )
    
    def test_error_contains_letters_no_hyphen(self):
        """Test: RUC sin guión pero con letras => error"""
        with self.assertRaises(RucFormatError) as ctx:
            normalize_sifen_truc("RUC_VALIDO_SIN_GUION")
        error_msg = str(ctx.exception).lower()
        self.assertTrue(
            "no contiene dígitos" in error_msg or "longitud inválida" in error_msg,
            f"Error message should mention no digits, got: {ctx.exception}"
        )
    
    def test_error_base_too_short(self):
        """Test: Base muy corta (< 6) => error"""
        with self.assertRaises(RucFormatError) as ctx:
            normalize_sifen_truc("12345-6")
        self.assertIn("longitud inválida", str(ctx.exception))
        self.assertIn("6 o 7 dígitos", str(ctx.exception))
    
    def test_error_base_too_long(self):
        """Test: Base muy larga (> 7) => error"""
        with self.assertRaises(RucFormatError) as ctx:
            normalize_sifen_truc("12345678-9")
        self.assertIn("longitud inválida", str(ctx.exception))
        self.assertIn("6 o 7 dígitos", str(ctx.exception))
    
    def test_error_no_dv_with_hyphen(self):
        """Test: RUC con guión pero sin DV => error"""
        with self.assertRaises(RucFormatError) as ctx:
            normalize_sifen_truc("4554737-")
        self.assertIn("debe incluir dígito verificador", str(ctx.exception))
    
    def test_error_dv_has_letters(self):
        """Test: DV con letras => error"""
        with self.assertRaises(RucFormatError) as ctx:
            normalize_sifen_truc("4554737-A")
        error_msg = str(ctx.exception).lower()
        self.assertTrue(
            "no numéricos" in error_msg or "dígito verificador" in error_msg,
            f"Error message should mention non-numeric DV, got: {ctx.exception}"
        )
    
    def test_error_starts_with_zero(self):
        """Test: RUC que empieza en 0 => válido (no hay restricción de patrón, solo longitud y dígitos)"""
        # Nota: Según la nueva especificación, solo validamos longitud y dígitos, no patrón
        # Un RUC que empiece en 0 técnicamente pasa la validación (7-8 dígitos)
        result = normalize_sifen_truc("0123456")
        self.assertEqual(result, "0123456")
        self.assertEqual(len(result), 7)
    
    def test_success_7_digits_base_with_dv(self):
        """Test: Base de 7 dígitos con DV => OK (7+1=8)"""
        result = normalize_sifen_truc("4554737-8")
        self.assertEqual(result, "45547378")
        self.assertEqual(len(result), 8)
    
    def test_success_6_digits_base_with_dv(self):
        """Test: Base de 6 dígitos con DV => OK (6+1=7)"""
        result = normalize_sifen_truc("455473-7")
        self.assertEqual(result, "4554737")
        self.assertEqual(len(result), 7)
    
    def test_error_5_digits(self):
        """Test: RUC de 5 dígitos => error (mínimo 7)"""
        with self.assertRaises(RucFormatError) as ctx:
            normalize_sifen_truc("12345")
        self.assertIn("longitud inválida", str(ctx.exception))
        self.assertIn("7 u 8 dígitos", str(ctx.exception))


if __name__ == "__main__":
    unittest.main()
