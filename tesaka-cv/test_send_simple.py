#!/usr/bin/env python3

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from tools.send_sirecepde import send_sirecepde
from pathlib import Path

# Probar con el lote ya firmado
xml_path = Path("artifacts/_debug_lote_from_xde.xml")
if not xml_path.exists():
    print(f"❌ El archivo {xml_path} no existe")
    sys.exit(1)

print(f"📄 Enviando: {xml_path}")
result = send_sirecepde(
    xml_path=xml_path,
    env="test",
    dump_http=True,
    goto_send=True  # Forzar modo AS-IS
)

print("\n=== RESULTADO ===")
print(f"Success: {result.get('success')}")
if not result.get('success'):
    print(f"Error: {result.get('error')}")
    print(f"Type: {result.get('error_type')}")
