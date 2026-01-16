#!/usr/bin/env python3
import sys
import os
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from tools.send_sirecepde import apply_bump_doc

def main():
    if len(sys.argv) > 1:
        num_doc = sys.argv[1]
    else:
        num_doc = "1"
    
    # Leer XML base
    xml_base = Path("artifacts/rde_signed_01045547378001001000000112026010210000000013.xml")
    xml_bytes = xml_base.read_bytes()
    
    # Aplicar bump-doc
    xml_bytes = apply_bump_doc(xml_bytes, num_doc, "test")
    
    # Guardar en Desktop
    desktop = Path.home() / "Desktop" / "prevalidador_rde_signed.xml"
    desktop.write_bytes(xml_bytes)
    print(f"✅ XML guardado en: {desktop}")
    print(f"   dNumDoc: {num_doc}")
    
    # Validar CDC
    os.system(f".venv/bin/python tools/debug_cdc.py {desktop}")

if __name__ == "__main__":
    main()
