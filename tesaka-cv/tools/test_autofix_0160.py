#!/usr/bin/env python3
"""
Test para el script autofix_0160_gTotSub.py
"""

import sys
from pathlib import Path

# Agregar el directorio tools al path
sys.path.insert(0, str(Path(__file__).parent))

from autofix_0160_gTotSub import parse_error_message, fix_gtotsub_order, run_send_sirecepde
import tempfile
import lxml.etree as ET


def test_parse_error_message():
    """Test para parse_error_message"""
    print("Testing parse_error_message...")
    
    # Test 1: Mensaje estándar
    msg1 = "XML malformado: [El elemento esperado es: dTotOpe en lugar de: dTotIVA]"
    assert parse_error_message(msg1) == "dTotOpe"
    print("✅ Test 1 passed")
    
    # Test 2: Mensaje con espacios extra
    msg2 = "XML malformado: [El elemento esperado es: dTotGrav  en lugar de: dTotIVA]"
    assert parse_error_message(msg2) == "dTotGrav"
    print("✅ Test 2 passed")
    
    # Test 3: Mensaje sin XML malformado
    msg3 = "Otro error: [cualquier cosa]"
    assert parse_error_message(msg3) is None
    print("✅ Test 3 passed")
    
    # Test 4: Mensaje con dTotExe
    msg4 = "XML malformado: [El elemento esperado es: dTotExe en lugar de: dTotIVA]"
    assert parse_error_message(msg4) == "dTotExe"
    print("✅ Test 4 passed")


def test_fix_gtotsub_order():
    """Test para fix_gtotsub_order"""
    print("\nTesting fix_gtotsub_order...")
    
    # Crear XML de prueba con gTotSub desordenado
    xml_content = """<?xml version="1.0" encoding="utf-8"?>
<rLoteDE xmlns="http://ekuatia.set.gov.py/sifen/xsd">
  <rDE Id="rDE123">
    <dVerFor>150</dVerFor>
    <DE Id="DE123">
      <gTotSub>
        <dTotIVA>1000</dTotIVA>
        <dTotOpe>2000</dTotOpe>
      </gTotSub>
    </DE>
  </rDE>
</rLoteDE>"""
    
    # Crear archivo temporal
    with tempfile.NamedTemporaryFile(mode='w', suffix='.xml', delete=False) as f:
        f.write(xml_content)
        temp_path = Path(f.name)
    
    try:
        # Corregir el XML
        fixed_path = fix_gtotsub_order(temp_path, "dTotOpe")
        
        # Verificar que se creó un nuevo archivo
        assert fixed_path != temp_path
        assert "dTotOpe" in fixed_path.name
        print("✅ Nuevo archivo creado")
        
        # Parsear el XML corregido y verificar orden
        tree = ET.parse(fixed_path)
        root = tree.getroot()
        ns = {'sifen': 'http://ekuatia.set.gov.py/sifen/xsd'}
        
        gtotsub = root.find('.//sifen:gTotSub', namespaces=ns)
        children = list(gtotsub)
        
        # dTotOpe debe estar antes que dTotIVA
        dtotope_idx = next(i for i, c in enumerate(children) if c.tag.endswith('dTotOpe'))
        dtotiva_idx = next(i for i, c in enumerate(children) if c.tag.endswith('dTotIVA'))
        
        assert dtotope_idx < dtotiva_idx
        print("✅ Tags en orden correcto")
        
        # Verificar valores
        assert children[dtotope_idx].text == "2000"
        assert children[dtotiva_idx].text == "1000"
        print("✅ Valores preservados")
        
    finally:
        # Limpiar archivos temporales
        temp_path.unlink(missing_ok=True)
        if fixed_path != temp_path:
            fixed_path.unlink(missing_ok=True)


