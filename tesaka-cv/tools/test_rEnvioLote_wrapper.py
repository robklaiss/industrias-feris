#!/usr/bin/env python3
"""
Regression test to verify that SOAP requests use rEnvioLote wrapper (not rEnvioLoteDe).
This script checks artifacts/soap_last_request_SENT.xml after sending a batch.
"""
import sys
import argparse
from pathlib import Path
import xml.etree.ElementTree as ET

def check_soap_wrapper(xml_path: Path) -> tuple[bool, str]:
    """Check if SOAP contains rEnvioLote and not rEnvioLoteDe."""
    if not xml_path.exists():
        return False, f"File not found: {xml_path}"
    
    try:
        content = xml_path.read_text(encoding="utf-8")
        
        # Check for correct wrapper
        has_rEnvioLote = "<rEnvioLote" in content
        has_rEnvioLoteDe = "<rEnvioLoteDe" in content
        
        if has_rEnvioLote and not has_rEnvioLoteDe:
            return True, "✓ SOAP uses rEnvioLote wrapper (correct)"
        elif has_rEnvioLoteDe:
            return False, "✗ SOAP uses rEnvioLoteDe wrapper (incorrect)"
        else:
            return False, "✗ Neither rEnvioLote nor rEnvioLoteDe found in SOAP"
            
    except Exception as e:
        return False, f"Error reading file: {e}"

def main():
    parser = argparse.ArgumentParser(
        description="Regression test for rEnvioLote wrapper in SOAP requests"
    )
    parser.add_argument(
        "--soap-file",
        default="artifacts/soap_last_request_SENT.xml",
        help="Path to SOAP request file (default: artifacts/soap_last_request_SENT.xml)"
    )
    args = parser.parse_args()
    
    soap_path = Path(args.soap_file)
    
    print("=== SIFEN SOAP Wrapper Regression Test ===")
    print(f"Checking file: {soap_path}")
    
    success, message = check_soap_wrapper(soap_path)
    
    print(f"\nResult: {message}")
    
    if success:
        print("\n✅ Test PASSED - SOAP request uses correct wrapper")
        return 0
    else:
        print("\n❌ Test FAILED - SOAP request uses incorrect wrapper")
        print("\nExpected: <rEnvioLote xmlns=\"http://ekuatia.set.gov.py/sifen/xsd\">")
        print("Found:    <rEnvioLoteDe> or missing wrapper")
        return 1

if __name__ == "__main__":
    sys.exit(main())
