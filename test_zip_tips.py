#!/usr/bin/env python3
"""
Test script para verificar que el ZIP se crea exactamente como TIPS lo requiere.
"""

import base64
import zipfile
import io
from pathlib import Path
import sys
import os

# Agregar el path correcto
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'tesaka-cv'))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'tesaka-cv', 'app'))

from tools.send_sirecepde import build_xde_zip_bytes_from_lote_xml

def test_zip_creation():
    # XML de prueba (sin XML declaration)
    lote_xml = '''<rLoteDE xmlns="http://ekuatia.set.gov.py/sifen/xsd">
  <rDE Id="rDE123">
    <dVerFor>150</dVerFor>
    <DE Id="DE123">
      <!-- contenido del DE -->
    </DE>
    <Signature xmlns="http://www.w3.org/2000/09/xmldsig#">
      <!-- firma -->
    </Signature>
  </rDE>
</rLoteDE>'''
    
    print("Testing build_xde_zip_bytes_from_lote_xml...")
    
    # Crear ZIP usando el helper
    zip_bytes = build_xde_zip_bytes_from_lote_xml(lote_xml)
    
    print(f"✅ ZIP creado: {len(zip_bytes)} bytes")
    
    # Verificar contenido del ZIP
    with zipfile.ZipFile(io.BytesIO(zip_bytes), 'r') as zf:
        namelist = zf.namelist()
        print(f"✅ ZIP_NAMES: {namelist}")
        
        # Verificar que solo contenga xml_file.xml
        assert namelist == ['xml_file.xml'], f"Expected ['xml_file.xml'], got {namelist}"
        
        # Verificar método de compresión
        info = zf.getinfo('xml_file.xml')
        print(f"✅ Compression method: {info.compress_type} (0=stored, 8=deflated)")
        assert info.compress_type == zipfile.ZIP_STORED, "Expected ZIP_STORED (no compression)"
        
        # Leer contenido y verificar estructura
        content = zf.read('xml_file.xml').decode('utf-8')
        print(f"✅ Content length: {len(content)} bytes")
        
        # Verificar header
        expected_header = '<?xml version="1.0" encoding="UTF-8"?><rLoteDE>'
        assert content.startswith(expected_header), f"Content should start with {expected_header}"
        
        # Verificar wrapper
        assert content.endswith('</rLoteDE>'), "Content should end with </rLoteDE>"
        
        # Verificar que contiene el XML interno
        assert '<rLoteDE xmlns="http://ekuatia.set.gov.py/sifen/xsd">' in content
        
        print("✅ HEAD(160):", content[:160])
        
        # Extraer el XML interno
        import re
        wrapper_match = re.search(r'<rLoteDE>(.*)</rLoteDE>', content, re.DOTALL)
        if wrapper_match:
            inner_xml = wrapper_match.group(1)
            print(f"✅ Inner XML extracted: {len(inner_xml)} bytes")
            assert inner_xml.startswith('<rLoteDE xmlns=')
            assert inner_xml.endswith('</rLoteDE>')
        
    print("\n✅ All tests passed! ZIP created exactly as TIPS requires.")

if __name__ == "__main__":
    test_zip_creation()
