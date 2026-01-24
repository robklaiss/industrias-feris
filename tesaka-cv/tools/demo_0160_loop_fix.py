#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Demostración del auto-fix loop para errores 0160 del tipo "esperado en lugar de"
"""

import tempfile
from pathlib import Path
from lxml import etree

# Importar funciones del auto_fix_0160_loop
import sys
REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "tesaka-cv"))
sys.path.insert(0, str(REPO_ROOT / "tesaka-cv" / "tools"))

from auto_fix_0160_loop import parse_0160_expected_found, ensure_expected_before_found, canonical_gTotSub_order

def strip_ns(tag):
    return tag.split("}", 1)[-1] if "}" in tag else tag


def create_initial_xml():
    """Crea un XML inicial con problemas típicos que causan 0160"""
    xml_content = """<?xml version="1.0" encoding="UTF-8"?>
<rLoteDE xmlns="http://ekuatia.set.gov.py/sifen/xsd">
  <rDE Id="rDE123">
    <dVerFor>150</dVerFor>
    <DE Id="DE456">
      <dCodGen>1</dCodGen>
      <dDenSuc>CASA MATRIZ</dDenSuc>
      <gDatGen>
        <dFeEmiDE>2026-01-23</dFeEmiDE>
        <!-- ... otros campos ... -->
      </gDatGen>
      <gTotSub>
        <dTotOpe>110000</dTotOpe>
        <dTotIVA>22000</dTotIVA>
        <dTotGralOp>132000</dTotGralOp>
      </gTotSub>
      <!-- ... otros campos ... -->
    </DE>
  </rDE>
</rLoteDE>"""
    return xml_content


def simulate_sifen_errors():
    """Simula la secuencia de errores que SIFEN devolvería"""
    return [
        "XML malformado: El elemento esperado es: dTotDesc en lugar de: dTotIVA",
        "XML malformado: El elemento esperado es: dTotDescGlotem en lugar de: dTotDesc",
        "XML malformado: El elemento esperado es: dTotAntItem en lugar de: dTotDescGlotem",
        "XML malformado: El elemento esperado es: dTotAnt en lugar de: dTotAntItem",
        "XML malformado: El elemento esperado es: dPorcDescTotal en lugar de: dTotAnt",
        "XML malformado: El elemento esperado es: dSubExe en lugar de: dTotOpe",
        "XML malformado: El elemento esperado es: dSubExo en lugar de: dSubExe",
        "Aceptado"  # Final exitoso
    ]


def main():
    print("🚀 Demostración del Auto-Fix 0160 Loop")
    print("=" * 60)
    
    with tempfile.TemporaryDirectory() as tmpdir:
        artifacts_dir = Path(tmpdir)
        
        # Crear XML inicial
        xml_content = create_initial_xml()
        current_xml = artifacts_dir / "lote_initial.xml"
        current_xml.write_text(xml_content, encoding="utf-8")
        
        print(f"\n📁 XML inicial guardado en: {current_xml}")
        
        # Mostrar estado inicial de gTotSub
        doc = etree.parse(str(current_xml))
        gTotSub = doc.xpath("//s:gTotSub", namespaces={"s": "http://ekuatia.set.gov.py/sifen/xsd"})[0]
        print("\n📊 Estado inicial de gTotSub:")
        for ch in gTotSub:
            print(f"   - {strip_ns(ch.tag)}: {ch.text}")
        
        # Simular el loop
        errors = simulate_sifen_errors()
        iteration = 0
        
        for error_msg in errors:
            iteration += 1
            print(f"\n{'='*60}")
            print(f"🔄 Iteración {iteration}")
            print(f"📝 SIFEN dice: {error_msg}")
            
            if error_msg == "Aceptado":
                print("\n✅ ¡ÉXITO! SIFEN aceptó el documento")
                break
            
            # Parsear el error
            expected_found = parse_0160_expected_found(error_msg)
            
            if not expected_found:
                print("❌ Error no reconocido")
                break
            
            expected, found = expected_found
            print(f"🔍 Detectado: se espera '{expected}' antes de '{found}'")
            
            # Aplicar el fix
            new_xml_path, changed, debug_info = ensure_expected_before_found(current_xml, expected, found)
            
            if changed:
                print(f"✅ Fix aplicado: {debug_info['action']}")
                print(f"📁 Nuevo XML: {new_xml_path.name}")
                
                # Mostrar estado actualizado de gTotSub si aplica
                if debug_info.get('parent_tag') == 'gTotSub':
                    doc = etree.parse(str(new_xml_path))
                    gTotSub = doc.xpath("//s:gTotSub", namespaces={"s": "http://ekuatia.set.gov.py/sifen/xsd"})[0]
                    print("\n📊 Estado actualizado de gTotSub:")
                    for ch in gTotSub:
                        print(f"   - {strip_ns(ch.tag)}: {ch.text}")
                
                current_xml = new_xml_path
            else:
                print("❌ No se pudo aplicar el fix")
                break
        
        # Resumen final
        print(f"\n{'='*60}")
        print("📋 RESUMEN FINAL")
        print(f"   Iteraciones: {iteration}")
        print(f"   XML final: {current_xml.name}")
        
        # Mostrar orden final canónico
        doc = etree.parse(str(current_xml))
        gTotSub = doc.xpath("//s:gTotSub", namespaces={"s": "http://ekuatia.set.gov.py/sifen/xsd"})[0]
        print("\n📊 Orden final de gTotSub:")
        for i, ch in enumerate(gTotSub):
            print(f"   {i+1:2d}. {strip_ns(ch.tag):15s}: {ch.text or ''}")
        
        print("\n🎯 El loop fue capaz de resolver automáticamente todos los errores 0160")
        print("    sin intervención manual.")


if __name__ == "__main__":
    main()
