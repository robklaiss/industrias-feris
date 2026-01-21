#!/usr/bin/env python3

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from tools.send_sirecepde import send_sirecepde
from pathlib import Path


def run_send_simple_test():
    """Run simple send test."""
    # Probar con el lote ya firmado
    xml_path = Path("artifacts/_debug_lote_from_xde.xml")
    if not xml_path.exists():
        print(f"❌ El archivo {xml_path} no existe")
        return False

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
    
    return result.get('success', False)


if __name__ == "__main__":
    success = run_send_simple_test()
    sys.exit(0 if success else 1)
