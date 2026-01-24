#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Tests para auto_fix_0160_loop.py - Funcionalidad de parseo y fix genérico
"""

import re
import tempfile
from pathlib import Path
from lxml import etree

# Importar las funciones del script
import sys
REPO_ROOT = Path(__file__).parent
sys.path.insert(0, str(REPO_ROOT))

def strip_ns(tag):
    return tag.split("}", 1)[-1] if "}" in tag else tag

# Importar desde tesaka-cv/tools
sys.path.insert(0, str(REPO_ROOT / "tesaka-cv" / "tools"))
from auto_fix_0160_loop import parse_0160_expected_found, ensure_expected_before_found, canonical_gTotSub_order


def test_parse_0160_expected_found():
    """Test que verifica el parseo del error 0160"""
    # Test caso normal
    msg = "XML malformado: El elemento esperado es: dTotDesc en lugar de: dTotIVA"
    result = parse_0160_expected_found(msg)
    assert result == ("dTotDesc", "dTotIVA"), f"Expected (dTotDesc, dTotIVA), got {result}"
    
    # Test con mayúsculas/minúsculas
    msg2 = "Error: El elemento esperado es: DPORTOTDESC EN LUGAR DE: DTOTIVA"
    result2 = parse_0160_expected_found(msg2)
    assert result2 == ("DPORTOTDESC", "DTOTIVA"), f"Expected (DPORTOTDESC, DTOTIVA), got {result2}"
    
    # Test sin patrón
    msg3 = "Otro error sin patrón esperado/en lugar de"
    result3 = parse_0160_expected_found(msg3)
    assert result3 is None, f"Expected None, got {result3}"
    
    print("✅ test_parse_0160_expected_found pasó")


def test_ensure_expected_before_found():
    """Test que verifica la inserción de elementos faltantes"""
    # Crear XML de prueba
    xml_content = """<?xml version="1.0" encoding="UTF-8"?>
<rLoteDE xmlns="http://ekuatia.set.gov.py/sifen/xsd">
  <rDE Id="rDE123">
    <DE Id="DE456">
      <gTotSub>
        <dTotIVA>1000</dTotIVA>
        <dTotGralOp>2000</dTotGralOp>
      </gTotSub>
    </DE>
  </rDE>
</rLoteDE>"""
    
    with tempfile.TemporaryDirectory() as tmpdir:
        xml_path = Path(tmpdir) / "test.xml"
        xml_path.write_text(xml_content, encoding="utf-8")
        
        # Insertar dTotDesc antes de dTotIVA
        new_path, changed, debug = ensure_expected_before_found(xml_path, "dTotDesc", "dTotIVA")
        
        assert changed, "El XML debería haber cambiado"
        assert debug["action"] == "CREATED", f"Expected action=CREATED, got {debug['action']}"
        assert debug["parent_tag"] == "gTotSub", f"Expected parent=gTotSub, got {debug['parent_tag']}"
        
        # Verificar el XML resultante
        doc = etree.parse(str(new_path))
        gTotSub = doc.xpath("//s:gTotSub", namespaces={"s": "http://ekuatia.set.gov.py/sifen/xsd"})[0]
        children = [strip_ns(ch.tag) for ch in gTotSub]
        
        assert children[0] == "dTotDesc", f"Expected first child=dTotDesc, got {children[0]}"
        assert children[1] == "dTotIVA", f"Expected second child=dTotIVA, got {children[1]}"
        assert gTotSub[0].text == "0", f"Expected dTotDesc=0, got {gTotSub[0].text}"
        
        print("✅ test_ensure_expected_before_found pasó")


def test_ensure_expected_move_existing():
    """Test que verifica el movimiento de elementos existentes"""
    # Crear XML con dTotDesc después de dTotIVA
    xml_content = """<?xml version="1.0" encoding="UTF-8"?>
<rLoteDE xmlns="http://ekuatia.set.gov.py/sifen/xsd">
  <rDE Id="rDE123">
    <DE Id="DE456">
      <gTotSub>
        <dTotIVA>1000</dTotIVA>
        <dTotDesc>100</dTotDesc>
        <dTotGralOp>2000</dTotGralOp>
      </gTotSub>
    </DE>
  </rDE>
</rLoteDE>"""
    
    def strip_ns(tag):
        return tag.split("}", 1)[-1] if "}" in tag else tag
    
    with tempfile.TemporaryDirectory() as tmpdir:
        xml_path = Path(tmpdir) / "test.xml"
        xml_path.write_text(xml_content, encoding="utf-8")
        
        # Mover dTotDesc antes de dTotIVA
        new_path, changed, debug = ensure_expected_before_found(xml_path, "dTotDesc", "dTotIVA")
        
        assert changed, "El XML debería haber cambiado"
        assert debug["action"] in ["REORDERED", "MOVED_BEFORE"], f"Expected action=REORDERED or MOVED_BEFORE, got {debug['action']}"
        
        # Verificar el XML resultante
        doc = etree.parse(str(new_path))
        gTotSub = doc.xpath("//s:gTotSub", namespaces={"s": "http://ekuatia.set.gov.py/sifen/xsd"})[0]
        children = [strip_ns(ch.tag) for ch in gTotSub]
        
        assert children[0] == "dTotDesc", f"Expected first child=dTotDesc, got {children[0]}"
        assert children[1] == "dTotIVA", f"Expected second child=dTotIVA, got {children[1]}"
        
        print("✅ test_ensure_expected_move_existing pasó")


def test_canonical_gTotSub_order():
    """Test que verifica el ordenamiento canónico de gTotSub"""
    # Crear XML con elementos desordenados
    xml_content = """<?xml version="1.0" encoding="UTF-8"?>
