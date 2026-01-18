#!/usr/bin/env python3
"""
Debug tool to extract xDE from SOAP requests and analyze signature namespace.
Used for SIFEN 0160 debugging iterations.
"""

import base64
import zipfile
import io
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

def find_xde_element(soap_xml):
    """Find xDE element regardless of prefix."""
    # Parse SOAP XML
    root = ET.fromstring(soap_xml)
    
    # Get all elements and find xDE by tag name
    for elem in root.iter():
        if elem.tag.endswith('xDE'):
            return elem
    
    return None

def extract_and_analyze(soap_file):
    """Extract xDE from SOAP and analyze signature."""
    print(f"\n=== Analyzing {soap_file} ===\n")
    
    # Read SOAP file
    with open(soap_file, 'r', encoding='utf-8') as f:
        soap_content = f.read()
    
    # Find xDE element
    xde_elem = find_xde_element(soap_content)
    if xde_elem is None:
        print("❌ xDE element not found in SOAP!")
        return
    
    # Get base64 content
    xde_b64 = xde_elem.text.strip()
    print(f"✓ Found xDE with {len(xde_b64)} chars of base64")
    
    # Decode base64
    try:
        zip_bytes = base64.b64decode(xde_b64)
        print(f"✓ Decoded to {len(zip_bytes)} bytes")
    except Exception as e:
        print(f"❌ Failed to decode base64: {e}")
        return
    
    # Open ZIP in memory
    try:
        with zipfile.ZipFile(io.BytesIO(zip_bytes)) as zf:
            print("✓ ZIP opened successfully")
            print("\nZIP contents:")
            for name in zf.namelist():
                size = zf.getinfo(name).file_size
                print(f"  - {name} ({size} bytes)")
            
            # Extract lote.xml
            if 'lote.xml' in zf.namelist():
                with zf.open('lote.xml') as f:
                    lote_xml = f.read().decode('utf-8')
                
                print("\n=== lote.xml analysis ===")
                
                # First 3 lines
                lines = lote_xml.split('\n')[:3]
                print("\nFirst 3 lines:")
                for i, line in enumerate(lines, 1):
                    print(f"  {i}: {line}")
                
                # Find Signature line
                sig_lines = [line for line in lote_xml.split('\n') if '<Signature' in line]
                if sig_lines:
                    print(f"\nSignature line:")
                    print(f"  {sig_lines[0].strip()}")
                
                # Find Reference line
                ref_lines = [line for line in lote_xml.split('\n') if 'Reference URI=' in line]
                if ref_lines:
                    print(f"\nReference line:")
                    print(f"  {ref_lines[0].strip()}")
                
                # Check namespace
                if 'xmlns="http://www.w3.org/2000/09/xmldsig#"' in lote_xml:
                    print("\n✓ Signature uses XMLDSig namespace (xmldsig#)")
                elif 'xmlns="http://ekuatia.set.gov.py/sifen/xsd"' in lote_xml and '<Signature' in lote_xml:
                    print("\n⚠ Signature uses SIFEN namespace (sifen/xsd)")
                else:
                    print("\n? Signature namespace unclear")
                    
    except Exception as e:
        print(f"❌ Failed to open ZIP: {e}")
        return

def main():
    if len(sys.argv) != 2:
        print("Usage: python debug_extract_xde.py <soap_file>")
        sys.exit(1)
    
    soap_file = sys.argv[1]
    if not Path(soap_file).exists():
        print(f"❌ File not found: {soap_file}")
        sys.exit(1)
    
    extract_and_analyze(soap_file)

if __name__ == "__main__":
    main()
