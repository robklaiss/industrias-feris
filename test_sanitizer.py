#!/usr/bin/env python3
"""
Test script for the XMLDSIG prefix sanitizer
"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'tesaka-cv'))

from app.sifen_client.xmlsec_signer import _sanitize_xmldsig_prefixes

# Test XML with ds: prefixes
test_xml = b'''<?xml version="1.0" encoding="UTF-8"?>
<rDE xmlns="http://ekuatia.set.gov.py/sifen/xsd" dVerFor="150">
  <DE Id="test123">
    <dEncF>1</dEncF>
  </DE>
  <ds:Signature xmlns:ds="http://www.w3.org/2000/09/xmldsig#">
    <ds:SignedInfo>
      <ds:CanonicalizationMethod Algorithm="http://www.w3.org/2001/10/xml-exc-c14n#"/>
      <ds:SignatureMethod Algorithm="http://www.w3.org/2000/09/xmldsig#rsa-sha1"/>
      <ds:Reference URI="#test123">
        <ds:Transforms>
          <ds:Transform Algorithm="http://www.w3.org/2000/09/xmldsig#enveloped-signature"/>
          <ds:Transform Algorithm="http://www.w3.org/2001/10/xml-exc-c14n#"/>
        </ds:Transforms>
        <ds:DigestMethod Algorithm="http://www.w3.org/2000/09/xmldsig#sha1"/>
        <ds:DigestValue>abc123</ds:DigestValue>
      </ds:Reference>
    </ds:SignedInfo>
    <ds:SignatureValue>signature123</ds:SignatureValue>
    <ds:KeyInfo>
      <ds:X509Data>
        <ds:X509Certificate>cert123</ds:X509Certificate>
      </ds:X509Data>
    </ds:KeyInfo>
  </ds:Signature>
</rDE>'''

print("Testing XMLDSIG sanitizer...")
print("\nOriginal XML has ds: prefixes:", b"<ds:" in test_xml)
print("Original XML has xmlns:ds=:", b"xmlns:ds=" in test_xml)

try:
    sanitized = _sanitize_xmldsig_prefixes(test_xml)
    
    print("\nSanitized XML has ds: prefixes:", b"<ds:" in sanitized)
    print("Sanitized XML has xmlns:ds=:", b"xmlns:ds=" in sanitized)
    
    # Verify Signature element exists without prefix
    if b'<Signature xmlns="http://www.w3.org/2000/09/xmldsig#">' in sanitized:
        print("\n✓ Signature element correctly uses default namespace")
    else:
        print("\n✗ Signature element not found with expected format")
    
    # Save results for inspection
    with open("test_original.xml", "wb") as f:
        f.write(test_xml)
    with open("test_sanitized.xml", "wb") as f:
        f.write(sanitized)
    
    print("\nFiles saved:")
    print("- test_original.xml")
    print("- test_sanitized.xml")
    print("- artifacts/rde_signed_sanitized.xml")
    
    # Quick verification commands
    print("\nVerification commands:")
    print("grep -n '<ds:' test_sanitized.xml || echo 'OK: no <ds: found'")
    print("grep -n 'xmlns:ds' test_sanitized.xml || echo 'OK: no xmlns:ds found'")
    print("grep -c '<Signature' test_sanitized.xml")
    
except Exception as e:
    print(f"\nError: {e}")
    sys.exit(1)
