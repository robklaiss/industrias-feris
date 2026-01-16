#!/usr/bin/env python3
"""
Demo script to show the rEnvioLote wrapper fix.
This script simulates the SOAP body generation with the correct wrapper.
"""
import os
import sys
sys.path.insert(0, '.')

from tools.send_sirecepde import build_r_envio_lote_xml, _resolve_envio_lote_root

# Simulate XML content
sample_xml = b'''<?xml version="1.0" encoding="UTF-8"?>
<rDE xmlns="http://ekuatia.set.gov.py/sifen/xsd" Id="DE123456">
  <dVerFor>150</dVerFor>
  <DE Id="DE123456">
    <!-- Sample DE content -->
  </DE>
</rDE>'''

print("=== Demo: rEnvioLote Wrapper Fix ===\n")

# Show the wrapper that will be used
wrapper_name = _resolve_envio_lote_root()
print(f"Wrapper configured: {wrapper_name}")
print(f"Environment SIFEN_ENVIOLOTE_ROOT: {os.getenv('SIFEN_ENVIOLOTE_ROOT', '(not set)')}\n")

# Build the SOAP body
soap_body = build_r_envio_lote_xml(did=123456789012345, xml_bytes=sample_xml)

print("Generated SOAP body:")
print("=" * 50)
print(soap_body)
print("=" * 50)

# Verify the wrapper
if "<rEnvioLote " in soap_body:
    print("\n✅ SUCCESS: SOAP body uses rEnvioLote wrapper (correct)")
elif "<rEnvioLoteDe " in soap_body:
    print("\n❌ ERROR: SOAP body uses rEnvioLoteDe wrapper (incorrect)")
else:
    print("\n⚠️  WARNING: Could not find wrapper in SOAP body")
