#!/usr/bin/env python3
"""
Comprehensive diagnostic script for SIFEN XMLDSIG issues.
This script attempts to reproduce the exact signing process to understand digest mismatches.
"""

import sys
import base64
import hashlib
import os
import tempfile
import subprocess
from pathlib import Path

from lxml import etree

# Namespaces
NS = {
    'ds': 'http://www.w3.org/2000/09/xmldsig#',
    'sifen': 'http://ekuatia.set.gov.py/sifen/xsd'
}

def check_xmlsec_version():
    """Check xmlsec1 version and availability."""
    try:
        result = subprocess.run(['xmlsec1', '--version'], capture_output=True, text=True)
        if result.returncode == 0:
            print(f"xmlsec1 version: {result.stdout.strip()}")
            return True
    except FileNotFoundError:
        pass
    print("❌ xmlsec1 not found in PATH")
    return False

def extract_signature_info(xml_file):
    """Extract all signature information from XML."""
    try:
        parser = etree.XMLParser(remove_blank_text=False)
        xml_doc = etree.parse(str(xml_file), parser)
        root = xml_doc.getroot()
    except Exception as e:
        print(f"Error parsing XML: {e}")
        return None
    
    # Find signature
    signature = root.xpath('//ds:Signature', namespaces=NS)
    if not signature:
        print("No ds:Signature found in XML")
        return None
    
    signature = signature[0]
    
    # Extract SignedInfo details
    signed_info = signature.xpath('./ds:SignedInfo', namespaces=NS)[0]
    
    # CanonicalizationMethod
    canon_method = signed_info.xpath('./ds:CanonicalizationMethod', namespaces=NS)[0]
    canon_alg = canon_method.get('Algorithm')
    
    # SignatureMethod
    sig_method = signed_info.xpath('./ds:SignatureMethod', namespaces=NS)[0]
    sig_alg = sig_method.get('Algorithm')
    
    # Reference details
    reference = signed_info.xpath('./ds:Reference', namespaces=NS)[0]
    ref_uri = reference.get('URI')
    
    # Transforms
    transforms = reference.xpath('./ds:Transforms', namespaces=NS)
    transform_algs = []
    if transforms:
        transform_elems = transforms[0].xpath('./ds:Transform', namespaces=NS)
        for t in transform_elems:
            transform_algs.append(t.get('Algorithm'))
    
    # DigestMethod and DigestValue
    digest_method = reference.xpath('./ds:DigestMethod', namespaces=NS)[0]
    digest_alg = digest_method.get('Algorithm')
    digest_value = reference.xpath('./ds:DigestValue', namespaces=NS)[0].text.strip()
    
    return {
        'canonicalization_algorithm': canon_alg,
        'signature_algorithm': sig_alg,
        'reference_uri': ref_uri,
        'transforms': transform_algs,
        'digest_algorithm': digest_alg,
        'digest_value': digest_value,
        'xml_doc': xml_doc,
        'root': root
    }

def test_xmlsec_verify(xml_file):
    """Try to verify with xmlsec1 to get detailed error information."""
    print("\n=== xmlsec1 Verification Attempt ===")
    
    # Try different verification options
    cmd_options = [
        # Basic verify
        ['xmlsec1', '--verify', '--insecure', str(xml_file)],
        # With Id attribute
        ['xmlsec1', '--verify', '--insecure', '--id-attr:Id', 'DE', str(xml_file)],
        # With verbose output
        ['xmlsec1', '--verify', '--insecure', '--verbose', str(xml_file)]
    ]
    
    for i, cmd in enumerate(cmd_options):
        print(f"\n--- Attempt {i+1}: {' '.join(cmd)} ---")
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.stdout:
            print(f"STDOUT:\n{result.stdout}")
        if result.stderr:
            print(f"STDERR:\n{result.stderr}")
        print(f"Return code: {result.returncode}")

def create_test_xml_with_de_content(xml_file):
    """Extract just the DE content to test signing in isolation."""
    sig_info = extract_signature_info(xml_file)
    if not sig_info:
        return None
    
    # Find the DE element
    ref_uri = sig_info['reference_uri']
    if ref_uri and ref_uri.startswith('#'):
        de_id = ref_uri[1:]
        de_elem = sig_info['root'].xpath(f'//*[@Id="{de_id}"]')
        if de_elem:
            de_elem = de_elem[0]
            
            # Create a standalone XML with just the DE
            standalone_xml = etree.tostring(
                de_elem,
                encoding='utf-8',
                xml_declaration=True,
                standalone=False
            )
            
            return standalone_xml, sig_info
    
    return None

def main():
    if len(sys.argv) != 2:
        print("Usage: python3 tools/dsig_debug_comprehensive.py <xml_file>")
        print("  This script provides comprehensive analysis of SIFEN signature issues")
        sys.exit(1)
    
    xml_file = Path(sys.argv[1])
    if not xml_file.exists():
        print(f"Error: File {xml_file} does not exist")
        sys.exit(1)
    
    print(f"=== Comprehensive SIFEN Signature Analysis ===")
    print(f"File: {xml_file}\n")
    
    # Check xmlsec1 availability
    has_xmlsec = check_xmlsec_version()
    
    # Extract signature information
    sig_info = extract_signature_info(xml_file)
    if not sig_info:
        sys.exit(1)
    
    print("\n=== Signature Details ===")
    print(f"Canonicalization: {sig_info['canonicalization_algorithm']}")
    print(f"Signature Method: {sig_info['signature_algorithm']}")
    print(f"Reference URI: {sig_info['reference_uri']}")
    print(f"Transforms: {len(sig_info['transforms'])}")
    for alg in sig_info['transforms']:
        print(f"  - {alg}")
    print(f"Digest Method: {sig_info['digest_algorithm']}")
    print(f"Digest Value: {sig_info['digest_value']}")
    
    # Try xmlsec verification
    if has_xmlsec:
        test_xmlsec_verify(xml_file)
    
    # Create test with DE content only
    print("\n=== DE Content Analysis ===")
    de_result = create_test_xml_with_de_content(xml_file)
    if de_result:
        de_xml, _ = de_result
        
        # Save DE content for manual inspection
        output_dir = xml_file.parent / 'debug_output'
        output_dir.mkdir(exist_ok=True)
        
        de_file = output_dir / f'{xml_file.stem}_DE_only.xml'
        de_file.write_bytes(de_xml)
        print(f"DE content saved to: {de_file}")
        
        # Show first few lines
        de_lines = de_xml.decode('utf-8').split('\n')[:10]
        print("\nFirst 10 lines of DE content:")
        for line in de_lines:
            print(f"  {line}")
    
    print("\n=== Analysis Complete ===")
    print("\nPossible causes for digest mismatch:")
    print("1. The XML was modified after signing (whitespace, namespace changes)")
    print("2. The wrong transforms are being applied during verification")
    print("3. The reference URI points to a different node than was signed")
    print("4. Namespace context is different between signing and verification")
    print("5. The signature was created with different canonicalization parameters")

if __name__ == '__main__':
    main()
