#!/usr/bin/env python3
"""
Fix for SIFEN error 0160 - SOAP namespace issue
The KB shows we should use xmlns:xsd instead of xmlns:sifen
"""

import sys
import os
sys.path.append(os.path.join(os.path.dirname(__file__), '..', 'tesaka-cv'))

def fix_build_r_envio_lote_namespace():
    """Apply the fix to use xsd prefix instead of sifen"""
    
    file_path = "../tesaka-cv/tools/send_sirecepde.py"
    
    print("=== Fixing SOAP namespace for error 0160 ===\n")
    
    # Read the file
    with open(file_path, 'r', encoding='utf-8') as f:
        content = f.read()
    
    # Find the line to replace
    old_line = '    rEnvioLote = etree.Element(etree.QName(SIFEN_NS, "rEnvioLote"), nsmap={"sifen": SIFEN_NS})'
    new_line = '    rEnvioLote = etree.Element(etree.QName(SIFEN_NS, "rEnvioLote"), nsmap={"xsd": SIFEN_NS})'
    
    if old_line in content:
        # Replace the line
        content = content.replace(old_line, new_line)
        
        # Write back
        with open(file_path, 'w', encoding='utf-8') as f:
            f.write(content)
        
        print("✅ Fixed line 5027:")
        print(f"   Old: {old_line}")
        print(f"   New: {new_line}")
        print("\n📝 According to SIFEN KB (line 400-406), the SOAP should use:")
        print("   xmlns:xsd=\"http://ekuatia.set.gov.py/sifen/xsd\"")
        print("   <xsd:rEnvioLote>")
        print("   <xsd:dId>...</xsd:dId>")
        print("   <xsd:xDE>...</xsd:xDE>")
        print("\n⚠️  Note: This changes the XML from <sifen:rEnvioLote> to <xsd:rEnvioLote>")
        
        return True
    else:
        print("❌ Could not find the line to replace!")
        print("   Looking for:")
        print(f"   {old_line}")
        return False

if __name__ == "__main__":
    if fix_build_r_envio_lote_namespace():
        print("\n✅ Fix applied successfully!")
        print("🔄 Please retry sending to SIFEN to test if error 0160 is resolved.")
    else:
        print("\n❌ Fix failed - manual intervention required.")