<rLoteDE xmlns="http://ekuatia.set.gov.py/sifen/xsd">
  <rDE Id="rDE123">
    <DE Id="DE456">
      <gTotSub>
        <dTotIVA>1000</dTotIVA>
        <dTotDesc>100</dTotDesc>
        <dTotOpe>1100</dTotOpe>
        <dSubExe>500</dSubExe>
      </gTotSub>
    </DE>
  </rDE>
</rLoteDE>"""
    
    def strip_ns(tag):
        return tag.split("}", 1)[-1] if "}" in tag else tag
    
    # Parsear y aplicar orden canónico
    doc = etree.fromstring(xml_content.encode('utf-8'))
    doc_tree = etree.ElementTree(doc)
    changed = canonical_gTotSub_order(doc_tree)
    
    assert changed > 0, "El XML debería haber cambiado"
    
    # Verificar orden canónico
    gTotSub = doc_tree.xpath("//s:gTotSub", namespaces={"s": "http://ekuatia.set.gov.py/sifen/xsd"})[0]
    children = [strip_ns(ch.tag) for ch in gTotSub]
    
    # El orden debería empezar con los elementos canónicos conocidos
    expected_order = ["dSubExe", "dSubExo", "dSub5", "dSub10", "dTotOpe", "dTotDesc", "dTotDescGlotem", 
                     "dTotAntItem", "dTotAnt", "dPorcDescTotal", "dTotIVA", "dTotGralOp", "dTotGrav", "dTotExe"]
    
    # Verificar que los primeros elementos estén en orden canónico
    for i, expected in enumerate(expected_order):
        if i < len(children) and children[i] in expected_order:
            assert children[i] == expected, f"Expected {expected} at position {i}, got {children[i]}"
    
    print("✅ test_canonical_gTotSub_order pasó")


def test_fix_sequence_simulation():
    """Test que simula la secuencia de fixes que haría el loop"""
    # Simular XML inicial que falta dTotDesc
    xml_content = """<?xml version="1.0" encoding="UTF-8"?>
<rLoteDE xmlns="http://ekuatia.set.gov.py/sifen/xsd">
  <rDE Id="rDE123">
    <DE Id="DE456">
      <gTotSub>
        <dTotOpe>1100</dTotOpe>
        <dTotIVA>1000</dTotIVA>
      </gTotSub>
    </DE>
  </rDE>
</rLoteDE>"""
    
    def strip_ns(tag):
        return tag.split("}", 1)[-1] if "}" in tag else tag
    
    with tempfile.TemporaryDirectory() as tmpdir:
        artifacts_dir = Path(tmpdir)
        xml_path = artifacts_dir / "test.xml"
        xml_path.write_text(xml_content, encoding="utf-8")
        
        current_xml = xml_path
        fixes_applied = []
        
        # Simular secuencia de errores 0160
        error_sequence = [
            ("dTotDesc", "dTotIVA"),
            ("dTotDescGlotem", "dTotAnt"),
            ("dTotAntItem", "dTotAnt"),
            ("dTotAnt", "dPorcDescTotal"),
            ("dPorcDescTotal", "dTotIVA")
        ]
        
        for expected, found in error_sequence:
            new_path, changed, debug = ensure_expected_before_found(current_xml, expected, found)
            if changed:
                fixes_applied.append(f"Inserted {expected} before {found}")
                current_xml = new_path
        
        # Verificar resultado final
        doc = etree.parse(str(current_xml))
        gTotSub = doc.xpath("//s:gTotSub", namespaces={"s": "http://ekuatia.set.gov.py/sifen/xsd"})[0]
        children = [strip_ns(ch.tag) for ch in gTotSub]
        
        # Verificar que todos los elementos estén en orden correcto
        assert "dTotDesc" in children, "dTotDesc debería estar presente"
        assert "dTotDescGlotem" in children, "dTotDescGlotem debería estar presente"
        assert "dTotAntItem" in children, "dTotAntItem debería estar presente"
        assert "dTotAnt" in children, "dTotAnt debería estar presente"
        assert "dPorcDescTotal" in children, "dPorcDescTotal debería estar presente"
        
        # Verificar orden relativo
        desc_idx = children.index("dTotDesc")
        iva_idx = children.index("dTotIVA")
        assert desc_idx < iva_idx, "dTotDesc debe estar antes que dTotIVA"
        
        print("✅ test_fix_sequence_simulation pasó")
        print(f"   Fixes aplicados: {len(fixes_applied)}")
        for fix in fixes_applied:
            print(f"   - {fix}")


if __name__ == "__main__":
    test_parse_0160_expected_found()
    test_ensure_expected_before_found()
    test_ensure_expected_move_existing()
    test_canonical_gTotSub_order()
    test_fix_sequence_simulation()
    print("\n🎉 Todos los tests pasaron")
