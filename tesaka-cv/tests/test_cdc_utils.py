#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Tests mínimos para cdc_utils.

Ejecutar:
    python -m pytest tests/test_cdc_utils.py -v
    # O directamente:
    python tests/test_cdc_utils.py
"""

import sys
from pathlib import Path

# Agregar el directorio padre al path para imports
sys.path.insert(0, str(Path(__file__).parent.parent))

# Importar directamente sin pasar por __init__.py
import importlib.util
cdc_utils_path = Path(__file__).parent.parent / "app" / "sifen_client" / "cdc_utils.py"
spec = importlib.util.spec_from_file_location("cdc_utils", cdc_utils_path)
cdc_utils = importlib.util.module_from_spec(spec)
spec.loader.exec_module(cdc_utils)

calc_dv_mod11 = cdc_utils.calc_dv_mod11
fix_cdc = cdc_utils.fix_cdc
validate_cdc = cdc_utils.validate_cdc


def test_calc_dv_mod11_caso_usuario():
    """Test con el caso del usuario: CDC con DV incorrecto."""
    base = "0104554737800100100000011202512301123456789"
    dv = calc_dv_mod11(base)
    assert dv == 5, f"DV esperado: 5, obtenido: {dv}"
    print(f"✅ Test 1: DV calculado correctamente = {dv}")


def test_fix_cdc_caso_usuario():
    """Test corrigiendo el CDC del usuario."""
    cdc_incorrecto = "01045547378001001000000112025123011234567892"
    cdc_correcto = fix_cdc(cdc_incorrecto)
    expected = "01045547378001001000000112025123011234567895"
    assert cdc_correcto == expected, f"CDC corregido esperado: {expected}, obtenido: {cdc_correcto}"
    print(f"✅ Test 2: CDC corregido correctamente = {cdc_correcto}")


def test_validate_cdc_valido():
    """Test validando un CDC válido."""
    cdc_valido = "01045547378001001000000112025123011234567895"
    es_valido, dv_orig, dv_calc = validate_cdc(cdc_valido)
    assert es_valido, f"CDC debería ser válido: {cdc_valido}"
    assert dv_orig == 5, f"DV original debería ser 5, obtenido: {dv_orig}"
    assert dv_calc == 5, f"DV calculado debería ser 5, obtenido: {dv_calc}"
    print(f"✅ Test 3: CDC válido detectado correctamente")


def test_validate_cdc_invalido():
    """Test validando un CDC inválido."""
    cdc_invalido = "01045547378001001000000112025123011234567892"
    es_valido, dv_orig, dv_calc = validate_cdc(cdc_invalido)
    assert not es_valido, f"CDC debería ser inválido: {cdc_invalido}"
    assert dv_orig == 2, f"DV original debería ser 2, obtenido: {dv_orig}"
    assert dv_calc == 5, f"DV calculado debería ser 5, obtenido: {dv_calc}"
    print(f"✅ Test 4: CDC inválido detectado correctamente")


if __name__ == "__main__":
    print("Ejecutando tests de cdc_utils...\n")
    try:
        test_calc_dv_mod11_caso_usuario()
        test_fix_cdc_caso_usuario()
        test_validate_cdc_valido()
        test_validate_cdc_invalido()
        print("\n✅ Todos los tests pasaron")
        sys.exit(0)
    except AssertionError as e:
        print(f"\n❌ Test falló: {e}")
        sys.exit(1)
    except Exception as e:
        print(f"\n❌ Error inesperado: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