def test_fix_gtotsub_create_missing():
    """Test para crear tag faltante"""
    print("\nTesting fix_gtotsub_order (crear tag faltante)...")
    
    # Crear XML sin dTotOpe
    xml_content = """<?xml version="1.0" encoding="utf-8"?>
<rLoteDE xmlns="http://ekuatia.set.gov.py/sifen/xsd">
  <rDE Id="rDE123">
    <dVerFor>150</dVerFor>
    <DE Id="DE123">
      <gTotSub>
        <dTotGrav>500</dTotGrav>
        <dTotIVA>1000</dTotIVA>
      </gTotSub>
    </DE>
  </rDE>
</rLoteDE>"""
    
    with tempfile.NamedTemporaryFile(mode='w', suffix='.xml', delete=False) as f:
        f.write(xml_content)
        temp_path = Path(f.name)
    
    try:
        # Corregir el XML
        fixed_path = fix_gtotsub_order(temp_path, "dTotOpe")
        
        # Parsear y verificar
        tree = ET.parse(fixed_path)
        root = tree.getroot()
        ns = {'sifen': 'http://ekuatia.set.gov.py/sifen/xsd'}
        
        gtotsub = root.find('.//sifen:gTotSub', namespaces=ns)
        dtotope = gtotsub.find('sifen:dTotOpe', namespaces=ns)
        
        assert dtotope is not None
        assert dtotope.text == "0"
        print("✅ Tag faltante creado con valor '0'")
        
        # Verificar orden
        children = list(gtotsub)
        dtotope_idx = next(i for i, c in enumerate(children) if c.tag.endswith('dTotOpe'))
        dtotiva_idx = next(i for i, c in enumerate(children) if c.tag.endswith('dTotIVA'))
        
        assert dtotope_idx < dtotiva_idx
        print("✅ Tag creado antes de dTotIVA")
        
    finally:
        temp_path.unlink(missing_ok=True)
        fixed_path.unlink(missing_ok=True)


def test_send_xml_command_construction():
    """Test para verificar que el comando send_sirecepde se construye correctamente"""
    print("\nTesting send_xml command construction...")
    
    # Crear un mock de run_command para capturar el comando
    captured_cmd = []
    
    def mock_run_command(cmd):
        captured_cmd.extend(cmd)
        class MockResult:
            returncode = 0
        return MockResult()
    
    # Mock para find_latest_file
    def mock_find_latest_file(pattern, artifacts_dir):
        return artifacts_dir / "response_test.json"
    
    # Patch temporal de funciones
    import autofix_0160_gTotSub
    original_run_command = autofix_0160_gTotSub.run_command
    original_find_latest_file = autofix_0160_gTotSub.find_latest_file
    autofix_0160_gTotSub.run_command = mock_run_command
    autofix_0160_gTotSub.find_latest_file = mock_find_latest_file
    
    try:
        # Crear XML temporal
        xml_content = "<?xml version='1.0'?><root></root>"
        with tempfile.NamedTemporaryFile(mode='w', suffix='.xml', delete=False) as f:
            f.write(xml_content)
            temp_path = Path(f.name)
        
        artifacts_dir = Path(temp_path.parent)
        
        # Test 1: Con bump_doc=1
        run_send_sirecepde(
            env="test",
            xml_path=temp_path,
            artifacts_dir=artifacts_dir,
            iteration=1,
            bump_doc=1,
            dump_http=False
        )
        
        # Verificar que --bump-doc 1 esté en el comando
        assert "--bump-doc" in captured_cmd
        bump_idx = captured_cmd.index("--bump-doc")
        assert captured_cmd[bump_idx + 1] == "1"
        print("✅ --bump-doc 1 incluido correctamente")
        
        # Reset
        captured_cmd.clear()
        
        # Test 2: Sin bump-doc (None o 0)
        run_send_sirecepde(
            env="test",
            xml_path=temp_path,
            artifacts_dir=artifacts_dir,
            iteration=2,
            bump_doc=0,
            dump_http=True
        )
        
        # Verificar que --bump-doc NO esté en el comando
        assert "--bump-doc" not in captured_cmd
        assert "--dump-http" in captured_cmd
        print("✅ --bump-doc omitido correctamente cuando es 0")
        
        # Limpiar
        temp_path.unlink()
        
    finally:
        # Restaurar funciones originales
        autofix_0160_gTotSub.run_command = original_run_command
        autofix_0160_gTotSub.find_latest_file = original_find_latest_file


if __name__ == "__main__":
    print("Running tests for autofix_0160_gTotSub.py...")
    print("=" * 50)
    
    test_parse_error_message()
    test_fix_gtotsub_order()
    test_fix_gtotsub_create_missing()
    test_send_xml_command_construction()
    
    print("\n" + "=" * 50)
    print("✅ All tests passed!")
