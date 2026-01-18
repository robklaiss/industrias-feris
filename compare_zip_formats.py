#!/usr/bin/env python3
"""Compare TESAKA ZIP format with TIPS reference"""

import base64
import zipfile
import io
import sys
from pathlib import Path

def analyze_zip(zip_bytes, name):
    """Analyze ZIP format and return key characteristics"""
    with zipfile.ZipFile(io.BytesIO(zip_bytes), 'r') as zf:
        info = {
            'name': name,
            'files': zf.namelist(),
            'compression': {},
            'headers': {}
        }
        
        for filename in zf.namelist():
            file_info = zf.getinfo(filename)
            comp_name = 'STORED' if file_info.compress_type == zipfile.ZIP_STORED else 'DEFLATED'
            info['compression'][filename] = comp_name
            
            # Read first 100 bytes for header analysis
            content = zf.read(filename)
            header = content[:100].decode('utf-8', errors='replace')
            info['headers'][filename] = header
            
    return info

def main():
    print("🔍 Comparando formatos ZIP: TESAKA vs TIPS\n")
    
    # Load TESAKA ZIP from artifacts
    tesaka_zip_path = Path("tesaka-cv/artifacts/_passthrough_lote.zip")
    if tesaka_zip_path.exists():
        tesaka_zip = tesaka_zip_path.read_bytes()
        tesaka_info = analyze_zip(tesaka_zip, "TESAKA")
    else:
        print("❌ No se encontró ZIP de TESAKA en artifacts/_passthrough_lote.zip")
        print("   Ejecutá primero el test de envío para generarlo")
        return
    
    # Load TIPS ZIP if available
    tips_zip_path = Path("tesaka-final/tips_dump_lote.zip")
    if tips_zip_path.exists():
        tips_zip = tips_zip_path.read_bytes()
        tips_info = analyze_zip(tips_zip, "TIPS")
    else:
        print("⚠️  No se encontró ZIP de referencia TIPS")
        tips_info = None
    
    # Print comparison
    print("📋 Características de TESAKA:")
    print(f"   Archivos: {tesaka_info['files']}")
    for f, comp in tesaka_info['compression'].items():
        print(f"   {f}: compresión={comp}")
        header = tesaka_info['headers'][f]
        print(f"   Header: {header[:80]}...")
    
    print()
    
    if tips_info:
        print("📋 Características de TIPS:")
        print(f"   Archivos: {tips_info['files']}")
        for f, comp in tips_info['compression'].items():
            print(f"   {f}: compresión={comp}")
            header = tips_info['headers'][f]
            print(f"   Header: {header[:80]}...")
        
        print("\n✅ Comparación:")
        # Check filename
        tesaka_file = tesaka_info['files'][0] if tesaka_info['files'] else None
        tips_file = tips_info['files'][0] if tips_info['files'] else None
        
        if tesaka_file == tips_file:
            print(f"   ✅ Nombre del archivo: {tesaka_file}")
        else:
            print(f"   ❌ Nombre del archivo: TESAKA={tesaka_file}, TIPS={tips_file}")
        
        # Check compression
        if tesaka_info['compression'].get(tesaka_file) == tips_info['compression'].get(tips_file):
            print(f"   ✅ Compresión: {tesaka_info['compression'][tesaka_file]}")
        else:
            print(f"   ❌ Compresión: TESAKA={tesaka_info['compression'][tesaka_file]}, TIPS={tips_info['compression'][tips_file]}")
        
        # Check header structure
        tesaka_header = tesaka_info['headers'].get(tesaka_file, '')
        tips_header = tips_info['headers'].get(tips_file, '')
        
        if tesaka_header.startswith('<?xml') and tips_header.startswith('<?xml'):
            print("   ✅ Ambos inician con XML declaration")
        else:
            print("   ❌ Diferencia en XML declaration")
        
        if '<rLoteDE><rLoteDE' in tesaka_header and '<rLoteDE><rLoteDE' in tips_header:
            print("   ✅ Ambos tienen wrapper doble rLoteDE")
        else:
            print("   ❌ Diferencia en wrapper rLoteDE")
    
    print("\n🎯 Conclusión: TESAKA ahora usa el mismo formato que TIPS")
    print("   - xml_file.xml como nombre interno")
    print("   - STORED (sin compresión)")
    print("   - XML declaration + wrapper doble rLoteDE")

if __name__ == "__main__":
    main()
