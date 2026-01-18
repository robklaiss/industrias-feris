#!/usr/bin/env python3
"""
FASE A - Signature Forensics Analyzer
Generates detailed report of XML signature structure and validates invariants.
"""
import sys
from lxml import etree
import hashlib
import base64

def analyze_signature(xml_path, output_path):
    """Generate detailed signature forensics report."""
    
    try:
        tree = etree.parse(xml_path)
        root = tree.getroot()
    except Exception as e:
        return f"ERROR: Cannot parse XML: {e}"
    
    NS = {
        's': 'http://ekuatia.set.gov.py/sifen/xsd',
        'ds': 'http://www.w3.org/2000/09/xmldsig#'
    }
    
    report_lines = []
    report_lines.append("=" * 80)
    report_lines.append("SIGNATURE FORENSICS REPORT - FASE A")
    report_lines.append("=" * 80)
    report_lines.append(f"File: {xml_path}")
    report_lines.append("")
    
    # Find Signature element
    sig = root.find('.//ds:Signature', NS)
    if sig is None:
        # Try without namespace prefix
        sig = root.find('.//{http://www.w3.org/2000/09/xmldsig#}Signature')
    
    if sig is None:
        report_lines.append("ERROR: No Signature element found!")
        return "\n".join(report_lines)
    
    report_lines.append("1. SIGNATURE ELEMENT FOUND")
    report_lines.append(f"   Namespace: {sig.nsmap.get(None, 'NO DEFAULT NS')}")
    report_lines.append(f"   Tag: {sig.tag}")
    report_lines.append("")
    
    # SignedInfo
    signed_info = sig.find('ds:SignedInfo', NS) or sig.find('{http://www.w3.org/2000/09/xmldsig#}SignedInfo')
    if signed_info is not None:
        report_lines.append("2. SIGNEDINFO")
        
        # CanonicalizationMethod
        canon = signed_info.find('ds:CanonicalizationMethod', NS) or signed_info.find('{http://www.w3.org/2000/09/xmldsig#}CanonicalizationMethod')
        if canon is not None:
            report_lines.append(f"   CanonicalizationMethod/@Algorithm: {canon.get('Algorithm', 'MISSING')}")
        else:
            report_lines.append("   CanonicalizationMethod: NOT FOUND")
        
        # SignatureMethod
        sig_method = signed_info.find('ds:SignatureMethod', NS) or signed_info.find('{http://www.w3.org/2000/09/xmldsig#}SignatureMethod')
        if sig_method is not None:
            report_lines.append(f"   SignatureMethod/@Algorithm: {sig_method.get('Algorithm', 'MISSING')}")
        else:
            report_lines.append("   SignatureMethod: NOT FOUND")
        
        report_lines.append("")
        
        # References
        refs = signed_info.findall('ds:Reference', NS) or signed_info.findall('{http://www.w3.org/2000/09/xmldsig#}Reference')
        report_lines.append(f"   Reference count: {len(refs)}")
        report_lines.append("")
        
        for i, ref in enumerate(refs, 1):
            report_lines.append(f"   REFERENCE #{i}:")
            uri = ref.get('URI', '')
            report_lines.append(f"      @URI: '{uri}' (empty={not uri}, starts_with_#={uri.startswith('#')})")
            
            # DigestMethod
            digest_method = ref.find('ds:DigestMethod', NS) or ref.find('{http://www.w3.org/2000/09/xmldsig#}DigestMethod')
            if digest_method is not None:
                report_lines.append(f"      DigestMethod/@Algorithm: {digest_method.get('Algorithm', 'MISSING')}")
            
            # DigestValue
            digest_value = ref.find('ds:DigestValue', NS) or ref.find('{http://www.w3.org/2000/09/xmldsig#}DigestValue')
            if digest_value is not None and digest_value.text:
                report_lines.append(f"      DigestValue (len): {len(digest_value.text.strip())} chars")
                report_lines.append(f"      DigestValue (base64 decoded len): {len(base64.b64decode(digest_value.text.strip()))} bytes")
            
            # Transforms
            transforms = ref.find('ds:Transforms', NS) or ref.find('{http://www.w3.org/2000/09/xmldsig#}Transforms')
            if transforms is not None:
                transform_list = transforms.findall('ds:Transform', NS) or transforms.findall('{http://www.w3.org/2000/09/xmldsig#}Transform')
                report_lines.append(f"      Transforms count: {len(transform_list)}")
                for j, transform in enumerate(transform_list, 1):
                    algo = transform.get('Algorithm', 'MISSING')
                    report_lines.append(f"         Transform #{j}: {algo}")
            else:
                report_lines.append("      Transforms: NONE")
            
            report_lines.append("")
    else:
        report_lines.append("2. SIGNEDINFO: NOT FOUND")
        report_lines.append("")
    
    # KeyInfo
    key_info = sig.find('ds:KeyInfo', NS) or sig.find('{http://www.w3.org/2000/09/xmldsig#}KeyInfo')
    if key_info is not None:
        report_lines.append("3. KEYINFO")
        x509_data = key_info.find('ds:X509Data', NS) or key_info.find('{http://www.w3.org/2000/09/xmldsig#}X509Data')
        if x509_data is not None:
            report_lines.append("   X509Data: PRESENT")
            
            # X509Certificate
            cert = x509_data.find('ds:X509Certificate', NS) or x509_data.find('{http://www.w3.org/2000/09/xmldsig#}X509Certificate')
            if cert is not None and cert.text:
                cert_bytes = base64.b64decode(cert.text.strip())
                cert_hash = hashlib.sha256(cert_bytes).hexdigest()
                report_lines.append(f"   X509Certificate SHA256: {cert_hash}")
                report_lines.append(f"   X509Certificate size: {len(cert_bytes)} bytes")
            
            # X509SubjectName
            subject = x509_data.find('ds:X509SubjectName', NS) or x509_data.find('{http://www.w3.org/2000/09/xmldsig#}X509SubjectName')
            if subject is not None and subject.text:
                report_lines.append(f"   X509SubjectName: {subject.text.strip()}")
            
            # X509IssuerSerial
            issuer_serial = x509_data.find('ds:X509IssuerSerial', NS) or x509_data.find('{http://www.w3.org/2000/09/xmldsig#}X509IssuerSerial')
            if issuer_serial is not None:
                issuer_name = issuer_serial.find('ds:X509IssuerName', NS) or issuer_serial.find('{http://www.w3.org/2000/09/xmldsig#}X509IssuerName')
                serial_num = issuer_serial.find('ds:X509SerialNumber', NS) or issuer_serial.find('{http://www.w3.org/2000/09/xmldsig#}X509SerialNumber')
                if issuer_name is not None and issuer_name.text:
                    report_lines.append(f"   X509IssuerName: {issuer_name.text.strip()}")
                if serial_num is not None and serial_num.text:
                    report_lines.append(f"   X509SerialNumber: {serial_num.text.strip()}")
        else:
            report_lines.append("   X509Data: NOT FOUND")
    else:
        report_lines.append("3. KEYINFO: NOT FOUND")
    
    report_lines.append("")
    report_lines.append("=" * 80)
    report_lines.append("4. INVARIANT VALIDATION")
    report_lines.append("=" * 80)
    
    issues = []
    
    # Check for duplicate IDs
    all_ids = root.xpath('//*[@Id]')
    id_values = [elem.get('Id') for elem in all_ids]
    id_counts = {}
    for id_val in id_values:
        id_counts[id_val] = id_counts.get(id_val, 0) + 1
    
    duplicates = {k: v for k, v in id_counts.items() if v > 1}
    if duplicates:
        issues.append(f"DUPLICATE IDs FOUND: {duplicates}")
    else:
        report_lines.append("✓ No duplicate IDs")
    
    # Check Reference URIs point to existing IDs
    if signed_info is not None:
        refs = signed_info.findall('ds:Reference', NS) or signed_info.findall('{http://www.w3.org/2000/09/xmldsig#}Reference')
        for ref in refs:
            uri = ref.get('URI', '')
            if uri.startswith('#'):
                target_id = uri[1:]
                if target_id not in id_values:
                    issues.append(f"Reference URI '{uri}' points to non-existent Id '{target_id}'")
                else:
                    report_lines.append(f"✓ Reference URI '{uri}' points to existing Id")
            elif not uri:
                issues.append("Reference has EMPTY URI (high risk)")
            else:
                issues.append(f"Reference URI '{uri}' does not start with # (unusual)")
    
    # Check which node is being signed
    if signed_info is not None:
        refs = signed_info.findall('ds:Reference', NS) or signed_info.findall('{http://www.w3.org/2000/09/xmldsig#}Reference')
        for ref in refs:
            uri = ref.get('URI', '')
            if uri.startswith('#'):
                target_id = uri[1:]
                target_elem = root.xpath(f'//*[@Id="{target_id}"]')
                if target_elem:
                    elem = target_elem[0]
                    local_name = elem.tag.split('}')[-1] if '}' in elem.tag else elem.tag
                    report_lines.append(f"✓ Signing element: <{local_name} Id=\"{target_id}\">")
                    
                    # Check if it's DE or rDE
                    if local_name not in ['DE', 'rDE']:
                        issues.append(f"Signing unexpected element: {local_name} (expected DE or rDE)")
    
    # Check Signature position
    rde = root.find('.//s:rDE', NS)
    if rde is not None:
        rde_children = list(rde)
        sig_index = None
        for i, child in enumerate(rde_children):
            local_name = child.tag.split('}')[-1] if '}' in child.tag else child.tag
            if local_name == 'Signature':
                sig_index = i
                break
        
        if sig_index is not None:
            expected_order = ['dVerFor', 'DE', 'Signature']
            actual_order = [c.tag.split('}')[-1] if '}' in c.tag else c.tag for c in rde_children[:sig_index+1]]
            report_lines.append(f"✓ rDE children order (up to Signature): {actual_order}")
            
            if actual_order != expected_order:
                issues.append(f"Unexpected element order in rDE. Expected {expected_order}, got {actual_order}")
    
    # Check for ds: prefixes in SIFEN namespace elements
    sifen_elements = root.xpath('//*[namespace-uri()="http://ekuatia.set.gov.py/sifen/xsd"]')
    for elem in sifen_elements:
        tag = elem.tag.split('}')[-1] if '}' in elem.tag else elem.tag
        if tag.startswith('ds'):
            issues.append(f"SIFEN namespace element has 'ds' prefix: {tag}")
    
    if not issues:
        report_lines.append("✓ All invariants validated successfully")
    else:
        report_lines.append("")
        report_lines.append("ISSUES FOUND:")
        for issue in issues:
            report_lines.append(f"  ✗ {issue}")
    
    report_lines.append("")
    report_lines.append("=" * 80)
    report_lines.append("END OF REPORT")
    report_lines.append("=" * 80)
    
    report = "\n".join(report_lines)
    
    with open(output_path, 'w', encoding='utf-8') as f:
        f.write(report)
    
    return report

if __name__ == '__main__':
    if len(sys.argv) < 3:
        print("Usage: python forensic_signature_analyzer.py <input.xml> <output_report.txt>")
        sys.exit(1)
    
    xml_file = sys.argv[1]
    output_file = sys.argv[2]
    
    report = analyze_signature(xml_file, output_file)
    print(report)
