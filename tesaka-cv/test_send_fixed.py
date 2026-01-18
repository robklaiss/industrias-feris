#!/usr/bin/env python3
"""
Script para probar enviando el XML con namespace corregido
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from tools.send_sirecepde import send_sirecepde
from pathlib import Path
import base64
import zipfile
import io

def fix_namespace_in_memory(xml_bytes: bytes) -> bytes:
    """Corrige el namespace de Signature en los bytes del XML"""
    xml_str = xml_bytes.decode('utf-8')
    xml_str = xml_str.replace(
        '<Signature xmlns="http://www.w3.org/2000/09/xmldsig#">',
        '<Signature xmlns="http://ekuatia.set.gov.py/sifen/xsd">'
    )
    return xml_str.encode('utf-8')

# Cargar y corregir el XML
xml_path = Path("artifacts/_debug_lote_from_xde.xml")
with open(xml_path, 'rb') as f:
    xml_bytes = f.read()

# Corregir namespace
xml_bytes = fix_namespace_in_memory(xml_bytes)

# Guardar temporalmente para usar con send_sirecepde
temp_path = Path("artifacts/_debug_lote_fixed.xml")
with open(temp_path, 'wb') as f:
    f.write(xml_bytes)

print(f"✅ XML corregido guardado en: {temp_path}")

# Verificar el cambio
if b'xmlns="http://ekuatia.set.gov.py/sifen/xsd"' in xml_bytes:
    print("✅ Signature tiene namespace SIFEN en el archivo corregido")
else:
    print("❌ Falló la corrección del namespace")

# Enviar
print("\n📡 Enviando a SIFEN...")
result = send_sirecepde(
    xml_path=temp_path,
    env="test",
    dump_http=True,
    goto_send=True
)

print("\n=== RESULTADO ===")
print(f"Success: {result.get('success')}")
if not result.get('success'):
    print(f"Error: {result.get('error')}")
