#!/usr/bin/env python3
"""Test QR generation debug"""

import os
import sys
sys.path.insert(0, '.')

from app.sifen_client.qr_generator import build_qr_dcarqr

# Load the XML
with open('tools/artifacts/_passthrough_lote.xml', 'rb') as f:
    rde_bytes = f.read()

# Set environment variables
os.environ['SIFEN_QR_IDCSC'] = '0001'
os.environ['SIFEN_QR_CSC'] = 'TEST_CSC_1234567890_ABCDEFGHIJKLMNOPQRSTUVWXYZ'
os.environ['SIFEN_ENV'] = 'test'

try:
    qr_url = build_qr_dcarqr(rde_xml=rde_bytes)
    print(f"QR URL generated: {qr_url[:100]}...")
    print(f"QR URL length: {len(qr_url)}")
except Exception as e:
    print(f"Error generating QR: {e}")
    import traceback
    traceback.print_exc()
