#!/usr/bin/env python3
"""
Deep SOAP envelope analysis to find 0160 root cause.
"""
import sys
import base64
import zipfile
import io
from lxml import etree

def analyze_soap(soap_path, output_path):
    """Analyze SOAP envelope structure."""
    
    tree = etree.parse(soap_path)
    root = tree.getroot()
    
    NS = {
        'soap': 'http://www.w3.org/2003/05/soap-envelope',
        'sifen': 'http://ekuatia.set.gov.py/sifen/xsd',
        's': 'http://ekuatia.set.gov.py/sifen/xsd'
    }
    
    report = []
    report.append("=" * 80)
    report.append("SOAP ENVELOPE FORENSIC ANALYSIS")
    report.append("=" * 80)
    report.append("")
    
    # Extract xDE base64 content
    xde_elem = root.find('.//sifen:xDE', NS)
    if xde_elem is None:
        report.append("ERROR: No xDE element found in SOAP")
        return "\n".join(report)
    
    xde_b64 = xde_elem.text.strip()
    report.append(f"xDE base64 length: {len(xde_b64)} chars")
    
    # Decode and analyze ZIP
    try:
        xde_bytes = base64.b64decode(xde_b64)
        report.append(f"xDE decoded length: {len(xde_bytes)} bytes")
        report.append("")
        
        # Open ZIP
        with zipfile.ZipFile(io.BytesIO(xde_bytes), 'r') as zf:
            report.append("ZIP CONTENTS:")
            for info in zf.infolist():
                report.append(f"  File: {info.filename}")
                report.append(f"    Compressed: {info.compress_size} bytes")
                report.append(f"    Uncompressed: {info.file_size} bytes")
                report.append(f"    Compression: {info.compress_type}")
                report.append(f"    CRC: {info.CRC}")
            report.append("")
            
            # Extract lote.xml
            lote_xml = zf.read('lote.xml')
            report.append(f"lote.xml extracted: {len(lote_xml)} bytes")
            report.append("")
            
            # Parse and analyze lote.xml
            lote_tree = etree.fromstring(lote_xml)
            
            # Check for XML declaration in raw bytes
            if lote_xml.startswith(b'<?xml'):
                report.append("✓ lote.xml has XML declaration")
                decl_end = lote_xml.find(b'?>')
                if decl_end > 0:
                    decl = lote_xml[:decl_end+2].decode('utf-8', errors='replace')
                    report.append(f"  Declaration: {decl}")
            else:
                report.append("✗ lote.xml missing XML declaration")
            report.append("")
            
            # Check namespace on root
            report.append("LOTE.XML ROOT ELEMENT:")
            report.append(f"  Tag: {lote_tree.tag}")
            report.append(f"  Namespaces: {lote_tree.nsmap}")
            report.append("")
            
            # Find rDE
            rde = lote_tree.find('.//{http://ekuatia.set.gov.py/sifen/xsd}rDE')
            if rde is not None:
                report.append("rDE ELEMENT:")
                report.append(f"  Id: {rde.get('Id')}")
                report.append(f"  Namespaces: {rde.nsmap}")
                
                # Check for xmlns attribute (redundant namespace declaration)
                xmlns_attr = rde.get('xmlns')
                if xmlns_attr:
                    report.append(f"  ✗ REDUNDANT xmlns attribute: {xmlns_attr}")
                else:
                    report.append(f"  ✓ No redundant xmlns attribute")
                
                # List all attributes
                report.append(f"  All attributes: {dict(rde.attrib)}")
                report.append("")
                
                # Check children order
                children_tags = [c.tag.split('}')[-1] if '}' in c.tag else c.tag for c in rde]
                report.append(f"  Children order: {children_tags}")
                report.append("")
            
            # Find Signature
            sig = lote_tree.find('.//{http://www.w3.org/2000/09/xmldsig#}Signature')
            if sig is not None:
                report.append("SIGNATURE ELEMENT:")
                report.append(f"  Tag: {sig.tag}")
                report.append(f"  Namespaces: {sig.nsmap}")
                report.append(f"  Parent: {sig.getparent().tag}")
                
                # Check for xmlns attribute
                xmlns_attr = sig.get('xmlns')
                if xmlns_attr:
                    report.append(f"  xmlns attribute: {xmlns_attr}")
                else:
                    report.append(f"  ✗ No xmlns attribute on Signature")
                report.append("")
            
    except Exception as e:
        report.append(f"ERROR decoding/analyzing ZIP: {e}")
        import traceback
        report.append(traceback.format_exc())
    
    # Check SOAP envelope structure
    report.append("=" * 80)
    report.append("SOAP ENVELOPE STRUCTURE")
    report.append("=" * 80)
    report.append("")
    
    # Check namespaces
    report.append("Root namespaces:")
    for prefix, uri in root.nsmap.items():
        report.append(f"  {prefix or '(default)'}: {uri}")
    report.append("")
    
    # Check rEnvioLote
    renvio = root.find('.//sifen:rEnvioLote', NS)
    if renvio is not None:
        report.append("rEnvioLote element:")
        report.append(f"  Tag: {renvio.tag}")
        
        # Check for proper namespace prefix
        if renvio.tag.startswith('{'):
            ns_uri = renvio.tag.split('}')[0][1:]
            report.append(f"  Namespace URI: {ns_uri}")
            if ns_uri == 'http://ekuatia.set.gov.py/sifen/xsd':
                report.append("  ✓ Correct namespace")
            else:
                report.append(f"  ✗ Wrong namespace")
        
        # Check children
        for child in renvio:
            child_name = child.tag.split('}')[-1] if '}' in child.tag else child.tag
            report.append(f"  Child: {child_name}")
            if child_name == 'dId':
                report.append(f"    Value: {child.text}")
            elif child_name == 'xDE':
                report.append(f"    Value: [base64, {len(child.text)} chars]")
    
    report.append("")
    report.append("=" * 80)
    
    full_report = "\n".join(report)
    
    with open(output_path, 'w', encoding='utf-8') as f:
        f.write(full_report)
    
    return full_report

if __name__ == '__main__':
    if len(sys.argv) < 3:
        print("Usage: python forensic_soap_analyzer.py <soap.xml> <output.txt>")
        sys.exit(1)
    
    report = analyze_soap(sys.argv[1], sys.argv[2])
    print(report)
