#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Script CLI para corregir DE@Id en un archivo XML.

Uso:
    python -m tools.fix_de_id artifacts/de_test.xml
"""

import sys
from pathlib import Path

# Agregar el directorio padre al path para imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from tools.cdc_fix import fix_de_id_in_file


def main() -> int:
    if len(sys.argv) < 2:
        print("Uso: python -m tools.fix_de_id <archivo.xml>")
        return 1
    
    xml_path = sys.argv[1]
    
    try:
        cdc = fix_de_id_in_file(xml_path)
        print(f"✅ DE@Id corregido: {cdc}")
        return 0
    except SystemExit as e:
        # SystemExit ya tiene el mensaje de error
        return 1
    except Exception as e:
        print(f"❌ Error inesperado: {e}")
        return 1


if __name__ == "__main__":
    sys.exit(main())

