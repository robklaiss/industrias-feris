#!/usr/bin/env python3
"""
Diagnostic script for XMLDSIG Reference digest mismatch.
Analyzes which canonicalization method matches the digest in the signature.
"""

import sys
import base64
import hashlib
import os
from pathlib import Path

from lxml import etree

# Namespaces
NS = {
    'ds': 'http://www.w3.org/2000/09/xmldsig#',
    'sifen': 'http://ekuatia.set.gov.py/sifen/xsd'
}

def find_signature_and_reference(xml_doc):
    """Find ds:Signature and ds:Reference elements."""
    # Find Signature
    signature = xml_doc.xpath('//ds:Signature', namespaces=NS)
    if not signature:
        raise ValueError("No ds:Signature found in XML")
    signature = signature[0]
    
    # Find Reference
    reference = signature.xpath('.//ds:Reference', namespaces=NS)
    if not reference:
        raise ValueError("No ds:Reference found in Signature")
    reference = reference[0]
    
    return signature, reference

def extract_reference_info(reference):
    """Extract URI and DigestValue from Reference."""
    uri = reference.get('URI')
    if not uri or not uri.startswith('#'):
        raise ValueError(f"Invalid or missing URI: {uri}")
    
    digest_value = reference.xpath('.//ds:DigestValue', namespaces=NS)
    if not digest_value:
        raise ValueError("No DigestValue found in Reference")
    digest_value = digest_value[0].text.strip()
    
    return uri[1:], digest_value  # Remove '#' from URI

def find_referenced_node(xml_doc, node_id):
    """Find the node referenced by Id."""
    # Try with @Id attribute
    node = xml_doc.xpath(f'//*[@Id="{node_id}"]')
    if not node:
        # Try with @id attribute (lowercase)
        node = xml_doc.xpath(f'//*[@id="{node_id}"]')
    if not node:
        raise ValueError(f"No node found with Id='{node_id}'")
    
    return node[0]

def apply_transforms(node, transform_algorithms):
    """Apply transforms to the node before canonicalization.
    
    Args:
        node: The XML node to transform
        transform_algorithms: List of transform algorithm URIs
    
    Returns:
        Transformed node
    """
    transformed_node = node
    
    for algorithm in transform_algorithms:
        if algorithm == "http://www.w3.org/2000/09/xmldsig#enveloped-signature":
            # Remove any Signature elements within this node
            signatures = transformed_node.xpath('.//ds:Signature', namespaces=NS)
            removed = 0
            for sig in signatures:
                sig.getparent().remove(sig)
                removed += 1
            if removed == 0:
                print("Note: No Signature found inside the referenced node for enveloped-signature transform")
        elif algorithm == "http://www.w3.org/2001/10/xml-exc-c14n#":
            # This is handled during canonicalization, not as a separate transform
            pass
        else:
            print(f"Warning: Unknown transform algorithm: {algorithm}")
    
    return transformed_node

def canonicalize_and_digest(node, method='inclusive', inclusive_prefixes=None):
    """Canonicalize node and return digest."""
    if method == 'inclusive':
        c14n = etree.tostring(
            node,
            method='c14n',
            exclusive=False,
            with_comments=False
        )
    elif method == 'exclusive':
        c14n = etree.tostring(
            node,
            method='c14n',
            exclusive=True,
            with_comments=False,
            inclusive_ns_prefixes=inclusive_prefixes
        )
    else:
        raise ValueError(f"Unknown canonicalization method: {method}")
    
    # Calculate SHA256 digest
    digest = hashlib.sha256(c14n).digest()
    digest_b64 = base64.b64encode(digest).decode('ascii')
    
    return digest_b64, c14n

