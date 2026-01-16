#!/usr/bin/env python3
import sys
import os
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from lxml import etree
from app.sifen_client.xml_generator_v150 import create_rde_xml_v150
from tools.send_sirecepde import sign_and_normalize_rde_inside_xml

def main():
    # Forzar valores conocidos
    os.environ["SIFEN_CODSEG"] = "123456789"
    os.environ["SIFEN_TIP_CONT"] = "1"
    os.environ["SI_TIP_EMI"] = "1"
    
    # Generar XML base COMPLETO (con rDE)
    xml_str = create_rde_xml_v150(
        ruc="4554737",
        dv_ruc="8",
        timbrado="12345678",
        establecimiento="001",
        punto_expedicion="001",
        numero_documento="0000006",
        tipo_documento="1",
        fecha="2026-01-13",
        hora="10:05:00",
        csc="123456789"
    )
    
    # Firmar el rDE completo (no solo el DE)
    cert_path = os.getenv("SIFEN_SIGN_P12_PATH")
    cert_pass = os.getenv("SIFEN_SIGN_P12_PASSWORD")
    
    if not cert_path or not cert_pass:
        print("❌ Setear SIFEN_SIGN_P12_PATH y SIFEN_SIGN_P12_PASSWORD")
        sys.exit(1)
    
    xml_bytes = xml_str.encode('utf-8')
    
    # Firmar y normalizar rDE completo
    signed_bytes = sign_and_normalize_rde_inside_xml(
        xml_bytes, cert_path, cert_pass
    )
    
    # Guardar
    desktop = Path.home() / "Desktop" / "prevalidador_rde_signed.xml"
    desktop.write_bytes(signed_bytes)
    print(f"✅ XML guardado en: {desktop}")
    
    # Validar CDC
    from tools.debug_cdc import main as debug_main
    sys.argv = ["debug_cdc.py", str(desktop)]
    debug_main()

if __name__ == "__main__":
    main()
