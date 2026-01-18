#!/usr/bin/env python3
"""Test corregido"""

import re
import zipfile
import io
from tools.send_sirecepde import build_xde_zip_bytes_from_lote_xml

# Test 2: XML con wrapper
xml_con_wrapper = '<rLoteDE xmlns="http://ekuatia.set.gov.py/sifen/xsd"><rDE Id="test"><dVerFor>150</dVerFor></rDE></rLoteDE>'

print("Test 2: XML con wrapper")
zip_bytes = build_xde_zip_bytes_from_lote_xml(xml_con_wrapper)

zf = zipfile.ZipFile(io.BytesIO(zip_bytes))
with zf.open('xml_file.xml') as f:
    result = f.read().decode('utf-8')
    
print("Resultado:")
print(result)
print()
print(f"Cantidad de <rLoteDE>: {result.count('<rLoteDE')}")
print(f"Tiene doble wrapper? {'<rLoteDE><rLoteDE' in result}")

if result.count('<rLoteDE>') == 1:
    print("✅ Test 2 pasado: No se agregó wrapper extra")
else:
    print("❌ Test 2 falló")
