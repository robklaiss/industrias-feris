#!/usr/bin/env python3
"""
Test H2 fix: Verify Signature has explicit xmlns attribute after signing.
"""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from lxml import etree
from app.sifen_client.xmlsec_signer import sign_de_with_p12
from pathlib import Path

def test_signature_xmlns():
    """Test that signed XML has explicit xmlns on Signature."""
    
    # Use existing test DE
    test_xml_path = Path(__file__).parent.parent / "artifacts" / "_stage_03_clean.xml"
    if not test_xml_path.exists():
        print(f"ERROR: Test file not found: {test_xml_path}")
        return False
    
    # Read test XML
    with open(test_xml_path, 'rb') as f:
        xml_bytes = f.read()
    
    # Get P12 credentials from env
    p12_path = os.getenv('SIFEN_P12_PATH')
    p12_pass = os.getenv('SIFEN_P12_PASSWORD')
    
    if not p12_path or not p12_pass:
        print("ERROR: SIFEN_P12_PATH and SIFEN_P12_PASSWORD must be set")
        return False
    
    print("Signing test DE...")
    try:
        signed_bytes = sign_de_with_p12(xml_bytes, p12_path, p12_pass)
        print(f"✓ Signing successful, output: {len(signed_bytes)} bytes")
    except Exception as e:
        print(f"✗ Signing failed: {e}")
        import traceback
        traceback.print_exc()
        return False
    
    # Parse signed XML
    signed_str = signed_bytes.decode('utf-8')
    
    # Check for explicit xmlns on Signature
    print("\nChecking for explicit xmlns on Signature...")
    
    if '<Signature xmlns="http://www.w3.org/2000/09/xmldsig#"' in signed_str:
        print("✓ PASS: Found explicit xmlns on Signature tag")
        
        # Extract the actual Signature tag for verification
        import re
        sig_match = re.search(r'<Signature[^>]*>', signed_str)
        if sig_match:
            print(f"  Signature tag: {sig_match.group(0)}")
        
        # Save to artifacts for inspection
        output_path = Path(__file__).parent.parent / "artifacts" / "_h2_test_signed.xml"
        with open(output_path, 'wb') as f:
            f.write(signed_bytes)
        print(f"\n✓ Saved signed XML to: {output_path}")
        
        return True
    else:
        print("✗ FAIL: Signature tag does not have explicit xmlns attribute")
        
        # Show what we got
        import re
        sig_match = re.search(r'<Signature[^>]*>', signed_str)
        if sig_match:
            print(f"  Actual Signature tag: {sig_match.group(0)}")
        
        return False

if __name__ == '__main__':
    success = test_signature_xmlns()
    sys.exit(0 if success else 1)
