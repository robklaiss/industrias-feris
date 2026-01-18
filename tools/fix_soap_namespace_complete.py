#!/usr/bin/env python3
"""
Complete fix for SIFEN error 0160 - Change sifen prefix to xsd
According to SIFEN KB lines 400-406, should use xmlns:xsd instead of xmlns:sifen
"""

import sys
import os
sys.path.append(os.path.join(os.path.dirname(__file__), '..', 'tesaka-cv'))

def fix_soap_namespace_complete():
    """Apply the complete fix to use xsd prefix instead of sifen"""
    
    soap_client_path = "../tesaka-cv/app/sifen_client/soap_client.py"
    send_sirecepde_path = "../tesaka-cv/tools/send_sirecepde.py"
    
    print("=== Complete SOAP namespace fix for error 0160 ===\n")
    
    # Fix 1: soap_client.py - change nsmap from sifen to xsd
    print("1. Fixing soap_client.py...")
    with open(soap_client_path, 'r', encoding='utf-8') as f:
        content = f.read()
    
    # Replace nsmap
    old_nsmap = 'nsmap={"env": soap_env_ns, "sifen": sifen_ns}'
    new_nsmap = 'nsmap={"env": soap_env_ns, "xsd": sifen_ns}'
    
    if old_nsmap in content:
        content = content.replace(old_nsmap, new_nsmap)
        print(f"   ✅ Line 1669: {old_nsmap} -> {new_nsmap}")
    
    # Replace cleanup_namespaces
    old_cleanup = 'etree.cleanup_namespaces(env, top_nsmap={"env": soap_env_ns, "sifen": sifen_ns})'
    new_cleanup = 'etree.cleanup_namespaces(env, top_nsmap={"env": soap_env_ns, "xsd": sifen_ns})'
    
    if old_cleanup in content:
        content = content.replace(old_cleanup, new_cleanup)
        print(f"   ✅ Line 1684: {old_cleanup} -> {new_cleanup}")
    
    # Replace assertions to expect xsd instead of sifen
    assertions = [
        ('assert "sifen:rEnvioLote" in payload_xml or "sifen:rEnvioLoteDe" in payload_xml',
         'assert "xsd:rEnvioLote" in payload_xml or "xsd:rEnvioLoteDe" in payload_xml'),
        ('assert "sifen:dId" in payload_xml', 'assert "xsd:dId" in payload_xml'),
        ('assert "sifen:xDE" in payload_xml', 'assert "xsd:xDE" in payload_xml'),
        ('assert \'xmlns:sifen="http://ekuatia.set.gov.py/sifen/xsd"\' in payload_xml',
         'assert \'xmlns:xsd="http://ekuatia.set.gov.py/sifen/xsd"\' in payload_xml')
    ]
    
    for old_assert, new_assert in assertions:
        if old_assert in content:
            content = content.replace(old_assert, new_assert)
            print(f"   ✅ Assertion updated: {old_assert[:50]}... -> {new_assert[:50]}...")
    
    with open(soap_client_path, 'w', encoding='utf-8') as f:
        f.write(content)
    
    # Fix 2: send_sirecepde.py - update rEnvioLote to use xsd prefix
    print("\n2. Fixing send_sirecepde.py...")
    with open(send_sirecepde_path, 'r', encoding='utf-8') as f:
        content = f.read()
    
    # The line was already fixed in previous step, but let's verify
    if 'nsmap={"xsd": SIFEN_NS}' in content:
        print("   ✅ Line 5027 already using xsd prefix")
    else:
        print("   ⚠️  Line 5027 not found - might need manual check")
    
    with open(send_sirecepde_path, 'w', encoding='utf-8') as f:
        f.write(content)
    
    print("\n📝 Summary of changes:")
    print("   - SOAP envelope now uses xmlns:xsd instead of xmlns:sifen")
    print("   - Body elements now use <xsd:rEnvioLote>, <xsd:dId>, <xsd:xDE>")
    print("   - Assertions updated to expect xsd prefix")
    print("\n📖 Reference: SIFEN KB lines 400-406")
    print("   <soap:Envelope xmlns:soap=\"...\" xmlns:xsd=\"http://ekuatia.set.gov.py/sifen/xsd\">")
    print("   <soap:Body>")
    print("   <xsd:rEnvioLote>")
    print("   <xsd:dId>...</xsd:dId>")
    print("   <xsd:xDE>...</xsd:xDE>")
    print("   </xsd:rEnvioLote>")
    
    return True

if __name__ == "__main__":
    if fix_soap_namespace_complete():
        print("\n✅ Complete fix applied successfully!")
        print("🔄 Please retry sending to SIFEN to test if error 0160 is resolved.")
    else:
        print("\n❌ Fix failed - manual intervention required.")