def main():
    if len(sys.argv) != 2:
        print("Usage: python3 tools/dsig_debug_reference.py <xml_file>")
        print("  xml_file should be lote_extraido.xml or rde_from_lote.xml")
        sys.exit(1)
    
    xml_file = Path(sys.argv[1])
    if not xml_file.exists():
        print(f"Error: File {xml_file} does not exist")
        sys.exit(1)
    
    print(f"\n=== Analyzing file: {xml_file} ===\n")
    
    # Parse XML
    try:
        parser = etree.XMLParser(remove_blank_text=True)
        xml_doc = etree.parse(str(xml_file), parser)
        root = xml_doc.getroot()
    except Exception as e:
        print(f"Error parsing XML: {e}")
        sys.exit(1)
    
    # Find signature and reference
    try:
        signature, reference = find_signature_and_reference(root)
        ref_id, digest_value = extract_reference_info(reference)
    except ValueError as e:
        print(f"Error: {e}")
        sys.exit(1)
    
    print(f"Reference URI: #{ref_id}")
    print(f"DigestValue (from XML): {digest_value}\n")
    
    # Extract transforms from Reference
    transforms_elem = reference.xpath('./ds:Transforms', namespaces=NS)
    transform_algorithms = []
    if transforms_elem:
        transform_elems = transforms_elem[0].xpath('./ds:Transform', namespaces=NS)
        for t in transform_elems:
            transform_algorithms.append(t.get('Algorithm'))
    
    print(f"Transforms found: {len(transform_algorithms)}")
    for alg in transform_algorithms:
        print(f"  - {alg}")
    print()
    
    # Find referenced node
    try:
        ref_node = find_referenced_node(root, ref_id)
    except ValueError as e:
        print(f"Error: {e}")
        sys.exit(1)
    
    # Apply transforms
    ref_node = apply_transforms(ref_node, transform_algorithms)
    
    # Prepare output directory
    output_dir = xml_file.parent / 'debug_output'
    output_dir.mkdir(exist_ok=True)
    
    # Test different canonicalization methods
    results = []
    
    # Method 1: Inclusive C14N
    inc_digest, inc_c14n = canonicalize_and_digest(ref_node, method='inclusive')
    inc_match = inc_digest == digest_value
    results.append(('Inclusive C14N', inc_digest, inc_match))
    
    # Save inclusive C14N
    inc_file = output_dir / f'{xml_file.stem}_{ref_id}_inclusive.c14n'
    inc_file.write_bytes(inc_c14n)
    
    # Method 2: Exclusive C14N
    exc_digest, exc_c14n = canonicalize_and_digest(ref_node, method='exclusive')
    exc_match = exc_digest == digest_value
    results.append(('Exclusive C14N', exc_digest, exc_match))
    
    # Save exclusive C14N
    exc_file = output_dir / f'{xml_file.stem}_{ref_id}_exclusive.c14n'
    exc_file.write_bytes(exc_c14n)
    
    # Method 3: Exclusive C14N with ds prefix
    exc_ds_digest, exc_ds_c14n = canonicalize_and_digest(
        ref_node, 
        method='exclusive', 
        inclusive_prefixes=['ds']
    )
    exc_ds_match = exc_ds_digest == digest_value
    results.append(('Exclusive C14N (ds inclusive)', exc_ds_digest, exc_ds_match))
    
    # Save exclusive C14N with ds
    exc_ds_file = output_dir / f'{xml_file.stem}_{ref_id}_exclusive_ds.c14n'
    exc_ds_file.write_bytes(exc_ds_c14n)
    
    # Print results
    print("=== Digest Comparison Results ===\n")
    
    for method, digest, match in results:
        status = "✅ MATCH" if match else "❌ NO MATCH"
        print(f"{method}:")
        print(f"  Calculated: {digest}")
        print(f"  Status: {status}\n")
    
    # Print file paths
    print("=== Generated Files ===\n")
    print(f"Inclusive C14N: {inc_file}")
    print(f"Exclusive C14N: {exc_file}")
    print(f"Exclusive C14N (ds): {exc_ds_file}\n")
    
    # Summary
    matching_methods = [m for m, _, match in results if match]
    if matching_methods:
        print(f"✅ Matching method(s): {', '.join(matching_methods)}")
    else:
        print("❌ No methods matched the digest. This indicates a potential issue with:")
        print("   - The transform applied during signing")
        print("   - The node selection (different node was signed)")
        print("   - The XML was modified after signing")

if __name__ == '__main__':
    main()
