#!/usr/bin/env python3
"""Test script to verify the rebuilt ZIP is being used"""

import os
import sys
sys.path.insert(0, 'tesaka-cv')

from tools.send_sirecepde import send_sirecepde
from pathlib import Path

# Set a real RUC for testing (you'll need to configure this with actual values)
os.environ['SIFEN_EMISOR_RUC'] = '4554737-8'  # Example RUC
os.environ['SIFEN_SKIP_RUC_GATE'] = '0'  # Enable RUC validation

# Test with the XML
result = send_sirecepde(
    xml_path=Path('../artifacts/de_20260109_180059.xml'),
    env='test',
    dump_http=True
)

print("\n=== RESULT ===")
print(f"success: {result.get('success')}")
if not result.get('success'):
    print(f"error: {result.get('error')}")
    print(f"error_type: {result.get('error_type')}")
else:
    print("✅ Successfully sent to SIFEN!")
    
    # Check if the response contains the expected structure
    if 'response' in result:
        resp = result['response']
        print(f"Response code: {resp.codigo_estado}")
        print(f"Response message: {resp.mensaje_estado}")
