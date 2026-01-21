#!/usr/bin/env python3
"""
Extrae el DE del XML real para usar como plantilla válida
"""

from lxml import etree
from pathlib import Path

def extraer_de():
    # Leer XML real
    xml_path = Path("../docs/fac_029-010-0189456_533750241.xml_01800140664029010018945612026010915677380320.xml")
    
    if not xml_path.exists():
        print(f"❌ Archivo no encontrado: {xml_path}")
        return
    
    parser = etree.XMLParser(remove_blank_text=False)
    tree = etree.parse(xml_path, parser)
    root = tree.getroot()
    
    # Extraer rDE
    rde = root.find(".//{http://ekuatia.set.gov.py/sifen/xsd}rDE")
    
    if rde is None:
        print("❌ No se encontró rDE")
        return
    
    # Guardar rDE como archivo individual
    output_path = Path("templates/rde_real_plantilla.xml")
    output_path.parent.mkdir(exist_ok=True)
    
    # Serializar con formato correcto
    xml_bytes = etree.tostring(rde, encoding='utf-8', xml_declaration=True, pretty_print=False)
    
    output_path.write_bytes(xml_bytes)
    print(f"✅ rDE guardado en: {output_path}")
    
    # Mostrar información
    SIFEN_NS = "{http://ekuatia.set.gov.py/sifen/xsd}"
    de = rde.find(f"{SIFEN_NS}DE")
    cdc = de.get('Id')
    print(f"   CDC: {cdc}")
    
    # Verificar firma
    signature = rde.find(".//{http://www.w3.org/2000/09/xmldsig#}Signature")
    if signature is not None:
        print("   ✅ Firma encontrada")
    else:
        print("   ❌ No se encontró firma")

if __name__ == "__main__":
    extraer_de()
