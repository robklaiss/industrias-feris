#!/usr/bin/env python3
import sys
import os
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from lxml import etree
from app.sifen_client.xml_generator_v150 import create_rde_xml_v150
from app.sifen_client.xmlsec_signer import sign_de_with_p12

def main():
    if len(sys.argv) > 1:
        num_doc = sys.argv[1]
    else:
        num_doc = "1"
    
    # Forzar valores conocidos
    os.environ["SIFEN_CODSEG"] = "123456789"
    os.environ["SIFEN_TIP_CONT"] = "1"
    os.environ["SI_TIP_EMI"] = "1"
    
    # Formatear número
    num_doc_formatted = str(num_doc).zfill(7)[-7:]
    
    print(f"📄 Generando XML con dNumDoc={num_doc_formatted}")
    
    # Generar XML base (sin CDC)
    xml_str = create_rde_xml_v150(
        ruc="4554737",
        dv_ruc="8",
        timbrado="12345678",
        establecimiento="001",
        punto_expedicion="001",
        numero_documento=num_doc_formatted,
        tipo_documento="1",
        fecha="2026-01-13",
        hora="10:18:00",
        csc="123456789"
    )
    
    # Parsear XML para modificar antes de firmar
    parser = etree.XMLParser(remove_blank_text=False)
    root = etree.fromstring(xml_str.encode('utf-8'), parser)
    
    # Namespaces
    SIFEN_NS = "{http://ekuatia.set.gov.py/sifen/xsd}"
    
    # El XML ya tiene el CDC correcto porque create_rde_xml_v150 lo calcula
    de = root.find(f"{SIFEN_NS}DE")
    current_cdc = de.get("Id")
    print(f"   CDC generado: {current_cdc}")
    
    # Convertir a bytes para firmar
    xml_bytes = etree.tostring(root, encoding='utf-8', xml_declaration=True)
    
    # Firmar el XML COMPLETO (con rDE)
    cert_path = os.getenv("SIFEN_SIGN_P12_PATH", "/Users/robinklaiss/.sifen/certs/F1T_65478.p12")
    cert_pass = os.getenv("SIFEN_SIGN_P12_PASSWORD", "bH1%T7EP")
    
    print("🔐 Firmando XML completo...")
    
    # Extraer solo el DE para firmar (como lo hace el sistema)
    de_elem = root.find(f"{SIFEN_NS}DE")
    de_bytes = etree.tostring(de_elem, encoding='utf-8')
    
    # Firmar el DE
    signed_de_bytes = sign_de_with_p12(de_bytes, cert_path, cert_pass)
    
    # Parsear el DE firmado y volver a poner en rDE
    signed_de = etree.fromstring(signed_de_bytes)
    
    # Reemplazar DE sin firma con DE firmado
    root.replace(de_elem, signed_de)
    
    # Serializar XML final
    final_bytes = etree.tostring(root, encoding='utf-8', xml_declaration=True)
    
    # Guardar
    desktop = Path.home() / "Desktop" / "prevalidador_rde_signed.xml"
    desktop.write_bytes(final_bytes)
    
    print(f"✅ XML guardado en: {desktop}")
    print(f"   dNumDoc: {num_doc_formatted}")
    print(f"   CDC: {current_cdc}")
    
    # Validar
    os.system(f".venv/bin/python tools/debug_cdc.py {desktop}")

if __name__ == "__main__":
    main()
