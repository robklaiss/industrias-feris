#!/usr/bin/env python3
import sys
import os
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.sifen_client.xml_generator_v150 import create_rde_xml_v150
from tools.send_sirecepde import sign_and_normalize_rde_inside_xml

def main():
    if len(sys.argv) > 1:
        num_doc = sys.argv[1]
    else:
        num_doc = "1"
    
    # Forzar valores conocidos
    os.environ["SIFEN_CODSEG"] = "123456789"
    os.environ["SIFEN_TIP_CONT"] = "1"
    os.environ["SI_TIP_EMI"] = "1"
    
    # Generar XML completamente nuevo
    print(f"📄 Generando XML nuevo con dNumDoc={num_doc}")
    
    # Formatear número de documento a 7 dígitos
    num_doc_formatted = str(num_doc).zfill(7)[-7:]
    
    xml_str = create_rde_xml_v150(
        ruc="4554737",
        dv_ruc="8",
        timbrado="12345678",
        establecimiento="001",
        punto_expedicion="001",
        numero_documento=num_doc_formatted,
        tipo_documento="1",
        fecha="2026-01-13",
        hora="10:15:00",
        csc="123456789"
    )
    
    # Firmar el XML nuevo
    cert_path = os.getenv("SIFEN_SIGN_P12_PATH", "/Users/robinklaiss/.sifen/certs/F1T_65478.p12")
    cert_pass = os.getenv("SIFEN_SIGN_P12_PASSWORD", "bH1%T7EP")
    
    print("🔐 Firmando XML nuevo...")
    xml_bytes = xml_str.encode('utf-8')
    xml_bytes = sign_and_normalize_rde_inside_xml(xml_bytes, cert_path, cert_pass)
    
    # Guardar en Desktop
    desktop = Path.home() / "Desktop" / "prevalidador_rde_signed.xml"
    desktop.write_bytes(xml_bytes)
    print(f"✅ XML guardado en: {desktop}")
    print(f"   dNumDoc: {num_doc_formatted}")
    
    # Validar CDC
    os.system(f".venv/bin/python tools/debug_cdc.py {desktop}")

if __name__ == "__main__":
    main()
