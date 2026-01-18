#!/usr/bin/env python3
"""
FASE C - SIFEN Strict Lote Checker
Non-XSD validation rules that SIFEN might enforce but aren't in the XSD.
"""
import sys
from lxml import etree

def strict_check(xml_path):
    """Perform strict non-XSD checks on lote XML."""
    
    try:
        tree = etree.parse(xml_path)
        root = tree.getroot()
    except Exception as e:
        print(f"FATAL: Cannot parse XML: {e}")
        return False
    
    NS = {
        's': 'http://ekuatia.set.gov.py/sifen/xsd',
        'ds': 'http://www.w3.org/2000/09/xmldsig#'
    }
    
    issues = []
    warnings = []
    
    print("=" * 80)
    print("SIFEN STRICT LOTE CHECK - FASE C")
    print("=" * 80)
    print(f"File: {xml_path}")
    print()
    
    # Rule 1: Check for duplicate IDs
    print("Rule 1: Checking for duplicate IDs...")
    all_ids = root.xpath('//*[@Id]')
    id_values = [elem.get('Id') for elem in all_ids]
    id_counts = {}
    for id_val in id_values:
        id_counts[id_val] = id_counts.get(id_val, 0) + 1
    
    duplicates = {k: v for k, v in id_counts.items() if v > 1}
    if duplicates:
        issues.append(f"DUPLICATE IDs: {duplicates}")
        print(f"  ✗ FAIL: Duplicate IDs found: {duplicates}")
    else:
        print("  ✓ PASS: No duplicate IDs")
    print()
    
    # Rule 2: Signature position check
    print("Rule 2: Checking Signature position...")
    rde = root.find('.//s:rDE', NS)
    if rde is not None:
        rde_children = list(rde)
        sig_index = None
        de_index = None
        
        for i, child in enumerate(rde_children):
            local_name = child.tag.split('}')[-1] if '}' in child.tag else child.tag
            if local_name == 'Signature':
                sig_index = i
            elif local_name == 'DE':
                de_index = i
        
        if sig_index is not None and de_index is not None:
            if sig_index != de_index + 1:
                issues.append(f"Signature is not immediately after DE (DE at {de_index}, Signature at {sig_index})")
                print(f"  ✗ FAIL: Signature not immediately after DE")
            else:
                print("  ✓ PASS: Signature immediately after DE")
        else:
            warnings.append("Could not find both DE and Signature in rDE")
            print("  ⚠ WARNING: Could not verify Signature position")
    else:
        issues.append("No rDE element found")
        print("  ✗ FAIL: No rDE element")
    print()
    
    # Rule 3: Check for prefixes in SIFEN namespace elements
    print("Rule 3: Checking for forbidden prefixes in SIFEN namespace...")
    sifen_elements = root.xpath('//*[namespace-uri()="http://ekuatia.set.gov.py/sifen/xsd"]')
    bad_prefixes = []
    for elem in sifen_elements:
        # Check if element has a prefix in its serialized form
        tag = elem.tag
        if '}' in tag:
            # Has namespace, check local name
            local_name = tag.split('}')[-1]
            if local_name.startswith('ds'):
                bad_prefixes.append(local_name)
    
    if bad_prefixes:
        issues.append(f"SIFEN elements with 'ds' prefix: {set(bad_prefixes)}")
        print(f"  ✗ FAIL: Found SIFEN elements starting with 'ds': {set(bad_prefixes)}")
    else:
        print("  ✓ PASS: No 'ds' prefixes in SIFEN elements")
    print()
    
    # Rule 4: Reference URI validation
    print("Rule 4: Checking Reference URI...")
    sig = root.find('.//ds:Signature', NS) or root.find('.//{http://www.w3.org/2000/09/xmldsig#}Signature')
    if sig is not None:
        signed_info = sig.find('ds:SignedInfo', NS) or sig.find('{http://www.w3.org/2000/09/xmldsig#}SignedInfo')
        if signed_info is not None:
            refs = signed_info.findall('ds:Reference', NS) or signed_info.findall('{http://www.w3.org/2000/09/xmldsig#}Reference')
            
            for i, ref in enumerate(refs, 1):
                uri = ref.get('URI', '')
                
                if not uri:
                    issues.append(f"Reference #{i} has EMPTY URI (high risk)")
                    print(f"  ✗ FAIL: Reference #{i} has empty URI")
                elif not uri.startswith('#'):
                    warnings.append(f"Reference #{i} URI '{uri}' does not start with #")
                    print(f"  ⚠ WARNING: Reference #{i} URI doesn't start with #: {uri}")
                else:
                    target_id = uri[1:]
                    if target_id not in id_values:
                        issues.append(f"Reference #{i} URI '{uri}' points to non-existent Id")
                        print(f"  ✗ FAIL: Reference #{i} points to non-existent Id: {target_id}")
                    else:
                        print(f"  ✓ PASS: Reference #{i} URI valid: {uri}")
        else:
            warnings.append("No SignedInfo found in Signature")
            print("  ⚠ WARNING: No SignedInfo in Signature")
    else:
        warnings.append("No Signature found")
        print("  ⚠ WARNING: No Signature element")
    print()
    
    # Rule 5: CanonicalizationMethod validation
    print("Rule 5: Checking CanonicalizationMethod...")
    if sig is not None and signed_info is not None:
        canon = signed_info.find('ds:CanonicalizationMethod', NS) or signed_info.find('{http://www.w3.org/2000/09/xmldsig#}CanonicalizationMethod')
        if canon is not None:
            algo = canon.get('Algorithm', '')
            accepted_algos = [
                'http://www.w3.org/2001/10/xml-exc-c14n#',
                'http://www.w3.org/TR/2001/REC-xml-c14n-20010315',
                'http://www.w3.org/2006/12/xml-c14n11'
            ]
            if algo not in accepted_algos:
                warnings.append(f"Unusual CanonicalizationMethod: {algo}")
                print(f"  ⚠ WARNING: Unusual canonicalization: {algo}")
            else:
                print(f"  ✓ PASS: Standard canonicalization: {algo}")
        else:
            issues.append("No CanonicalizationMethod found")
            print("  ✗ FAIL: No CanonicalizationMethod")
    print()
    
    # Rule 6: Transform validation
    print("Rule 6: Checking Transforms...")
    if sig is not None and signed_info is not None:
        refs = signed_info.findall('ds:Reference', NS) or signed_info.findall('{http://www.w3.org/2000/09/xmldsig#}Reference')
        for i, ref in enumerate(refs, 1):
            transforms = ref.find('ds:Transforms', NS) or ref.find('{http://www.w3.org/2000/09/xmldsig#}Transforms')
            if transforms is not None:
                transform_list = transforms.findall('ds:Transform', NS) or transforms.findall('{http://www.w3.org/2000/09/xmldsig#}Transform')
                
                expected_transforms = [
                    'http://www.w3.org/2000/09/xmldsig#enveloped-signature',
                    'http://www.w3.org/2001/10/xml-exc-c14n#'
                ]
                
                actual_algos = [t.get('Algorithm', '') for t in transform_list]
                
                # Check for suspicious transforms
                suspicious = []
                for algo in actual_algos:
                    if algo not in expected_transforms and 'c14n' not in algo.lower():
                        suspicious.append(algo)
                
                if suspicious:
                    warnings.append(f"Reference #{i} has unusual transforms: {suspicious}")
                    print(f"  ⚠ WARNING: Reference #{i} unusual transforms: {suspicious}")
                else:
                    print(f"  ✓ PASS: Reference #{i} has standard transforms")
            else:
                warnings.append(f"Reference #{i} has no Transforms")
                print(f"  ⚠ WARNING: Reference #{i} has no Transforms")
    print()
    
    # Rule 7: Check rDE structure
    print("Rule 7: Checking rDE structure...")
    if rde is not None:
        # Check for Id attribute on rDE
        rde_id = rde.get('Id')
        if not rde_id:
            issues.append("rDE missing Id attribute")
            print("  ✗ FAIL: rDE has no Id attribute")
        else:
            print(f"  ✓ PASS: rDE has Id: {rde_id}")
        
        # Check first child is dVerFor
        if len(rde) > 0:
            first_child = rde[0]
            first_child_name = first_child.tag.split('}')[-1] if '}' in first_child.tag else first_child.tag
            if first_child_name != 'dVerFor':
                issues.append(f"First child of rDE is '{first_child_name}', expected 'dVerFor'")
                print(f"  ✗ FAIL: First child is {first_child_name}, not dVerFor")
            else:
                dver_value = first_child.text
                if dver_value != '150':
                    warnings.append(f"dVerFor value is '{dver_value}', expected '150'")
                    print(f"  ⚠ WARNING: dVerFor = {dver_value} (expected 150)")
                else:
                    print("  ✓ PASS: dVerFor is first child with value 150")
        else:
            issues.append("rDE has no children")
            print("  ✗ FAIL: rDE is empty")
    print()
    
    # Rule 8: Check namespace declarations
    print("Rule 8: Checking namespace declarations...")
    
    # Check rLoteDE namespace
    rlote = root
    if rlote.tag.endswith('rLoteDE'):
        ns = rlote.nsmap.get(None)
        if ns != 'http://ekuatia.set.gov.py/sifen/xsd':
            issues.append(f"rLoteDE default namespace is '{ns}', expected SIFEN namespace")
            print(f"  ✗ FAIL: rLoteDE wrong namespace: {ns}")
        else:
            print("  ✓ PASS: rLoteDE has correct default namespace")
    
    # Check Signature namespace
    if sig is not None:
        sig_ns = sig.nsmap.get(None)
        if sig_ns != 'http://www.w3.org/2000/09/xmldsig#':
            warnings.append(f"Signature default namespace is '{sig_ns}', expected XMLDSig")
            print(f"  ⚠ WARNING: Signature namespace: {sig_ns}")
        else:
            print("  ✓ PASS: Signature has XMLDSig namespace")
    print()
    
    # Summary
    print("=" * 80)
    print("SUMMARY")
    print("=" * 80)
    
    if issues:
        print("CRITICAL ISSUES:")
        for issue in issues:
            print(f"  ✗ {issue}")
        print()
    
    if warnings:
        print("WARNINGS:")
        for warning in warnings:
            print(f"  ⚠ {warning}")
        print()
    
    if not issues and not warnings:
        print("✓ ALL CHECKS PASSED")
        print()
        return True
    elif not issues:
        print("✓ NO CRITICAL ISSUES (only warnings)")
        print()
        return True
    else:
        print(f"✗ VALIDATION FAILED: {len(issues)} critical issue(s)")
        print()
        return False

if __name__ == '__main__':
    if len(sys.argv) < 2:
        print("Usage: python sifen_strict_lote_check.py <lote.xml>")
        sys.exit(1)
    
    xml_file = sys.argv[1]
    success = strict_check(xml_file)
    sys.exit(0 if success else 1)
