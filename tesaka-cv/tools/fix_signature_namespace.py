#!/usr/bin/env python3
"""
Script para corregir el namespace de Signature en XML ya firmados.
Cambia <Signature xmlns="http://www.w3.org/2000/09/xmldsig#"> 
a <Signature xmlns="http://ekuatia.set.gov.py/sifen/xsd">
"""

import sys
import xml.etree.ElementTree as ET
from pathlib import Path

# Namespace SIFEN
SIFEN_NS = "http://ekuatia.set.gov.py/sifen/xsd"
XMLDSIG_NS = "http://www.w3.org/2000/09/xmldsig#"

def fix_signature_namespace(xml_file: Path):
    """Corrige el namespace de Signature en un XML."""
    print(f"📄 Procesando: {xml_file}")
    
    # Leer XML
    with open(xml_file, 'r', encoding='utf-8') as f:
        content = f.read()
    
    # Reemplazar namespace de Signature
    old_sig = f'<Signature xmlns="{XMLDSIG_NS}"'
    new_sig = f'<Signature xmlns="{SIFEN_NS}"'
    
    if old_sig in content:
        content = content.replace(old_sig, new_sig)
        print("✅ Namespace de Signature corregido")
        
        # Guardar
        with open(xml_file, 'w', encoding='utf-8') as f:
            f.write(content)
        print(f"💾 Archivo actualizado: {xml_file}")
    else:
        print("⚠️  No se encontró Signature con namespace xmldsig")
    
    # Verificar
    with open(xml_file, 'r', encoding='utf-8') as f:
        content = f.read()
    
    if f'xmlns="{SIFEN_NS}"' in content.split('<Signature')[1].split('>')[0]:
        print("✅ Verificación: Signature ahora tiene namespace SIFEN")
    else:
        print("❌ Verificación fallida")

if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Uso: python fix_signature_namespace.py <archivo.xml>")
        sys.exit(1)
    
    xml_file = Path(sys.argv[1])
    if not xml_file.exists():
        print(f"❌ El archivo {xml_file} no existe")
        sys.exit(1)
    
    fix_signature_namespace(xml_file)
