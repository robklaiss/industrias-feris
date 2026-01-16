#!/usr/bin/env python3
"""
Simple demo to show the rEnvioLote wrapper configuration fix.
"""
import os
import sys
sys.path.insert(0, '.')

from tools.send_sirecepde import _resolve_envio_lote_root

print("=== rEnvioLote Wrapper Configuration Fix ===\n")

# Show current configuration
wrapper_name = _resolve_envio_lote_root()
print(f"✓ Default wrapper configured: {wrapper_name}")
print(f"  Environment SIFEN_ENVIOLOTE_ROOT: {os.getenv('SIFEN_ENVIOLOTE_ROOT', '(not set)')}\n")

print("Changes made:")
print("1. send_sirecepde.py - _resolve_envio_lote_root() now returns 'rEnvioLote' by default")
print("2. soap_client.py - _preferred_envio_root_name() now returns 'rEnvioLote' by default")
print("3. Added sanity check that forces 'rEnvioLote' when WSDL contains 'recibe-lote.wsdl'\n")

print("Expected SOAP body structure:")
print("""<soap:Body>
  <rEnvioLote xmlns="http://ekuatia.set.gov.py/sifen/xsd">
    <dId>123456789012345</dId>
    <xDE>BASE64_ZIP_CONTENT</xDE>
  </rEnvioLote>
</soap:Body>""")

print("\nTo test with real send:")
print("1. Run: python -m tools.send_sirecepde --env test --xml latest")
print("2. Check: python tools/test_rEnvioLote_wrapper.py")
