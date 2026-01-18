#!/usr/bin/env python3
"""Test script to verify ZIP delta fix - TESAKA now matches TIPS format"""

import base64
import zipfile
import io
import re
from pathlib import Path

def test_zip_format():
    """Test that ZIP format matches TIPS exactly"""
    
    # Load a sample signed XML
    sample_xml = Path("test_rde_final_correct.xml").read_bytes() if Path("test_rde_final_correct.xml").exists() else None
    
    if not sample_xml:
        print("❌ No se encontró test_rde_final_correct.xml")
        return
    
    # Import the function to test
    import sys
    sys.path.insert(0, str(Path(__file__).parent / "tesaka-cv"))
    
    from tools.send_sirecepde import build_lote_passthrough_signed
    
    # Build ZIP using the updated function
    zip_b64, lote_xml_bytes, zip_bytes = build_lote_passthrough_signed(sample_xml, return_debug=True)
    
    print("🔍 Verificando formato del ZIP generado...")
    
    # Check ZIP format
    with zipfile.ZipFile(io.BytesIO(zip_bytes), 'r') as zf:
        namelist = zf.namelist()
        print(f"   📁 Archivos en ZIP: {namelist}")
        
        if "xml_file.xml" not in namelist:
            print("   ❌ ERROR: ZIP no contiene 'xml_file.xml'")
            return
        else:
            print("   ✅ ZIP contiene 'xml_file.xml'")
        
        # Check compression
        for info in zf.infolist():
            if info.filename == "xml_file.xml":
                comp_method = info.compress_type
                comp_name = zipfile.ZIP_STORED if comp_method == zipfile.ZIP_STORED else "DEFLATED"
                print(f"   🗜️  Compresión: {comp_name} ({'STORED' if comp_method == zipfile.ZIP_STORED else 'DEFLATED'})")
                
                if comp_method != zipfile.ZIP_STORED:
                    print("   ❌ ERROR: ZIP debe usar STORED (sin compresión)")
                else:
                    print("   ✅ ZIP usa STORED (sin compresión)")
        
        # Read and check content
        content = zf.read("xml_file.xml")
        print(f"   📄 Tamaño: {len(content)} bytes")
        
        # Check XML declaration and wrapper
        content_str = content.decode('utf-8', errors='replace')
        
        if content_str.startswith('<?xml version="1.0" encoding="UTF-8"?>'):
            print("   ✅ Inicia con XML declaration")
        else:
            print("   ❌ ERROR: No inicia con XML declaration")
        
        # Check for double rLoteDE wrapper
        if '<rLoteDE><rLoteDE xmlns="http://ekuatia.set.gov.py/sifen/xsd">' in content_str:
            print("   ✅ Tiene wrapper doble rLoteDE")
        elif '<rLoteDE><rLoteDE' in content_str:
            print("   ✅ Tiene wrapper doble rLoteDE")
        else:
            print("   ❌ ERROR: No tiene wrapper doble rLoteDE")
            print(f"   Inicio: {content_str[:100]}...")
        
        # Extract inner XML to verify it's valid
        wrapper_match = re.search(rb'<rLoteDE>(.*)</rLoteDE>', content, re.DOTALL)
        if wrapper_match:
            inner_xml = wrapper_match.group(1)
            print(f"   📦 XML interno extraído: {len(inner_xml)} bytes")
            
            # Quick validation
            try:
                from lxml import etree
                root = etree.fromstring(inner_xml)
                if root.tag.endswith('rLoteDE'):
                    print("   ✅ XML interno válido (root: rLoteDE)")
                else:
                    print(f"   ❌ ERROR: Root del XML interno es {root.tag}")
            except Exception as e:
                print(f"   ❌ ERROR: XML interno no es válido: {e}")
    
    print("\n✅ Test completado - El ZIP ahora debería coincidir con TIPS")

if __name__ == "__main__":
    test_zip_format()
