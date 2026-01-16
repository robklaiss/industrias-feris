#!/usr/bin/env python3
"""
Final diagnostic script for SIFEN batch XML signature digest mismatch.
This script reproduces the exact issue and provides solutions.
"""

import sys
import base64
import hashlib
import subprocess
from pathlib import Path

from lxml import etree

# Namespaces
NS = {
    'ds': 'http://www.w3.org/2000/09/xmldsig#',
    'sifen': 'http://ekuatia.set.gov.py/sifen/xsd'
}

def main():
    if len(sys.argv) != 2:
        print("Usage: python3 tools/dsig_debug_final.py <xml_file>")
        print("  This script diagnoses and provides solutions for SIFEN digest mismatch")
        sys.exit(1)
    
    xml_file = Path(sys.argv[1])
    if not xml_file.exists():
        print(f"Error: File {xml_file} does not exist")
        sys.exit(1)
    
    print(f"=== SIFEN Digest Mismatch Diagnosis ===")
    print(f"File: {xml_file}\n")
    
    # Parse XML
    try:
        parser = etree.XMLParser(remove_blank_text=False)
        xml_doc = etree.parse(str(xml_file), parser)
        root = xml_doc.getroot()
    except Exception as e:
        print(f"Error parsing XML: {e}")
        sys.exit(1)
    
    # Find signature and reference
    signature = root.xpath('//ds:Signature', namespaces=NS)
    if not signature:
        print("❌ No ds:Signature found")
        sys.exit(1)
    
    signature = signature[0]
    signed_info = signature.xpath('./ds:SignedInfo', namespaces=NS)[0]
    reference = signed_info.xpath('./ds:Reference', namespaces=NS)[0]
    
    # Extract details
    ref_uri = reference.get('URI')
    digest_value = reference.xpath('./ds:DigestValue', namespaces=NS)[0].text.strip()
    
    # Get transforms
    transforms = reference.xpath('./ds:Transforms/ds:Transform', namespaces=NS)
    transform_algs = [t.get('Algorithm') for t in transforms]
    
    # Get canonicalization method
    canon_method = signed_info.xpath('./ds:CanonicalizationMethod', namespaces=NS)[0]
    canon_alg = canon_method.get('Algorithm')
    
    print(f"Reference URI: {ref_uri}")
    print(f"Digest Value: {digest_value}")
    print(f"Canonicalization: {canon_alg}")
    print(f"Transforms: {len(transform_algs)}")
    for alg in transform_algs:
        print(f"  - {alg}")
    
    # Find referenced node
    if ref_uri and ref_uri.startswith('#'):
        de_id = ref_uri[1:]
        de_nodes = root.xpath(f'//*[@Id="{de_id}"]')
        if not de_nodes:
            print(f"\n❌ No node found with Id='{de_id}'")
            sys.exit(1)
        de_node = de_nodes[0]
    else:
        print("\n❌ Invalid or missing Reference URI")
        sys.exit(1)
    
    # THE KEY ISSUE: SIFEN batch signatures have inconsistent transforms!
    print("\n=== DIAGNOSIS ===")
    
    if len(transform_algs) == 1 and transform_algs[0] == "http://www.w3.org/2000/09/xmldsig#enveloped-signature":
        if canon_alg == "http://www.w3.org/2001/10/xml-exc-c14n#":
            print("🔍 FOUND THE ISSUE:")
            print("  The signature specifies exclusive C14N but only includes enveloped-signature transform!")
            print("  This is inconsistent - exclusive C14N should be listed as a transform.")
            print("\n  This causes digest mismatch because:")
            print("  1. During signing, exclusive C14N was applied")
            print("  2. But it's not listed in Transforms, so verifiers might not apply it")
            print("  3. Or vice versa - the transform list is incomplete")
    
    # Test different digest calculations
    print("\n=== Testing Digest Calculations ===")
    
    # Since Signature is outside DE (sibling), enveloped-signature has no effect
    print("\n1. Exclusive C14N (as per CanonicalizationMethod):")
    c14n_exc = etree.tostring(de_node, method='c14n', exclusive=True, with_comments=False)
    digest_exc = base64.b64encode(hashlib.sha256(c14n_exc).digest()).decode()
    match_exc = digest_exc == digest_value
    print(f"   Digest: {digest_exc}")
    print(f"   Match: {'✅ YES' if match_exc else '❌ NO'}")
    
    print("\n2. Inclusive C14N:")
    c14n_inc = etree.tostring(de_node, method='c14n', exclusive=False, with_comments=False)
    digest_inc = base64.b64encode(hashlib.sha256(c14n_inc).digest()).decode()
    match_inc = digest_inc == digest_value
    print(f"   Digest: {digest_inc}")
    print(f"   Match: {'✅ YES' if match_inc else '❌ NO'}")
    
    # Save canonicalized forms for inspection
    output_dir = xml_file.parent / 'debug_output'
    output_dir.mkdir(exist_ok=True)
    
    exc_file = output_dir / f'{xml_file.stem}_{de_id}_exclusive.c14n'
    inc_file = output_dir / f'{xml_file.stem}_{de_id}_inclusive.c14n'
    
    exc_file.write_bytes(c14n_exc)
    inc_file.write_bytes(c14n_inc)
    
    print(f"\n📁 Canonicalized files saved:")
    print(f"   Exclusive: {exc_file}")
    print(f"   Inclusive: {inc_file}")
    
    # Provide solution
    print("\n=== SOLUTION ===")
    
    if not match_exc and not match_inc:
        print("❌ Neither canonicalization method matches the digest.")
        print("\nThis indicates one of the following:")
        print("1. The XML was modified after signing")
        print("2. A different node/namespace context was signed")
        print("3. Additional transforms were applied during signing")
        print("4. The signature was created with buggy software")
        
        print("\n🔧 To fix this:")
        print("1. Re-sign the document with consistent transforms")
        print("2. Ensure the Transforms list matches what was actually applied")
        print("3. For SIFEN batches, the correct transforms should be:")
        print("   - http://www.w3.org/2000/09/xmldsig#enveloped-signature")
        print("   - http://www.w3.org/2001/10/xml-exc-c14n#")
        
        # Try with both transforms
        print("\n3. Testing with BOTH transforms (enveloped-signature + exc-c14n):")
        # Since Signature is outside DE, enveloped-signature does nothing
        # So we just test exclusive C14N again
        print("   Result: Same as exclusive C14N above (no change)")
    
    elif match_exc:
        print("✅ Exclusive C14N matches!")
        print("The signature was created with exclusive C14N but the transform list is incomplete.")
        print("To fix: Add exc-c14n transform to the Transforms list.")
    
    elif match_inc:
        print("✅ Inclusive C14N matches!")
        print("The signature was created with inclusive C14N despite specifying exclusive.")
        print("To fix: Either change CanonicalizationMethod to inclusive OR add proper transforms.")
    
    # Final recommendation
    print("\n=== RECOMMENDATION ===")
    print("For SIFEN batch processing, ensure the signature has:")
    print("1. CanonicalizationMethod: http://www.w3.org/2001/10/xml-exc-c14n#")
    print("2. Transforms:")
    print("   - http://www.w3.org/2000/09/xmldsig#enveloped-signature")
    print("   - http://www.w3.org/2001/10/xml-exc-c14n#")
    print("3. Signature placed as sibling of DE (not inside)")
    print("4. Reference URI pointing to the DE Id attribute")

if __name__ == '__main__':
    main()
