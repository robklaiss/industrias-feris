#!/usr/bin/env python3
"""Test QR injection debug"""

import os
import re
from xml.sax.saxutils import escape as _xml_escape

# Load the XML
with open('tools/artifacts/_passthrough_lote.xml', 'rb') as f:
    rde_bytes = f.read()

rde_str2 = rde_bytes.decode("utf-8", errors="strict")

print("Checking QR injection conditions:")
print(f"XML length: {len(rde_str2)}")
print(f"Contains <dCarQR>: {'<dCarQR>' in rde_str2}")
print(f"Contains <gCamFuFD>: {'<gCamFuFD>' in rde_str2}")

# Set environment variables
os.environ['SIFEN_QR_IDCSC'] = '0001'
os.environ['SIFEN_QR_CSC'] = 'TEST_CSC_1234567890_ABCDEFGHIJKLMNOPQRSTUVWXYZ'
os.environ['SIFEN_ENV'] = 'test'

if "<dCarQR>" not in rde_str2:
    print("Condition met: dCarQR not found, proceeding with QR generation...")
    
    # Import QR generator
    from app.sifen_client.qr_generator import build_qr_dcarqr
    
    # Generate QR
    qr_url = build_qr_dcarqr(
        rde_xml=rde_bytes,
        base_url=os.getenv("SIFEN_QR_BASE_URL") or os.getenv("QR_BASE_URL"),
        idcsc=os.getenv("SIFEN_IDCSC") or os.getenv("SIFEN_QR_IDCSC") or os.getenv("IDCSC"),
        csc=os.getenv("SIFEN_CSC") or os.getenv("SIFEN_QR_CSC") or os.getenv("CSC"),
    )
    qr_url_xml = _xml_escape(qr_url)
    
    print(f"QR URL generated (first 100 chars): {qr_url[:100]}...")
    
    # Check if gCamFuFD exists
    if re.search(r"<gCamFuFD\b[^>]*>", rde_str2):
        print("gCamFuFD found, injecting dCarQR...")
        rde_str2 = re.sub(
            r"(<gCamFuFD\b[^>]*>)",
            r"\1<dCarQR>" + qr_url_xml + r"</dCarQR>",
            rde_str2,
            count=1,
            flags=re.DOTALL,
        )
        print("✅ Injection completed")
        print(f"Contains <dCarQR> after injection: {'<dCarQR>' in rde_str2}")
    else:
        print("gCamFuFD not found, would create new one...")
else:
    print("❌ dCarQR already exists, skipping injection")
