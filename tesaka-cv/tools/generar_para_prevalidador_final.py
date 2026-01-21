#!/usr/bin/env python3
import sys
import os
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from lxml import etree
from tools.send_sirecepde import apply_bump_doc, sign_and_normalize_rde_inside_xml

def remove_existing_signature(xml_bytes: bytes) -> bytes:
    """Elimina cualquier Signature existente del rDE"""
    parser = etree.XMLParser(remove_blank_text=False)
    root = etree.fromstring(xml_bytes, parser)
    
    # Buscar rDE (con namespace)
    SIFEN_NS = "{http://ekuatia.set.gov.py/sifen/xsd}"
    rde = root if root.tag == f"{SIFEN_NS}rDE" else root.find(f".//{SIFEN_NS}rDE")
    if rde is not None:
        # Eliminar todos los elementos Signature
        DS_NS = "{http://www.w3.org/2000/09/xmldsig#}"
        for sig in rde.findall(f".//{DS_NS}Signature"):
            sig.getparent().remove(sig)
    
    return etree.tostring(root, encoding='utf-8', xml_declaration=True)

def local_tag(tag):
    """Obtiene el tag local sin namespace"""
    if isinstance(tag, str):
        return tag.split('}')[-1] if '}' in tag else tag
    return tag

def main():
    if len(sys.argv) > 1:
        num_doc = sys.argv[1]
    else:
        num_doc = "1"
    
    # Leer XML base
    xml_base = Path("artifacts/rde_signed_01045547378001001000000112026010210000000013.xml")
    xml_bytes = xml_base.read_bytes()
    
    # Aplicar bump-doc (modifica dNumDoc y CDC)
    xml_bytes = apply_bump_doc(xml_bytes, num_doc, "test")
    
    # ELIMINAR firma existente
    print("🗑️  Eliminando firma existente...")
    xml_bytes = remove_existing_signature(xml_bytes)
    
    # VOLVER A FIRMAR el XML modificado usando sign_rde_with_p12
    cert_path = os.getenv("SIFEN_SIGN_P12_PATH", "/Users/robinklaiss/.sifen/certs/F1T_65478.p12")
    cert_pass = os.getenv("SIFEN_SIGN_P12_PASSWORD", "bH1%T7EP")
    
    print("🔐 Firmando XML modificado...")
    # Firmar el XML sin firma (ya fue eliminada)
    xml_bytes = sign_and_normalize_rde_inside_xml(xml_bytes, cert_path, cert_pass)
    
    # Guardar en Desktop
    desktop = Path.home() / "Desktop" / "prevalidador_rde_signed.xml"
    desktop.write_bytes(xml_bytes)
    print(f"✅ XML guardado en: {desktop}")
    print(f"   dNumDoc: {num_doc}")
    
    # Validar CDC
    os.system(f".venv/bin/python tools/debug_cdc.py {desktop}")

if __name__ == "__main__":
    main()
