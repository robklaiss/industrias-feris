#!/usr/bin/env python3
"""Test script to verify SOAP headers have correct action URI"""

import sys
sys.path.insert(0, 'app')

from sifen_client.soap_client import _build_soap12_headers, _content_type_action_value

# Test siRecepLoteDE headers
print("=== Headers para siRecepLoteDE ===")
headers = _build_soap12_headers("siRecepLoteDE", _content_type_action_value())
print(f"Content-Type: {headers['Content-Type']}")
print()

# Verify the action is the full URI
expected_action = "http://ekuatia.set.gov.py/sifen/xsd/siRecepLoteDE"
if expected_action in headers['Content-Type']:
    print("✅ Correcto: Action contiene la URI completa del namespace SIFEN")
else:
    print("❌ Error: Action no contiene la URI completa")

print()
print("=== Valor por defecto del action ===")
default_action = _content_type_action_value()
print(f"Action default: {default_action}")
