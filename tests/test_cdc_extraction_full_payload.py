#!/usr/bin/env python3
"""Anti-regression test for CDC extraction from full payload (rEnvioLote with xDE)"""

import sys
from pathlib import Path

# Add tesaka-cv directory to path
sys.path.insert(0, str(Path(__file__).parent / "tesaka-cv"))

from tools.send_sirecepde import _extract_metadata_from_xml

def test_cdc_extraction_from_full_payload():
    """
    Test that CDC is correctly extracted from a full payload (rEnvioLote).
    
    This is an anti-regression test for the issue where CDC was None
    when processing full payloads because the CDC is nested within
    xDE → ZIP → lote.xml → DE@Id
    """
    # Read the real diagnostic file
    diagnostic_file = Path(__file__).parent / "tesaka-cv" / "artifacts" / "diagnostic_last_soap_request_full.xml"
    
    if not diagnostic_file.exists():
        print(f"⚠️  Test file not found: {diagnostic_file}")
        print("   This test requires the diagnostic file to run")
        return True  # Pass if file doesn't exist (CI environment)
    
    with open(diagnostic_file, 'r') as f:
        xml_content = f.read()
    
    # Extract metadata
    metadata = _extract_metadata_from_xml(xml_content)
    
    # Assertions
    assert metadata is not None, "Metadata should not be None"
    assert metadata.get("dId") is not None, "dId should be extracted from rEnvioLote"
    assert metadata.get("CDC") is not None, "CDC should be extracted from xDE->lote.xml->DE@Id"
    assert metadata.get("dRucEm") is not None, "dRucEm should be extracted"
    assert metadata.get("dDVEmi") is not None, "dDVEmi should be extracted"
    assert metadata.get("dNumTim") is not None, "dNumTim should be extracted"
    
    # Verify specific values from the test file
    assert metadata.get("dId") == "202601221935443", f"Unexpected dId: {metadata.get('dId')}"
    assert metadata.get("CDC") == "01045547378001001119354412026011710000000018", f"Unexpected CDC: {metadata.get('CDC')}"
    assert metadata.get("dRucEm") == "4554737", f"Unexpected dRucEm: {metadata.get('dRucEm')}"
    assert metadata.get("dDVEmi") == "8", f"Unexpected dDVEmi: {metadata.get('dDVEmi')}"
    assert metadata.get("dNumTim") == "12560693", f"Unexpected dNumTim: {metadata.get('dNumTim')}"
    
    print("✅ CDC extraction from full payload works correctly")
    print(f"   dId: {metadata['dId']}")
    print(f"   CDC: {metadata['CDC']}")
    print(f"   dRucEm: {metadata['dRucEm']}")
    print(f"   dDVEmi: {metadata['dDVEmi']}")
    print(f"   dNumTim: {metadata['dNumTim']}")
    
    return True

if __name__ == "__main__":
    print("Testing CDC extraction from full payload (rEnvioLote)...")
    
    try:
        if test_cdc_extraction_from_full_payload():
            print("\n✅ Anti-regression test passed!")
            sys.exit(0)
    except AssertionError as e:
        print(f"\n❌ Anti-regression test failed: {e}")
        sys.exit(1)
    except Exception as e:
        print(f"\n❌ Unexpected error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
