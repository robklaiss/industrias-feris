#!/usr/bin/env python3
"""Test QR generation debug with actual rDE"""

import os
import sys
sys.path.insert(0, '.')

from lxml import etree

# Load the XML
with open('tools/artifacts/_passthrough_lote.xml', 'rb') as f:
    content = f.read()

# Parse and extract rDE
root = etree.fromstring(content)
rde_elem = root.find('.//{http://ekuatia.set.gov.py/sifen/xsd}rDE')
rde_bytes = etree.tostring(rde_elem, encoding='utf-8')

print(f"rDE bytes length: {len(rde_bytes)}")
print("rDE content (first 200 chars):")
print(rde_bytes[:200])

# Set environment variables
os.environ['SIFEN_QR_IDCSC'] = '0001'
os.environ['SIFEN_QR_CSC'] = 'TEST_CSC_1234567890_ABCDEFGHIJKLMNOPQRSTUVWXYZ'
os.environ['SIFEN_ENV'] = 'test'

try:
    from app.sifen_client.qr_generator import build_qr_dcarqr
    qr_url = build_qr_dcarqr(rde_xml=rde_bytes)
    print(f"\n✅ QR URL generated: {qr_url[:100]}...")
except Exception as e:
    print(f"\n❌ Error: {e}")
    import traceback
    traceback.print_exc()
